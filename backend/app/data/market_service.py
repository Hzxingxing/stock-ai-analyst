import asyncio
import json
import logging
import os
import sys
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
    pass


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

    async def _run_provider(self, *arguments: str, timeout: int = 30) -> Any:
        environment = os.environ.copy()
        old_pythonpath = environment.get("PYTHONPATH", "")
        environment["PYTHONPATH"] = os.pathsep.join(
            path for path in (str(BACKEND_ROOT), old_pythonpath) if path
        )
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
            raise MarketDataError("行情源请求超时") from exc
        except asyncio.CancelledError:
            worker.kill()
            await worker.communicate()
            raise
        if worker.returncode != 0:
            details = (stderr or b"").decode("utf-8", errors="replace")
            logger.warning("AKShare worker failed: %s", details[-2000:])
            raise MarketDataError("行情源暂时不可用")
        try:
            return json.loads(stdout)
        except (json.JSONDecodeError, UnicodeDecodeError) as exc:
            raise MarketDataError("行情源返回格式异常") from exc

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
    ) -> int:
        end_date = datetime.now(MARKET_TIMEZONE).date()
        start_date = end_date - timedelta(days=lookback_days)
        if instrument.instrument_type == "index":
            records = await self._run_provider(
                "index-daily", instrument.provider_symbol,
                start_date.isoformat(), end_date.isoformat(), timeout=35,
            )
            adjustment = "none"
        else:
            records = await self._run_provider(
                "daily", instrument.provider_symbol, instrument.instrument_type,
                start_date.isoformat(), end_date.isoformat(), adjustment, timeout=35,
            )
        if not records:
            return 0
        values = [
            {
                **record,
                "instrument_code": instrument.code,
                "adjustment": adjustment,
                "source": "AKShare",
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
        return len(values)

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
            if available < requested_daily or not fresh:
                fetched = await self._fetch_and_store_daily(
                    session, instrument, effective_adjustment, min(3650, requested_daily * 2)
                )
                await session.commit()
                cache_status = "database_refreshed" if fetched else "database_fresh"

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
        return {
            "symbol": instrument.provider_symbol,
            "name": instrument.name,
            "instrument_type": instrument.instrument_type,
            "period": period,
            "adjustment": effective_adjustment,
            "unit": {
                "price": "index point" if instrument.instrument_type == "index" else "CNY/share",
                "volume": "lot (as reported by AKShare)",
                "amount": "CNY",
                "change_pct": "%",
                "turnover_rate": "%",
            },
            "source": "AKShare + MySQL",
            "data_as_of": latest_date,
            "cache_status": cache_status,
            "bars": records,
        }

    @staticmethod
    def _bar_dict(bar: MarketDailyBar) -> dict[str, Any]:
        return {
            "date": bar.trade_date.isoformat(), "open": bar.open, "high": bar.high,
            "low": bar.low, "close": bar.close, "volume": bar.volume,
            "amount": bar.amount, "change_pct": bar.change_pct,
            "turnover_rate": bar.turnover_rate,
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
            aggregated.append({
                "date": rows[-1]["date"],
                "open": opens[0] if opens else None,
                "high": max(highs) if highs else None,
                "low": min(lows) if lows else None,
                "close": close,
                "volume": sum(row["volume"] or 0 for row in rows),
                "amount": sum(row["amount"] or 0 for row in rows),
                "change_pct": change_pct,
                "turnover_rate": sum(row["turnover_rate"] or 0 for row in rows),
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
        if points is None:
            points = await self._run_provider("minute", code, period, timeout=35)
            ttl = {"1": 15, "5": 30, "15": 60, "30": 120, "60": 180}[period]
            cached = await self._cache_set(key, points, ttl)
            cache_status = "miss_cached" if cached else "miss"
        return {
            "symbol": code, "name": name, "period_minutes": int(period),
            "source": "AKShare", "cache_status": cache_status,
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
        if trades is None:
            try:
                trades = await self._run_provider("ticks", code, timeout=15)
            except MarketDataError as exc:
                raise MarketDataError(f"逐笔数据源不可用，未保存原始成交记录：{exc}") from exc
            cached = await self._cache_set(key, trades, 10)
            cache_status = "miss_cached" if cached else "miss"
        return {
            "symbol": code, "name": name, "source": "AKShare",
            "cache_status": cache_status,
            "retrieved_at": datetime.now(UTC).isoformat(timespec="seconds"),
            "storage_policy": "Redis only; raw trades are not stored in MySQL",
            "trades": trades,
        }

    async def search_instruments(self, query: str) -> list[dict[str, str]]:
        query = query.strip()
        if not query:
            return []
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
        if query.isdigit() and len(query) == 6:
            exchange = (
                "SSE" if query.startswith(("6", "9"))
                else "BSE" if query.startswith(("4", "8"))
                else "SZSE"
            )
            results.append({
                "code": f"{exchange}:{query}", "name": query,
                "instrument_type": "equity", "provider_symbol": query,
            })
        cache_key = f"market:equity-search:{query.casefold()[:80]}"
        equities = await self._cache_get(cache_key)
        if equities is None:
            try:
                equities = await self._run_provider("search", query, timeout=25)
                await self._cache_set(cache_key, equities, 1800)
            except MarketDataError as exc:
                logger.info("AKShare stock directory search failed (%s)", type(exc).__name__)
                equities = []
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
        return output

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
                    updated += await self._fetch_and_store_index_daily(session, instrument, 30)
                except MarketDataError:
                    logger.exception("Failed to refresh core index %s", instrument.code)
            await session.commit()
        return updated

    async def _fetch_and_store_index_daily(
        self, session: AsyncSession, instrument: Instrument, lookback_days: int
    ) -> int:
        end_date = datetime.now(MARKET_TIMEZONE).date()
        start_date = end_date - timedelta(days=lookback_days)
        records = await self._run_provider(
            "index-daily", instrument.provider_symbol,
            start_date.isoformat(), end_date.isoformat(), timeout=35,
        )
        if not records:
            return 0
        statement = mysql_insert(MarketDailyBar).values([
            {
                **record, "instrument_code": instrument.code,
                "adjustment": "none", "source": "AKShare",
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
            source=statement.inserted.source,
            collected_at=func.now(),
        )
        await session.execute(statement)
        await session.flush()
        return len(records)

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
                return {
                    "symbol": provider_symbol, "name": name, "dataset": dataset,
                    "source": state.source, "data_as_of": cached["data_as_of"],
                    "cache_status": "database", "records": cached["records"],
                    "units": cached.get("units", {}),
                    "distribution_available": cached.get("distribution_available"),
                }

        payload = await self._run_provider(
            "company-research", provider_symbol, dataset, timeout=90
        )
        written = await self._store_company_dataset(code, dataset, payload)
        async with self.session_factory() as session:
            instrument = await session.get(Instrument, code)
            cached = await self._read_company_dataset(session, instrument, dataset, limit)
            if cached is None:
                cached = {"records": [], "data_as_of": None, "units": {}}
        return {
            "symbol": provider_symbol, "name": name, "dataset": dataset,
            "source": cached.get("source", "AKShare"), "data_as_of": cached["data_as_of"],
            "cache_status": "database_refreshed" if written else "database_fresh",
            "records": cached["records"], "units": cached.get("units", {}),
            "distribution_available": cached.get("distribution_available"),
        }

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
                        source=record.get("source", "CNINFO"),
                    )
                    await session.execute(statement.on_duplicate_key_update(
                        announcement_date=date.fromisoformat(record["announcement_date"]),
                        disclosure_time=disclosure_time, title=record["title"][:1000],
                        url=record.get("url"), collected_at=func.now(),
                    ))
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
            if trade_date is None:
                index = await session.get(Instrument, "SSE:000001")
                if index is not None:
                    await self._fetch_and_store_index_daily(session, index, 30)
                    await session.commit()
                    trade_date = await session.scalar(
                        select(func.max(MarketDailyBar.trade_date)).where(
                            MarketDailyBar.instrument_code == "SSE:000001",
                            MarketDailyBar.adjustment == "none",
                        )
                    )
            if trade_date is None:
                raise MarketDataError("尚无可确认的核心指数交易日，暂时无法生成市场概览")
            row = await session.get(MarketStatistic, trade_date)
        cache_status = "database"
        is_stale = (
            row is None
            or row.collected_at is None
            or row.collected_at < datetime.now(UTC).replace(tzinfo=None) - timedelta(hours=6)
        )
        if is_stale:
            snapshot = await self._run_provider("snapshot", timeout=35)
            if not snapshot:
                raise MarketDataError("市场概览数据源没有返回记录")
            changes = []
            volumes = []
            amounts = []
            for record in snapshot:
                change = self._snapshot_number(record, "涨跌幅", "涨跌幅(%)", "change_pct")
                volume = self._snapshot_number(record, "成交量", "volume")
                amount = self._snapshot_number(record, "成交额", "amount")
                if change is not None:
                    changes.append(change)
                if volume is not None:
                    volumes.append(volume)
                if amount is not None:
                    amounts.append(amount)
            market_trade_date = self._snapshot_trade_date(snapshot, trade_date)
            if market_trade_date is None:
                raise MarketDataError("市场概览缺少可确认的交易日期")
            values = {
                "trade_date": market_trade_date,
                "total_stocks": len(changes),
                "advances": sum(value > 0 for value in changes),
                "declines": sum(value < 0 for value in changes),
                "unchanged": sum(value == 0 for value in changes),
                "limit_up": None,
                "limit_down": None,
                "total_volume": sum(volumes),
                "total_amount": sum(amounts),
                "source": "AKShare stock_zh_a_spot_em",
            }
            async with self.session_factory() as session:
                statement = mysql_insert(MarketStatistic).values(**values)
                statement = statement.on_duplicate_key_update(
                    **{key: statement.inserted[key] for key in values if key != "trade_date"},
                    collected_at=func.now(),
                )
                await session.execute(statement)
                await session.commit()
                row = await session.get(MarketStatistic, market_trade_date)
            cache_status = "database_refreshed"
        return {
            "trade_date": row.trade_date.isoformat(),
            "total_stocks": row.total_stocks,
            "advances": row.advances,
            "declines": row.declines,
            "unchanged": row.unchanged,
            "limit_up": row.limit_up,
            "limit_down": row.limit_down,
            "total_volume": row.total_volume,
            "total_amount": row.total_amount,
            "source": row.source,
            "units": {"total_amount": "CNY", "total_volume": "AKShare-reported lots"},
            "cache_status": cache_status,
            "collected_at": _utc_iso(row.collected_at),
        }

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
