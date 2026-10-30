import asyncio
import json
import logging
import os
import sys
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from math import isfinite
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from redis.exceptions import RedisError
from sqlalchemy import func, select
from sqlalchemy.dialects.mysql import insert as mysql_insert
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.db.models import (
    ChipDistributionSnapshot,
    CompanyDatasetState,
    CompanyFinancialReport,
    CompanyNotice,
    FundFlowBar,
    HolderSnapshot,
    Instrument,
    MarketDailyBar,
    MarketStatistic,
    UserWatchlist,
    ValuationSnapshot,
)

logger = logging.getLogger(__name__)
BACKEND_ROOT = Path(__file__).resolve().parents[2]
MARKET_TIMEZONE = ZoneInfo("Asia/Shanghai")
CORE_INDEX_CODES = (
    "SSE:000001", "SZSE:399001", "SZSE:399006", "SSE:000688",
    "SSE:000300", "SSE:000905", "SSE:000852", "SSE:000016",
)
CORE_INDEX_PROVIDER_SYMBOLS = {
    "SSE:000001": "sh000001",
    "SZSE:399001": "sz399001",
    "SZSE:399006": "sz399006",
    "SSE:000688": "sh000688",
    "SSE:000300": "sh000300",
    "SSE:000905": "sh000905",
    "SSE:000852": "sh000852",
    "SSE:000016": "sh000016",
}
RESEARCH_DATASETS = ("notices", "financial", "valuation", "chip", "fund_flow", "holders")
_PROVIDER_SEMAPHORE = asyncio.Semaphore(4)
_TRANSIENT_PROVIDER_ERRORS = (
    "connectionerror", "connection reset", "remotedisconnected", "readtimeout",
    "connecttimeout", "timed out", "timeout", "temporarily unavailable",
)


def _market_overview_needs_refresh(row: MarketStatistic | None, now: datetime) -> bool:
    if row is None or row.collected_at is None or not row.trade_date_source:
        return True
    if row.collected_at < now - timedelta(hours=6):
        return True
    return (
        (row.limit_up is None or row.limit_down is None)
        and row.collected_at < now - timedelta(minutes=15)
    )


def _utc_naive(value: datetime | str) -> datetime:
    """Normalize a timestamp to naive UTC for MySQL DATETIME columns."""
    if isinstance(value, str):
        value = datetime.fromisoformat(value)
    if value.tzinfo is None:
        return value
    return value.astimezone(UTC).replace(tzinfo=None)


def _utc_iso(value: datetime | date | None) -> str | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        value = value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)
    return value.isoformat()


class MarketDataError(Exception):
    def __init__(self, message: str, retry_count: int = 0):
        super().__init__(message)
        self.retry_count = retry_count


@dataclass(frozen=True, slots=True)
class ProviderOutput:
    value: Any
    retry_count: int = 0


class InstrumentSearchResults(list[dict[str, str]]):
    def __init__(
        self,
        values: list[dict[str, str]],
        retry_count: int = 0,
        provider_error: bool = False,
    ):
        super().__init__(values)
        self.retry_count = retry_count
        self.provider_error = provider_error


class MarketDataService:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession], redis: Any | None):
        self.session_factory = session_factory
        self.redis = redis

    async def _cache_get(self, key: str) -> Any | None:
        if self.redis is None:
            return None
        try:
            value = await self.redis.get(key)
            return json.loads(value) if value else None
        except (RedisError, TypeError, ValueError):
            logger.warning("Redis read failed for key %s", key)
            return None

    async def _cache_set(self, key: str, value: Any, ttl: int) -> bool:
        if self.redis is None:
            return False
        try:
            await self.redis.set(key, json.dumps(value, ensure_ascii=False, default=str), ex=ttl)
            return True
        except (RedisError, TypeError, ValueError):
            logger.warning("Redis write failed for key %s", key)
            return False

    async def _run_provider(self, *arguments: str, timeout: int = 30) -> ProviderOutput:
        environment = os.environ.copy()
        old_pythonpath = environment.get("PYTHONPATH", "")
        environment["PYTHONPATH"] = os.pathsep.join(
            path for path in (str(BACKEND_ROOT), old_pythonpath) if path
        )
        async with _PROVIDER_SEMAPHORE:
            for attempt in range(2):
                worker = await asyncio.create_subprocess_exec(
                    sys.executable, "-m", "app.data.worker", *arguments,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                    env=environment,
                    limit=8 * 1024 * 1024,
                )
                try:
                    stdout, stderr = await asyncio.wait_for(worker.communicate(), timeout=timeout)
                except TimeoutError as exc:
                    worker.kill()
                    await worker.communicate()
                    if attempt == 0:
                        await asyncio.sleep(0.35)
                        continue
                    raise MarketDataError("行情源请求超时", retry_count=attempt) from exc
                except asyncio.CancelledError:
                    worker.kill()
                    await worker.communicate()
                    raise
                if worker.returncode != 0:
                    details = (stderr or b"").decode("utf-8", errors="replace")
                    logger.warning("AKShare worker failed: %s", details[-2000:])
                    transient = any(
                        marker in details.casefold() for marker in _TRANSIENT_PROVIDER_ERRORS
                    )
                    if attempt == 0 and transient:
                        await asyncio.sleep(0.35)
                        continue
                    raise MarketDataError("行情源暂时不可用", retry_count=attempt)
                try:
                    return ProviderOutput(json.loads(stdout), retry_count=attempt)
                except (json.JSONDecodeError, UnicodeDecodeError) as exc:
                    raise MarketDataError("行情源返回格式异常", retry_count=attempt) from exc
        raise MarketDataError("行情源暂时不可用", retry_count=1)

    async def _resolve_instrument(
        self, session: AsyncSession, symbol: str, owner_id: str
    ) -> Instrument:
        normalized = symbol.strip().upper()
        lower_symbol = symbol.strip().lower()
        instrument = await session.scalar(
            select(Instrument).where(
                (func.upper(Instrument.code) == normalized)
                | (func.lower(Instrument.provider_symbol) == lower_symbol)
            )
        )
        if instrument is None and symbol.strip().isdigit():
            instrument = await session.scalar(
                select(Instrument).where(
                    Instrument.instrument_type == "equity",
                    Instrument.provider_symbol == symbol.strip(),
                )
            )
        if instrument is None and symbol.strip().upper() in CORE_INDEX_PROVIDER_SYMBOLS:
            instrument = await session.scalar(
                select(Instrument).where(
                    Instrument.instrument_type == "index",
                    Instrument.provider_symbol == CORE_INDEX_PROVIDER_SYMBOLS[symbol.strip().upper()],
                )
            )
        if instrument is None or not instrument.is_active:
            raise MarketDataError(f"没有找到标的：{symbol}")
        if instrument.instrument_type == "equity":
            in_watchlist = await session.scalar(
                select(UserWatchlist.id).where(
                    UserWatchlist.owner_id == owner_id,
                    UserWatchlist.instrument_code == instrument.code,
                )
            )
            if in_watchlist is None:
                raise MarketDataError("个股数据仅对当前用户关注列表开放，请先添加该股票")
        return instrument

    async def _fetch_and_store_daily(
        self,
        session: AsyncSession,
        instrument: Instrument,
        adjustment: str,
        lookback_days: int,
    ) -> tuple[int, int]:
        end_date = datetime.now(MARKET_TIMEZONE).date()
        start_date = end_date - timedelta(days=lookback_days)
        if instrument.instrument_type == "index":
            provider = await self._run_provider(
                "index-daily", instrument.provider_symbol,
                start_date.isoformat(), end_date.isoformat(), timeout=35,
            )
            payload = provider.value
            adjustment = "none"
        else:
            provider = await self._run_provider(
                "daily", instrument.provider_symbol, instrument.instrument_type,
                start_date.isoformat(), end_date.isoformat(), adjustment, timeout=35,
            )
            payload = provider.value
        records = payload.get("records", [])
        if not records:
            raise MarketDataError("行情源未返回有效日线记录", retry_count=provider.retry_count)
        source = payload["source"]
        values = [
            {
                **record,
                "instrument_code": instrument.code,
                "adjustment": adjustment,
                "source": source,
            }
            for record in records
        ]
        statement = mysql_insert(MarketDailyBar).values(values)
        statement = statement.on_duplicate_key_update(
            open=statement.inserted.open,
            high=statement.inserted.high,
            low=statement.inserted.low,
            close=statement.inserted.close,
            volume=statement.inserted.volume,
            amount=statement.inserted.amount,
            change_pct=statement.inserted.change_pct,
            turnover_rate=statement.inserted.turnover_rate,
            source=statement.inserted.source,
            collected_at=func.now(),
        )
        await session.execute(statement)
        await session.flush()
        return len(values), provider.retry_count

    async def get_price_history(
        self, owner_id: str, symbol: str, period: str = "daily", limit: int = 60,
        adjustment: str = "qfq",
    ) -> dict[str, Any]:
        if period not in {"daily", "weekly", "monthly"}:
            raise MarketDataError("周期必须是 daily、weekly 或 monthly")
        if adjustment not in {"qfq", "hfq", "none"}:
            raise MarketDataError("复权口径必须是 qfq、hfq 或 none")
        limit = max(1, min(limit, 250))
        async with self.session_factory() as session:
            instrument = await self._resolve_instrument(session, symbol, owner_id)
            effective_adjustment = "none" if instrument.instrument_type == "index" else adjustment
            daily_factor = {"daily": 1, "weekly": 7, "monthly": 32}[period]
            requested_daily = min(2500, limit * daily_factor + 30)
            available = await session.scalar(
                select(func.count(MarketDailyBar.id)).where(
                    MarketDailyBar.instrument_code == instrument.code,
                    MarketDailyBar.adjustment == effective_adjustment,
                )
            ) or 0
            latest = await session.scalar(
                select(func.max(MarketDailyBar.trade_date)).where(
                    MarketDailyBar.instrument_code == instrument.code,
                    MarketDailyBar.adjustment == effective_adjustment,
                )
            )
            age_days = (datetime.now(MARKET_TIMEZONE).date() - latest).days if latest else None
            fresh = latest is not None and age_days is not None and age_days <= 5
            cache_status = "database"
            retry_count = 0
            refresh_warning = None
            if available < requested_daily or not fresh:
                try:
                    fetched, retry_count = await self._fetch_and_store_daily(
                        session, instrument, effective_adjustment,
                        min(3650, requested_daily * 2),
                    )
                    await session.commit()
                    if not fetched:
                        raise MarketDataError("行情源未返回有效日线记录", retry_count=retry_count)
                    cache_status = "database_refreshed"
                except MarketDataError as exc:
                    retry_count = exc.retry_count
                    if available == 0:
                        raise
                    cache_status = "database_stale"
                    refresh_warning = (
                        f"行情源刷新失败，返回数据库已有数据；最近记录日期为 {latest}。"
                    )

            rows = (
                await session.scalars(
                    select(MarketDailyBar)
                    .where(
                        MarketDailyBar.instrument_code == instrument.code,
                        MarketDailyBar.adjustment == effective_adjustment,
                    )
                    .order_by(MarketDailyBar.trade_date.desc())
                    .limit(requested_daily)
                )
            ).all()
            records = [self._bar_dict(row) for row in reversed(rows)]

        if period != "daily":
            records = self._aggregate(records, period)
        records = records[-limit:]
        latest_date = records[-1]["date"] if records else None
        current_date = datetime.now(MARKET_TIMEZONE).date()
        last_record_date = date.fromisoformat(latest_date) if latest_date else None
        data_sources = sorted({
            record.get("source") for record in records if record.get("source")
        })
        source_summary = ", ".join(data_sources) if data_sources else "source not recorded"
        current_period_incomplete = bool(
            last_record_date and period != "daily" and (
                (period == "weekly" and last_record_date.isocalendar()[:2]
                 == current_date.isocalendar()[:2])
                or (period == "monthly" and last_record_date.strftime("%Y-%m")
                    == current_date.strftime("%Y-%m"))
            )
        )
        warnings = [refresh_warning] if refresh_warning else []
        if current_period_incomplete:
            warnings.append(
                f"当前{('周线' if period == 'weekly' else '月线')}尚未结束，最新周期仅为阶段数据。"
            )
        return {
            "symbol": instrument.provider_symbol,
            "name": instrument.name,
            "instrument_type": instrument.instrument_type,
            "period": period,
            "adjustment": effective_adjustment,
            "unit": {
                "price": "index point" if instrument.instrument_type == "index" else "CNY/share",
                "volume": "lot (100 shares)",
                "amount": (
                    "CNY when provided; Sina index data has no amount field"
                    if instrument.instrument_type == "index"
                    else "CNY"
                ),
                "change_pct": "%",
                "turnover_rate": (
                    "% (sum of daily rates; approximate period turnover)"
                    if period != "daily" else "%"
                ),
            },
            "source": f"MySQL market bars: {source_summary}",
            "data_as_of": latest_date,
            "cache_status": cache_status,
            "retry_count": retry_count,
            "warning": "；".join(warnings) or None,
            "current_period_may_be_incomplete": current_period_incomplete,
            "bars": records,
        }

    @staticmethod
    def _bar_dict(bar: MarketDailyBar) -> dict[str, Any]:
        return {
            "date": bar.trade_date.isoformat(), "open": bar.open, "high": bar.high,
            "low": bar.low, "close": bar.close, "volume": bar.volume,
            "amount": bar.amount, "change_pct": bar.change_pct,
            "turnover_rate": bar.turnover_rate, "source": bar.source,
        }

    @staticmethod
    def _aggregate(records: list[dict[str, Any]], period: str) -> list[dict[str, Any]]:
        groups: dict[tuple[int, ...], list[dict[str, Any]]] = {}
        for record in records:
            current = date.fromisoformat(record["date"])
            if period == "weekly":
                key = (current.isocalendar().year, current.isocalendar().week)
            else:
                key = (current.year, current.month)
            groups.setdefault(key, []).append(record)

        aggregated = []
        previous_close = None
        for rows in groups.values():
            opens = [row["open"] for row in rows if row["open"] is not None]
            highs = [row["high"] for row in rows if row["high"] is not None]
            lows = [row["low"] for row in rows if row["low"] is not None]
            closes = [row["close"] for row in rows if row["close"] is not None]
            close = closes[-1] if closes else None
            change_pct = (
                (close / previous_close - 1) * 100
                if close is not None and previous_close not in (None, 0)
                else None
            )
            sources = sorted({row.get("source") for row in rows if row.get("source")})

            def sum_available(field: str, current_rows=rows) -> float | None:
                values = [
                    row[field] for row in current_rows if row.get(field) is not None
                ]
                return sum(values) if values else None

            aggregated.append({
                "date": rows[-1]["date"],
                "open": opens[0] if opens else None,
                "high": max(highs) if highs else None,
                "low": min(lows) if lows else None,
                "close": close,
                "volume": sum_available("volume"),
                "amount": sum_available("amount"),
                "change_pct": change_pct,
                "turnover_rate": sum_available("turnover_rate"),
                "source": ", ".join(sources) if sources else None,
            })
            previous_close = close
        return aggregated

    async def get_intraday(
        self, owner_id: str, symbol: str, period: str = "5", limit: int = 500
    ) -> dict[str, Any]:
        if period not in {"1", "5", "15", "30", "60"}:
            raise MarketDataError("分时周期只支持 1、5、15、30、60 分钟")
        limit = max(1, min(limit, 2000))
        async with self.session_factory() as session:
            instrument = await self._resolve_instrument(session, symbol, owner_id)
            if instrument.instrument_type != "equity":
                raise MarketDataError("分时接口当前只支持关注列表内的个股")
            code = instrument.provider_symbol
            name = instrument.name
        key = f"market:intraday:{code}:{period}"
        points = await self._cache_get(key)
        cache_status = "hit"
        retry_count = 0
        if points is None:
            provider = await self._run_provider("minute", code, period, timeout=35)
            points = provider.value
            retry_count = provider.retry_count
            ttl = {"1": 15, "5": 30, "15": 60, "30": 120, "60": 180}[period]
            cached = await self._cache_set(key, points, ttl)
            cache_status = "miss_cached" if cached else "miss"
        return {
            "symbol": code, "name": name, "period_minutes": int(period),
            "source": "AKShare", "cache_status": cache_status,
            "retry_count": retry_count,
            "data_as_of": points[-1].get("time") if points else None,
            "bars": points[-max(1, min(limit, 2000)):],
        }

    async def get_recent_trades(self, owner_id: str, symbol: str) -> dict[str, Any]:
        async with self.session_factory() as session:
            instrument = await self._resolve_instrument(session, symbol, owner_id)
            if instrument.instrument_type != "equity":
                raise MarketDataError("逐笔成交接口当前只支持关注列表内的个股")
            code = instrument.provider_symbol
            name = instrument.name
        key = f"market:trades:{code}"
        trades = await self._cache_get(key)
        cache_status = "hit"
        retry_count = 0
        if trades is None:
            try:
                provider = await self._run_provider("ticks", code, timeout=15)
                trades = provider.value
                retry_count = provider.retry_count
            except MarketDataError as exc:
                raise MarketDataError(
                    f"逐笔数据源不可用，未保存原始成交记录：{exc}",
                    retry_count=exc.retry_count,
                ) from exc
            cached = await self._cache_set(key, trades, 10)
            cache_status = "miss_cached" if cached else "miss"
        return {
            "symbol": code, "name": name, "source": "AKShare",
            "cache_status": cache_status,
            "retry_count": retry_count,
            "retrieved_at": datetime.now(UTC).isoformat(timespec="seconds"),
            "storage_policy": "Redis only; raw trades are not stored in MySQL",
            "trades": trades,
        }

    async def get_current_quote(self, owner_id: str, symbol: str) -> dict[str, Any]:
        async with self.session_factory() as session:
            instrument = await self._resolve_instrument(session, symbol, owner_id)
            code = instrument.provider_symbol
            name = instrument.name
        key = f"market:quote:{code.casefold()}"
        cached = await self._cache_get(key)
        if cached is not None:
            return {**cached, "cache_status": "hit", "retry_count": 0}
        try:
            provider = await self._run_provider("quote", code, timeout=20)
        except MarketDataError as exc:
            try:
                history = await self.get_price_history(owner_id, symbol, "daily", 1)
            except MarketDataError as history_error:
                raise MarketDataError(
                    f"实时报价不可用，且无法读取最近收盘数据：{history_error}",
                    retry_count=exc.retry_count + history_error.retry_count,
                ) from history_error
            last_bar = history["bars"][-1] if history["bars"] else None
            if last_bar is None:
                raise
            return {
                "symbol": code, "name": name,
                "quote": {"price": last_bar["close"], "change_pct": last_bar["change_pct"]},
                "source": history["source"], "data_as_of": history["data_as_of"],
                "observed_at": None, "market_time": None,
                "units": history["unit"], "cache_status": "database_stale",
                "retry_count": exc.retry_count + history.get("retry_count", 0),
                "warning": "；".join(filter(None, [
                    "实时报价源不可用，以下是最近一个交易日收盘数据，不代表当前价格。",
                    history.get("warning"),
                ])),
            }
        result = {
            **provider.value,
            "name": name,
            "cache_status": "miss_cached" if await self._cache_set(
                key, {**provider.value, "name": name}, 10
            ) else "miss",
            "retry_count": provider.retry_count,
        }
        return result

    async def search_instruments(self, query: str) -> list[dict[str, str]]:
        query = query.strip()
        if not query:
            return InstrumentSearchResults([])
        async with self.session_factory() as session:
            rows = (
                await session.scalars(
                    select(Instrument).where(
                        Instrument.instrument_type == "index",
                        Instrument.is_active.is_(True),
                        (Instrument.code.ilike(f"%{query}%"))
                        | Instrument.name.ilike(f"%{query}%"),
                    )
            )
        ).all()
        results = [self._instrument_dict(row) for row in rows]
        cache_key = f"market:equity-search:{query.casefold()[:80]}"
        equities = await self._cache_get(cache_key)
        retry_count = 0
        provider_error = False
        if equities is None:
            try:
                provider = await self._run_provider("search", query, timeout=25)
                equities = provider.value
                retry_count = provider.retry_count
                await self._cache_set(cache_key, equities, 1800)
            except MarketDataError as exc:
                logger.info("AKShare stock directory search failed (%s)", type(exc).__name__)
                equities = []
                retry_count = exc.retry_count
                provider_error = True
        for item in equities:
            code = item["provider_symbol"]
            exchange = (
                "SSE" if code.startswith(("6", "9"))
                else "BSE" if code.startswith(("4", "8"))
                else "SZSE"
            )
            results.append({
                "code": f"{exchange}:{code}", "name": item["name"],
                "instrument_type": "equity", "provider_symbol": code,
            })
        unique = {item["code"]: item for item in results}
        output = list(unique.values())[:20]
        equities_to_register = [item for item in output if item["instrument_type"] == "equity"]
        if equities_to_register:
            async with self.session_factory() as session:
                for item in equities_to_register:
                    if await session.get(Instrument, item["code"]) is None:
                        exchange = item["code"].split(":", maxsplit=1)[0]
                        session.add(Instrument(
                            code=item["code"], name=item["name"], instrument_type="equity",
                            exchange=exchange, provider_symbol=item["provider_symbol"],
                        ))
                await session.commit()
        return InstrumentSearchResults(output, retry_count, provider_error)

    @staticmethod
    def _instrument_dict(item: Instrument) -> dict[str, str]:
        return {
            "code": item.code, "name": item.name,
            "instrument_type": item.instrument_type, "provider_symbol": item.provider_symbol,
        }

    async def refresh_core_indexes(self) -> int:
        updated = 0
        async with self.session_factory() as session:
            instruments = (
                await session.scalars(
                    select(Instrument).where(Instrument.code.in_(CORE_INDEX_CODES))
                )
            ).all()
            for instrument in instruments:
                try:
                    count, _ = await self._fetch_and_store_index_daily(session, instrument, 30)
                    updated += count
                except MarketDataError:
                    logger.exception("Failed to refresh core index %s", instrument.code)
            await session.commit()
        return updated

    async def _fetch_and_store_index_daily(
        self, session: AsyncSession, instrument: Instrument, lookback_days: int
    ) -> tuple[int, int]:
        end_date = datetime.now(MARKET_TIMEZONE).date()
        start_date = end_date - timedelta(days=lookback_days)
        provider = await self._run_provider(
            "index-daily", instrument.provider_symbol,
            start_date.isoformat(), end_date.isoformat(), timeout=35,
        )
        payload = provider.value
        records = payload.get("records", [])
        if not records:
            raise MarketDataError("指数行情源未返回有效日线记录", retry_count=provider.retry_count)
        statement = mysql_insert(MarketDailyBar).values([
            {
                **record, "instrument_code": instrument.code,
                "adjustment": "none", "source": payload["source"],
            }
            for record in records
        ])
        statement = statement.on_duplicate_key_update(
            open=statement.inserted.open,
            high=statement.inserted.high,
            low=statement.inserted.low,
            close=statement.inserted.close,
            volume=statement.inserted.volume,
            amount=statement.inserted.amount,
            change_pct=statement.inserted.change_pct,
            turnover_rate=statement.inserted.turnover_rate,
            source=statement.inserted.source,
            collected_at=func.now(),
        )
        await session.execute(statement)
        await session.flush()
        return len(records), provider.retry_count

    async def get_company_research(
        self, owner_id: str, symbol: str, dataset: str, limit: int = 20
    ) -> dict[str, Any]:
        if dataset not in RESEARCH_DATASETS:
            raise MarketDataError("不支持的公司研究数据类型")
        limit = max(1, min(limit, 100))
        async with self.session_factory() as session:
            instrument = await self._resolve_instrument(session, symbol, owner_id)
            if instrument.instrument_type != "equity":
                raise MarketDataError("公告、财务、估值、筹码及股东数据只适用于关注个股")
            code = instrument.code
            provider_symbol = instrument.provider_symbol
            name = instrument.name
            state = await session.get(CompanyDatasetState, (code, dataset))
            fresh = state is not None and (
                datetime.now(UTC).replace(tzinfo=None) - state.checked_at
            ).total_seconds() <= 24 * 3600
            cached = await self._read_company_dataset(session, instrument, dataset, limit)
            if fresh:
                cached = cached or {"records": [], "data_as_of": None, "units": {}}
                return self._research_result({
                    "symbol": provider_symbol, "name": name, "dataset": dataset,
                    "source": state.source, "data_as_of": cached["data_as_of"],
                    "cache_status": "database", "records": cached["records"],
                    "units": cached.get("units", {}),
                    "distribution_available": cached.get("distribution_available"),
                }, dataset)

        try:
            provider = await self._run_provider(
                "company-research", provider_symbol, dataset, timeout=90
            )
        except MarketDataError as exc:
            if cached is None:
                raise
            return self._research_result({
                "symbol": provider_symbol, "name": name, "dataset": dataset,
                "source": cached.get("source", "database"),
                "data_as_of": cached.get("data_as_of"),
                "cache_status": "database_stale",
                "records": cached.get("records", []),
                "units": cached.get("units", {}),
                "distribution_available": cached.get("distribution_available"),
                "retry_count": exc.retry_count,
                "warning": f"数据源刷新失败，返回数据库已有记录：{exc}",
            }, dataset)
        written = await self._store_company_dataset(code, dataset, provider.value)
        async with self.session_factory() as session:
            instrument = await session.get(Instrument, code)
            cached = await self._read_company_dataset(session, instrument, dataset, limit)
            if cached is None:
                cached = {"records": [], "data_as_of": None, "units": {}}
        return self._research_result({
            "symbol": provider_symbol, "name": name, "dataset": dataset,
            "source": cached.get("source", "AKShare"), "data_as_of": cached["data_as_of"],
            "cache_status": "database_refreshed" if written else "database_fresh",
            "records": cached["records"], "units": cached.get("units", {}),
            "distribution_available": cached.get("distribution_available"),
            "retry_count": provider.retry_count,
        }, dataset)

    @staticmethod
    def _research_result(result: dict[str, Any], dataset: str) -> dict[str, Any]:
        if dataset == "notices" and any(
            not item.get("content") for item in result.get("records", [])
        ):
            result["warning"] = (
                (result.get("warning", "") + "；")
                if result.get("warning") else ""
            ) + "巨潮公告正文未采集；不能仅凭标题推断公告具体内容。"
        return result

    async def _read_company_dataset(
        self, session: AsyncSession, instrument: Instrument, dataset: str, limit: int
    ) -> dict[str, Any] | None:
        if dataset == "notices":
            rows = (await session.scalars(
                select(CompanyNotice).where(CompanyNotice.instrument_code == instrument.code)
                .order_by(CompanyNotice.disclosure_time.desc(), CompanyNotice.id.desc()).limit(limit)
            )).all()
            values = [{
                "external_id": row.external_id,
                "announcement_date": row.announcement_date.isoformat() if row.announcement_date else None,
                "disclosure_time": _utc_iso(row.disclosure_time),
                "category": row.category, "title": row.title, "url": row.url,
                "content": row.content,
                "content_status": "available" if row.content else "metadata_only",
            } for row in rows]
            return self._dataset_result(rows, values, lambda row: row.announcement_date, "CNINFO")
        if dataset == "financial":
            rows = (await session.scalars(
                select(CompanyFinancialReport).where(CompanyFinancialReport.instrument_code == instrument.code)
                .order_by(CompanyFinancialReport.report_date.desc()).limit(limit * 3)
            )).all()
            values = [{
                "report_type": row.report_type, "report_date": row.report_date.isoformat(),
                "available_on": row.available_on.isoformat() if row.available_on else None,
                "metrics": row.metrics, "source": row.source,
            } for row in rows]
            result = self._dataset_result(
                rows, values, lambda row: row.report_date, "Eastmoney"
            )
            if result:
                result["units"] = {
                    "metrics": (
                        "源字段原始值，采集链路未提供字段级单位且未做换算；"
                        "不可根据数值大小推断币种或单位。"
                    )
                }
            return result
        if dataset == "valuation":
            rows = (await session.scalars(
                select(ValuationSnapshot).where(ValuationSnapshot.instrument_code == instrument.code)
                .order_by(ValuationSnapshot.observed_at.desc()).limit(limit)
            )).all()
            values = [{
                "valuation_date": row.valuation_date.isoformat(),
                "observed_at": _utc_iso(row.observed_at), "metrics": row.metrics,
                "units": row.units, "industry": row.industry,
            } for row in rows]
            result = self._dataset_result(rows, values, lambda row: row.observed_at, "Xueqiu")
            if result:
                result["units"] = rows[0].units
            return result
        if dataset == "chip":
            rows = (await session.scalars(
                select(ChipDistributionSnapshot).where(ChipDistributionSnapshot.instrument_code == instrument.code)
                .order_by(ChipDistributionSnapshot.trade_date.desc()).limit(limit)
            )).all()
            values = [{
                "trade_date": row.trade_date.isoformat(), "profit_ratio": row.profit_ratio,
                "average_cost": row.average_cost, "cost_90_low": row.cost_90_low,
                "cost_90_high": row.cost_90_high, "concentration_90": row.concentration_90,
                "cost_70_low": row.cost_70_low, "cost_70_high": row.cost_70_high,
                "concentration_70": row.concentration_70,
                "price_distribution": row.price_distribution,
                "distribution_available": row.distribution_available,
            } for row in rows]
            result = self._dataset_result(rows, values, lambda row: row.trade_date, "Eastmoney")
            if result:
                result["distribution_available"] = all(row.distribution_available for row in rows)
                result["units"] = {
                    "average_cost": "CNY/share",
                    "cost_90_low": "CNY/share",
                    "cost_90_high": "CNY/share",
                    "cost_70_low": "CNY/share",
                    "cost_70_high": "CNY/share",
                    "profit_ratio": "provider-native scale; not normalized",
                    "concentration_90": "provider-native scale; not normalized",
                    "concentration_70": "provider-native scale; not normalized",
                }
            return result
        if dataset == "fund_flow":
            rows = (await session.scalars(
                select(FundFlowBar).where(FundFlowBar.instrument_code == instrument.code)
                .order_by(FundFlowBar.trade_date.desc()).limit(limit)
            )).all()
            values = [{
                "trade_date": row.trade_date.isoformat(), "metrics": row.metrics, "units": row.units,
            } for row in rows]
            result = self._dataset_result(rows, values, lambda row: row.trade_date, "Eastmoney")
            if result:
                result["units"] = rows[0].units
            return result
        rows = (await session.scalars(
            select(HolderSnapshot).where(HolderSnapshot.instrument_code == instrument.code)
            .order_by(HolderSnapshot.report_date.desc()).limit(limit)
        )).all()
        values = [{
            "report_date": row.report_date.isoformat(),
            "available_on": row.available_on.isoformat() if row.available_on else None,
            "total_holders": row.total_holders, "average_hold_number": row.average_hold_number,
            "top10_hold_ratio": row.top10_hold_ratio, "first_holder_name": row.first_holder_name,
            "first_holder_ratio": row.first_holder_ratio, "concentration_trend": row.concentration_trend,
            "top_holders": row.top_holders,
        } for row in rows]
        return self._dataset_result(
            rows, values, lambda row: row.available_on or row.report_date, "Sina"
        ) | {
            "units": {
                "total_holders": "holders",
                "average_hold_number": "shares/holder (provider-reported)",
                "top10_hold_ratio": "%",
                "first_holder_ratio": "%",
                "top_holders.hold_number": "shares (provider-reported)",
                "top_holders.hold_ratio": "%",
            }
        } if rows else None

    @staticmethod
    def _dataset_result(rows: list[Any], values: list[dict[str, Any]], date_getter, source: str):
        if not rows:
            return None
        data_as_of = max((date_getter(row) for row in rows if date_getter(row)), default=None)
        return {
            "records": list(reversed(values)),
            "data_as_of": _utc_iso(data_as_of) if isinstance(data_as_of, (date, datetime)) else data_as_of,
            "source": source,
        }

    async def _store_company_dataset(self, code: str, dataset: str, payload: dict[str, Any]) -> int:
        now = datetime.now(UTC).replace(tzinfo=None)
        source = "AKShare"
        written = 0
        async with self.session_factory() as session:
            if dataset == "notices":
                for record in payload.get("notices", []):
                    disclosure_time = _utc_naive(record["disclosure_time"])
                    statement = mysql_insert(CompanyNotice).values(
                        instrument_code=code, external_id=record["external_id"],
                        announcement_date=date.fromisoformat(record["announcement_date"]),
                        disclosure_time=disclosure_time, category=record.get("category"),
                        title=record["title"][:1000], url=record.get("url"),
                        content=record.get("content"),
                        source=record.get("source", "CNINFO"),
                    )
                    updates = {
                        "announcement_date": date.fromisoformat(record["announcement_date"]),
                        "disclosure_time": disclosure_time,
                        "title": record["title"][:1000],
                        "url": record.get("url"),
                        "collected_at": func.now(),
                    }
                    if record.get("content"):
                        updates["content"] = record["content"]
                    await session.execute(statement.on_duplicate_key_update(**updates))
                written = len(payload.get("notices", []))
                source = "CNINFO"
            elif dataset == "financial":
                for record in payload.get("reports", []):
                    statement = mysql_insert(CompanyFinancialReport).values(
                        instrument_code=code, report_type=record["report_type"],
                        report_date=date.fromisoformat(record["report_date"]),
                        available_on=date.fromisoformat(record["available_on"]) if record.get("available_on") else None,
                        metrics=record["metrics"], source=record.get("source", "AKShare"),
                    )
                    await session.execute(statement.on_duplicate_key_update(
                        available_on=statement.inserted.available_on,
                        metrics=statement.inserted.metrics, source=statement.inserted.source,
                        collected_at=func.now(),
                    ))
                written = len(payload.get("reports", []))
                source = "Eastmoney report-period statements"
            elif dataset == "valuation":
                snapshot = payload.get("snapshot")
                if snapshot:
                    statement = mysql_insert(ValuationSnapshot).values(
                        instrument_code=code,
                        valuation_date=date.fromisoformat(snapshot["valuation_date"]),
                        observed_at=_utc_naive(snapshot["observed_at"]),
                        metrics=snapshot["metrics"], units=snapshot["units"],
                        industry=snapshot.get("industry"), source="Xueqiu / AKShare",
                    )
                    await session.execute(statement.on_duplicate_key_update(
                        observed_at=statement.inserted.observed_at, metrics=statement.inserted.metrics,
                        units=statement.inserted.units, industry=statement.inserted.industry,
                        collected_at=func.now(),
                    ))
                    written = 1
            elif dataset == "chip":
                for record in payload.get("snapshots", []):
                    values = {
                        **record, "instrument_code": code,
                        "trade_date": date.fromisoformat(record["trade_date"]),
                        "source": "AKShare / Eastmoney",
                    }
                    statement = mysql_insert(ChipDistributionSnapshot).values(**values)
                    await session.execute(statement.on_duplicate_key_update(
                        **{
                            key: statement.inserted[key]
                            for key in values if key not in {"instrument_code", "trade_date"}
                        },
                        collected_at=func.now(),
                    ))
                written = len(payload.get("snapshots", []))
            elif dataset == "fund_flow":
                for record in payload.get("bars", []):
                    statement = mysql_insert(FundFlowBar).values(
                        instrument_code=code, trade_date=date.fromisoformat(record["trade_date"]),
                        metrics=record["metrics"], units=record["units"],
                        source="AKShare / Eastmoney",
                    )
                    await session.execute(statement.on_duplicate_key_update(
                        metrics=statement.inserted.metrics, units=statement.inserted.units,
                        collected_at=func.now(),
                    ))
                written = len(payload.get("bars", []))
            elif dataset == "holders":
                for record in payload.get("snapshots", []):
                    statement = mysql_insert(HolderSnapshot).values(
                        instrument_code=code,
                        report_date=date.fromisoformat(record["report_date"]),
                        available_on=date.fromisoformat(record["available_on"]) if record.get("available_on") else None,
                        total_holders=record.get("total_holders"),
                        average_hold_number=record.get("average_hold_number"),
                        top10_hold_ratio=record.get("top10_hold_ratio"),
                        first_holder_name=record.get("first_holder_name"),
                        first_holder_ratio=record.get("first_holder_ratio"),
                        concentration_trend=None, top_holders=record.get("top_holders"),
                        source="AKShare / Sina",
                    )
                    await session.execute(statement.on_duplicate_key_update(
                        available_on=statement.inserted.available_on,
                        total_holders=statement.inserted.total_holders,
                        average_hold_number=statement.inserted.average_hold_number,
                        top10_hold_ratio=statement.inserted.top10_hold_ratio,
                        first_holder_name=statement.inserted.first_holder_name,
                        first_holder_ratio=statement.inserted.first_holder_ratio,
                        top_holders=statement.inserted.top_holders, collected_at=func.now(),
                    ))
                written = len(payload.get("snapshots", []))
                source = "AKShare / Sina"
            state = await session.get(CompanyDatasetState, (code, dataset))
            if state is None:
                session.add(CompanyDatasetState(
                    instrument_code=code, dataset=dataset, checked_at=now,
                    source=source, record_count=written,
                ))
            else:
                state.checked_at = now
                state.source = source
                state.record_count = written
            await session.commit()
        return written

    async def get_market_overview(self) -> dict[str, Any]:
        async with self.session_factory() as session:
            trade_date = await session.scalar(
                select(func.max(MarketDailyBar.trade_date)).where(
                    MarketDailyBar.instrument_code == "SSE:000001",
                    MarketDailyBar.adjustment == "none",
                )
            )
            fallback_date_source = "SSE:000001 stored daily bars"
            index_refresh_error = None
            if trade_date is None:
                index = await session.get(Instrument, "SSE:000001")
                if index is not None:
                    try:
                        await self._fetch_and_store_index_daily(session, index, 30)
                        await session.commit()
                        trade_date = await session.scalar(
                            select(func.max(MarketDailyBar.trade_date)).where(
                                MarketDailyBar.instrument_code == "SSE:000001",
                                MarketDailyBar.adjustment == "none",
                            )
                        )
                    except MarketDataError as exc:
                        index_refresh_error = exc
            if trade_date is None:
                trade_date = await session.scalar(select(func.max(MarketStatistic.trade_date)))
                fallback_date_source = "latest stored market-statistics date"
            if trade_date is None:
                retry_count = getattr(index_refresh_error, "retry_count", 0)
                raise MarketDataError(
                    "核心指数和市场统计均无可用交易日，暂时无法生成市场概览",
                    retry_count=retry_count,
                )
            row = await session.get(MarketStatistic, trade_date)
        cache_status = "database"
        warning = None
        retry_count = 0
        is_stale = _market_overview_needs_refresh(
            row, datetime.now(UTC).replace(tzinfo=None)
        )
        if is_stale:
            try:
                provider = await self._run_provider("snapshot", timeout=35)
                snapshot_payload = provider.value
                snapshot = snapshot_payload.get("records", [])
                if not snapshot:
                    raise MarketDataError(
                        "市场概览数据源没有返回记录", retry_count=provider.retry_count
                    )
                market_trade_date = self._snapshot_trade_date(snapshot, trade_date)
                if market_trade_date is None:
                    raise MarketDataError(
                        "市场概览缺少可确认的交易日期", retry_count=provider.retry_count
                    )
                has_snapshot_date = self._snapshot_has_trade_date(snapshot)
                trade_date_source = (
                    "Tencent snapshot date field"
                    if has_snapshot_date else fallback_date_source
                )
                limit_statistics = {
                    "limit_up": None,
                    "limit_down": None,
                    "limit_up_source": None,
                    "limit_down_source": None,
                }
                limit_retry_count = 0
                limit_warning = None
                try:
                    limit_provider = await self._run_provider(
                        "limit-statistics", market_trade_date.isoformat(), timeout=35
                    )
                    limit_statistics.update({
                        field: limit_provider.value.get(field)
                        for field in limit_statistics
                    })
                    limit_retry_count = limit_provider.retry_count
                    limit_warning = limit_provider.value.get("warning")
                except MarketDataError as exc:
                    limit_retry_count = exc.retry_count
                    limit_warning = "涨跌停统计数据源暂时不可用，相关字段保持为空。"

                values = {
                    "trade_date": market_trade_date,
                    "trade_date_source": trade_date_source,
                    **self._market_snapshot_statistics(snapshot),
                    **limit_statistics,
                    "source": snapshot_payload["source"],
                }
                async with self.session_factory() as session:
                    statement = mysql_insert(MarketStatistic).values(**values)
                    update_values = {
                        key: statement.inserted[key]
                        for key in values if key != "trade_date"
                    }
                    for field in (
                        "limit_up", "limit_down", "limit_up_source", "limit_down_source"
                    ):
                        if values[field] is None:
                            update_values[field] = func.coalesce(
                                statement.inserted[field], getattr(MarketStatistic, field)
                            )
                    statement = statement.on_duplicate_key_update(
                        **update_values,
                        collected_at=func.now(),
                    )
                    await session.execute(statement)
                    await session.commit()
                    refreshed_row = await session.get(MarketStatistic, market_trade_date)
                    if refreshed_row is None:
                        raise MarketDataError(
                            "市场概览写入后未能重新读取", retry_count=provider.retry_count
                        )
                    row = refreshed_row
                cache_status = "database_refreshed"
                retry_count = provider.retry_count + limit_retry_count
                warning = limit_warning
            except MarketDataError as exc:
                if row is None:
                    raise
                cache_status = "database_stale"
                retry_count = exc.retry_count
                warning = f"市场概览刷新失败，返回数据库已有统计：{exc}"
        if row is None:
            raise MarketDataError("市场概览没有可返回的已保存统计", retry_count=retry_count)
        if row.trade_date_source != "Tencent snapshot date field":
            date_warning = (
                "市场快照未提供交易日期，当前使用已保存的交易日依据归档；"
                "快照所属交易日未能独立确认。"
                if row.trade_date_source else "该市场统计未记录交易日依据，日期未能独立核实。"
            )
            warning = f"{warning}；{date_warning}" if warning else date_warning
        missing_fields = [
            key for key in ("limit_up", "limit_down") if getattr(row, key) is None
        ]
        if missing_fields:
            missing_warning = "涨跌停统计缺失：" + "、".join(missing_fields)
            warning = f"{warning}；{missing_warning}" if warning else missing_warning
        return {
            "trade_date": row.trade_date.isoformat(),
            "trade_date_source": row.trade_date_source,
            "total_stocks": row.total_stocks,
            "advances": row.advances,
            "declines": row.declines,
            "unchanged": row.unchanged,
            "limit_up": row.limit_up,
            "limit_down": row.limit_down,
            "limit_up_source": row.limit_up_source,
            "limit_down_source": row.limit_down_source,
            "total_volume": row.total_volume,
            "total_amount": row.total_amount,
            "source": row.source,
            "units": {
                "total_amount": "CNY (Tencent turnover normalized from 10,000 CNY)"
                if "Tencent" in row.source else "CNY",
                "total_volume": "lot (100 shares)"
                if "Tencent" in row.source else "AKShare-reported lots",
                "limit_up": "stocks",
                "limit_down": "stocks",
            },
            "cache_status": cache_status,
            "retry_count": retry_count,
            "warning": warning,
            "collected_at": _utc_iso(row.collected_at),
            "missing_fields": missing_fields,
        }

    @staticmethod
    def _market_snapshot_statistics(snapshot: list[dict[str, Any]]) -> dict[str, Any]:
        changes = [
            value for record in snapshot
            if (value := MarketDataService._snapshot_number(
                record, "涨跌幅", "涨跌幅(%)", "change_pct"
            )) is not None
        ]
        volumes = [
            value for record in snapshot
            if (value := MarketDataService._snapshot_number(record, "成交量", "volume")) is not None
        ]
        amounts = [
            value for record in snapshot
            if (value := MarketDataService._snapshot_number(record, "成交额", "amount")) is not None
        ]
        return {
            "total_stocks": len(changes),
            "advances": sum(value > 0 for value in changes),
            "declines": sum(value < 0 for value in changes),
            "unchanged": sum(value == 0 for value in changes),
            "total_volume": sum(volumes) if len(volumes) == len(snapshot) else None,
            "total_amount": sum(amounts) if len(amounts) == len(snapshot) else None,
        }

    @staticmethod
    def _snapshot_has_trade_date(snapshot: list[dict[str, Any]]) -> bool:
        return any(record.get("日期") or record.get("date") for record in snapshot)

    @staticmethod
    def _snapshot_trade_date(
        snapshot: list[dict[str, Any]], index_trade_date: date | None
    ) -> date | None:
        dates = []
        for record in snapshot:
            value = record.get("日期") or record.get("date")
            if isinstance(value, datetime):
                market_time = (
                    value.astimezone(MARKET_TIMEZONE) if value.tzinfo else value
                )
                dates.append(market_time.date())
            elif isinstance(value, date):
                dates.append(value)
            elif value:
                text = str(value).strip()
                try:
                    timestamp = datetime.fromisoformat(text)
                except ValueError:
                    try:
                        dates.append(date.fromisoformat(text[:10]))
                    except ValueError:
                        continue
                else:
                    market_time = (
                        timestamp.astimezone(MARKET_TIMEZONE)
                        if timestamp.tzinfo else timestamp
                    )
                    dates.append(market_time.date())
        return max(dates, default=index_trade_date)

    @staticmethod
    def _snapshot_number(record: dict[str, Any], *columns: str) -> float | None:
        for column in columns:
            value = record.get(column)
            if value is not None:
                try:
                    number = float(str(value).replace(",", "").replace("%", ""))
                except (TypeError, ValueError):
                    continue
                if isfinite(number):
                    return number
        return None

    async def add_to_watchlist(self, owner_id: str, provider_symbol: str) -> dict[str, str]:
        provider_symbol = provider_symbol.strip()
        if len(provider_symbol) != 6 or not provider_symbol.isdigit():
            raise MarketDataError("股票代码须为 6 位数字")
        matches = await self.search_instruments(provider_symbol)
        instrument = next(
            (item for item in matches if item["provider_symbol"] == provider_symbol and item["instrument_type"] == "equity"),
            None,
        )
        if instrument is None:
            raise MarketDataError("行情源没有找到该股票")
        async with self.session_factory() as session:
            existing = await session.get(Instrument, instrument["code"])
            if existing is None:
                exchange = instrument["code"].split(":", maxsplit=1)[0]
                existing = Instrument(
                    code=instrument["code"], name=instrument["name"], instrument_type="equity",
                    exchange=exchange, provider_symbol=provider_symbol,
                )
                session.add(existing)
                await session.flush()
            link = await session.scalar(
                select(UserWatchlist).where(
                    UserWatchlist.owner_id == owner_id,
                    UserWatchlist.instrument_code == existing.code,
                )
            )
            if link is None:
                session.add(UserWatchlist(owner_id=owner_id, instrument_code=existing.code))
            await session.commit()
            return self._instrument_dict(existing)

    async def list_watchlist(self, owner_id: str) -> list[dict[str, str]]:
        async with self.session_factory() as session:
            rows = (
                await session.execute(
                    select(Instrument).join(UserWatchlist).where(UserWatchlist.owner_id == owner_id)
                    .order_by(Instrument.name)
                )
            ).scalars().all()
            return [self._instrument_dict(row) for row in rows]

    async def remove_from_watchlist(self, owner_id: str, code: str) -> bool:
        async with self.session_factory() as session:
            link = await session.scalar(
                select(UserWatchlist).where(
                    UserWatchlist.owner_id == owner_id,
                    UserWatchlist.instrument_code == code.upper(),
                )
            )
            if link is None:
                return False
            await session.delete(link)
            await session.commit()
            return True
