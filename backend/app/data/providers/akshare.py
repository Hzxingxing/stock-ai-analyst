import json
from datetime import date, datetime, timedelta
from typing import Any
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo

import pandas as pd

MARKET_TIMEZONE = ZoneInfo("Asia/Shanghai")
SINA_EQUITY_DAILY_SOURCE = "AKShare / Sina stock_zh_a_daily"
SINA_INDEX_DAILY_SOURCE = "AKShare / Sina stock_zh_index_daily"
TENCENT_MARKET_SNAPSHOT_SOURCE = "AKShare / Tencent stock_zh_a_spot_tx"
TENCENT_BEIJING_EQUITY_DAILY_SOURCE = "Tencent / appstock newfqkline"
TENCENT_TURNOVER_TO_CNY = 10_000
TENCENT_KLINE_URL = "https://proxy.finance.qq.com/ifzqgtimg/appstock/app/newfqkline/get"


def _number(value: Any) -> float | None:
    if value is None:
        return None
    if pd.isna(value):
        return None
    if isinstance(value, str):
        value = value.strip().replace(",", "").replace("%", "")
        if not value or value in {"-", "--", "None"}:
            return None
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return result if pd.notna(result) else None


def _first_column(frame: pd.DataFrame, *names: str) -> str | None:
    return next((name for name in names if name in frame.columns), None)


def _market_timestamp(value: Any) -> pd.Timestamp | None:
    timestamp = pd.to_datetime(value, errors="coerce")
    if pd.isna(timestamp):
        return None
    return (
        timestamp.tz_localize(MARKET_TIMEZONE)
        if timestamp.tzinfo is None
        else timestamp.tz_convert(MARKET_TIMEZONE)
    )


def normalize_daily_frame(
    frame: pd.DataFrame,
    *,
    volume_scale: float = 1,
    turnover_rate_scale: float = 1,
    derive_change_pct: bool = False,
) -> list[dict[str, Any]]:
    if frame is None or frame.empty:
        return []
    columns = {
        "trade_date": ("日期", "date", "trade_date"),
        "open": ("开盘", "开盘价", "open"),
        "high": ("最高", "最高价", "high"),
        "low": ("最低", "最低价", "low"),
        "close": ("收盘", "收盘价", "close"),
        "volume": ("成交量", "volume"),
        "amount": ("成交额", "amount"),
        "change_pct": ("涨跌幅", "change_pct", "涨跌幅(%)"),
        "turnover_rate": ("换手率", "turnover_rate", "turnover"),
    }
    matched = {key: _first_column(frame, *aliases) for key, aliases in columns.items()}
    if matched["trade_date"] is None:
        raise ValueError("AKShare 日线数据缺少日期列")

    rows = []
    for _, row in frame.iterrows():
        trade_date = pd.to_datetime(row[matched["trade_date"]], errors="coerce")
        if pd.isna(trade_date):
            continue
        normalized = {"trade_date": trade_date.date()}
        for key, column in matched.items():
            if key != "trade_date":
                value = _number(row[column]) if column is not None else None
                if value is not None and key == "volume":
                    value *= volume_scale
                elif value is not None and key == "turnover_rate":
                    value *= turnover_rate_scale
                normalized[key] = value
        rows.append(normalized)
    rows.sort(key=lambda item: item["trade_date"])
    if derive_change_pct:
        previous_close = None
        for row in rows:
            close = row["close"]
            if row["change_pct"] is None and previous_close not in (None, 0) and close is not None:
                row["change_pct"] = (close / previous_close - 1) * 100
            if close is not None:
                previous_close = close
    return rows


def _sina_equity_symbol(provider_symbol: str) -> str:
    if provider_symbol.startswith(("sh", "sz", "bj")):
        return provider_symbol
    if provider_symbol.startswith(("6", "9")):
        return f"sh{provider_symbol}"
    if provider_symbol.startswith(("4", "8")):
        return f"bj{provider_symbol}"
    return f"sz{provider_symbol}"


def _beijing_equity_symbol(provider_symbol: str) -> str | None:
    symbol = provider_symbol.strip().lower()
    if symbol.startswith("bj"):
        return symbol
    if symbol.startswith(("4", "8", "92")):
        return f"bj{symbol}"
    return None


def _fetch_tencent_beijing_daily_frame(
    symbol: str, start_date: date, end_date: date, adjustment: str
) -> pd.DataFrame:
    adjustment_code = {"qfq": "qfq", "hfq": "hfq", "none": ""}[adjustment]
    result_rows = []
    for year in range(start_date.year, end_date.year + 1):
        request_start = max(start_date, date(year, 1, 1))
        request_end = min(end_date, date(year, 12, 31))
        params = {
            "_var": f"kline_day{adjustment_code}{year}",
            "param": (
                f"{symbol},day,{request_start},{request_end},640,{adjustment_code}"
            ),
            "r": "0.8205512681390605",
        }
        request = Request(f"{TENCENT_KLINE_URL}?{urlencode(params)}")
        with urlopen(request, timeout=10) as response:
            body = response.read().decode("utf-8")
        _, separator, json_text = body.partition("=")
        if not separator:
            raise ValueError("Tencent 北京个股日线响应格式异常")
        payload = json.loads(json_text.strip().rstrip(";"))
        if str(payload.get("code")) != "0":
            raise ValueError("Tencent 北京个股日线接口未返回成功状态")
        symbol_data = payload.get("data", {}).get(symbol)
        data_key = {"qfq": "qfqday", "hfq": "hfqday", "none": "day"}[adjustment]
        if symbol_data is None or data_key not in symbol_data:
            raise ValueError(f"Tencent 北京个股日线缺少 {adjustment} 数据")
        for values in symbol_data[data_key]:
            if len(values) < 9:
                raise ValueError("Tencent 北京个股日线记录字段不完整")
            amount = _number(values[8])
            result_rows.append({
                "date": values[0],
                "open": values[1],
                "close": values[2],
                "high": values[3],
                "low": values[4],
                "volume": values[5],
                "turnover_rate": values[7],
                "amount": amount * TENCENT_TURNOVER_TO_CNY if amount is not None else None,
            })
    return pd.DataFrame(result_rows)


def _date_range(
    records: list[dict[str, Any]], start_date: date, end_date: date
) -> list[dict[str, Any]]:
    return [
        record for record in records
        if start_date <= record["trade_date"] <= end_date
    ]


def fetch_daily_bars(
    provider_symbol: str,
    instrument_type: str,
    start_date: date,
    end_date: date,
    adjustment: str,
) -> dict[str, Any]:
    import akshare as ak

    if instrument_type == "index":
        return fetch_index_bars(provider_symbol, start_date, end_date)

    adjustment_code = {"qfq": "qfq", "hfq": "hfq", "none": ""}[adjustment]
    beijing_symbol = _beijing_equity_symbol(provider_symbol)
    if beijing_symbol:
        frame = _fetch_tencent_beijing_daily_frame(
            beijing_symbol, start_date - timedelta(days=14), end_date, adjustment
        )
        records = normalize_daily_frame(frame, derive_change_pct=True)
        return {
            "records": _date_range(records, start_date, end_date),
            "source": TENCENT_BEIJING_EQUITY_DAILY_SOURCE,
            "units": {
                "volume": "lot (Tencent Beijing kline native volume)",
                "amount": "CNY (Tencent turnover normalized from 10,000 CNY)",
                "change_pct": "% (derived from consecutive adjusted closes)",
                "turnover_rate": "%",
            },
        }

    frame = ak.stock_zh_a_daily(
        symbol=_sina_equity_symbol(provider_symbol),
        start_date=(start_date - timedelta(days=14)).strftime("%Y%m%d"),
        end_date=end_date.strftime("%Y%m%d"),
        adjust=adjustment_code,
    )
    records = normalize_daily_frame(
        frame,
        volume_scale=0.01,
        turnover_rate_scale=100,
        derive_change_pct=True,
    )
    return {
        "records": _date_range(records, start_date, end_date),
        "source": SINA_EQUITY_DAILY_SOURCE,
        "units": {
            "volume": "lot (Sina shares converted at 100 shares per lot)",
            "amount": "CNY",
            "change_pct": "% (derived from consecutive adjusted closes)",
            "turnover_rate": "% (Sina fraction converted to percent)",
        },
    }


def fetch_intraday_bars(provider_symbol: str, period: str) -> list[dict[str, Any]]:
    import akshare as ak

    market_now = datetime.now(MARKET_TIMEZONE)
    frame = ak.stock_zh_a_hist_min_em(
        symbol=provider_symbol,
        period=period,
        start_date=f"{market_now.date().isoformat()} 09:30:00",
        end_date=f"{market_now.date().isoformat()} 15:00:00",
        adjust="",
    )
    if frame is None or frame.empty:
        return []
    time_column = _first_column(frame, "时间", "日期", "time", "date")
    if time_column is None:
        raise ValueError("AKShare 分时数据缺少时间列")
    aliases = {
        "open": ("开盘", "open"),
        "high": ("最高", "high"),
        "low": ("最低", "low"),
        "close": ("收盘", "close"),
        "volume": ("成交量", "volume"),
        "amount": ("成交额", "amount"),
    }
    matched = {key: _first_column(frame, *values) for key, values in aliases.items()}
    output = []
    for _, row in frame.tail(2000).iterrows():
        timestamp = _market_timestamp(row[time_column])
        if timestamp is None:
            point_time = str(row[time_column])
        else:
            point_time = timestamp.isoformat()
        point = {"time": point_time}
        for key, column in matched.items():
            point[key] = _number(row[column]) if column else None
        output.append(point)
    return output


def fetch_recent_trades(provider_symbol: str) -> list[dict[str, Any]]:
    import akshare as ak

    frame = ak.stock_intraday_em(symbol=provider_symbol)
    if frame is None or frame.empty:
        return []
    return [
        {str(key): None if pd.isna(value) else (value.item() if hasattr(value, "item") else value)
         for key, value in record.items()}
        for record in frame.tail(1000).to_dict(orient="records")
    ]


def fetch_current_quote(provider_symbol: str) -> dict[str, Any]:
    import akshare as ak

    normalized_symbol = provider_symbol.strip().upper()
    if not normalized_symbol.startswith(("SH", "SZ", "BJ")):
        normalized_symbol = _code_market_prefix(provider_symbol)
    frame = ak.stock_individual_spot_xq(symbol=normalized_symbol)
    if frame is None or frame.empty or not {"item", "value"}.issubset(frame.columns):
        raise ValueError("雪球实时行情缺少 item/value 字段")
    fields = {
        "price": ("现价", "最新价"),
        "previous_close": ("昨收", "前收"),
        "change_pct": ("涨幅", "涨跌幅"),
        "change": ("涨跌", "涨跌额"),
        "open": ("今开", "开盘"),
        "high": ("最高",),
        "low": ("最低",),
        "amount": ("成交额",),
        "volume": ("成交量",),
        "turnover_rate": ("周转率", "换手率"),
        "pe_ttm": ("市盈率(TTM)",),
        "pb": ("市净率",),
    }
    values = {}
    for field, aliases in fields.items():
        matching = frame[frame["item"].isin(aliases)]
        values[field] = _number(matching.iloc[0]["value"]) if not matching.empty else None
    time_rows = frame[frame["item"] == "时间"]
    market_time = str(time_rows.iloc[0]["value"]) if not time_rows.empty else None
    if values["price"] is None:
        raise ValueError("雪球实时行情没有返回有效现价")
    return {
        "symbol": normalized_symbol,
        "observed_at": datetime.now(tz=MARKET_TIMEZONE).isoformat(timespec="seconds"),
        "market_time": market_time,
        "quote": values,
        "source": "Xueqiu / stock_individual_spot_xq",
        "units": {
            "price": "CNY/share or index point",
            "change_pct": "%",
            "turnover_rate": "provider-native scale",
            "amount": "provider-native scale; not normalized",
            "volume": "provider-native scale; not normalized",
        },
    }


def search_equities(query: str) -> list[dict[str, str]]:
    import akshare as ak

    frame = ak.stock_info_a_code_name()
    if frame is None or frame.empty:
        raise ValueError("AKShare 股票目录未返回记录")
    code_column = _first_column(frame, "code", "代码")
    name_column = _first_column(frame, "name", "名称")
    if not code_column or not name_column:
        raise ValueError("AKShare 股票列表字段不完整")
    query = query.strip().lower()
    matches = frame[
        frame[code_column].astype(str).str.lower().str.contains(query, regex=False)
        | frame[name_column].astype(str).str.lower().str.contains(query, regex=False)
    ].head(20)
    return [
        {"provider_symbol": str(row[code_column]), "name": str(row[name_column])}
        for _, row in matches.iterrows()
    ]


def fetch_market_snapshot() -> dict[str, Any]:
    import akshare as ak

    frame = ak.stock_zh_a_spot_tx()
    required_columns = {"code", "name", "zdf", "volume", "turnover"}
    if frame is not None and not frame.empty and not required_columns.issubset(frame.columns):
        raise ValueError("Tencent 市场快照字段不完整")
    records = []
    if frame is not None and not frame.empty:
        for _, row in frame.iterrows():
            turnover = _number(row["turnover"])
            records.append({
                "code": str(row["code"]),
                "name": str(row["name"]),
                "change_pct": _number(row["zdf"]),
                "volume": _number(row["volume"]),
                # Tencent reports turnover in 10,000 CNY; volume is in lots.
                "amount": turnover * TENCENT_TURNOVER_TO_CNY if turnover is not None else None,
            })
    return {
        "records": records,
        "source": TENCENT_MARKET_SNAPSHOT_SOURCE,
        "units": {"volume": "lot (100 shares)", "amount": "CNY"},
    }


def fetch_market_limit_statistics(trade_date: date | str) -> dict[str, Any]:
    """Count Eastmoney's dated limit-up/down pools; an empty successful pool means zero."""
    import akshare as ak

    target = date.fromisoformat(trade_date) if isinstance(trade_date, str) else trade_date
    date_text = target.strftime("%Y%m%d")
    result: dict[str, Any] = {
        "trade_date": target.isoformat(),
        "limit_up": None,
        "limit_down": None,
        "limit_up_source": None,
        "limit_down_source": None,
        "errors": {},
    }
    for field, function, source in (
        ("limit_up", ak.stock_zt_pool_em, "Eastmoney stock_zt_pool_em"),
        ("limit_down", ak.stock_zt_pool_dtgc_em, "Eastmoney stock_zt_pool_dtgc_em"),
    ):
        try:
            frame = function(date=date_text)
            if frame is None:
                raise ValueError("数据源未返回涨跌停列表")
            result[field] = len(frame)
            result[f"{field}_source"] = source
        except Exception as exc:  # noqa: BLE001 - preserve independent field availability
            result["errors"][field] = type(exc).__name__
    if result["errors"]:
        result["warning"] = "涨跌停统计存在缺失，未成功的字段保持为空。"
    return result


def _code_market_prefix(provider_symbol: str) -> str:
    if provider_symbol.startswith(("6", "9")):
        return f"SH{provider_symbol}"
    if provider_symbol.startswith(("4", "8")):
        return f"BJ{provider_symbol}"
    return f"SZ{provider_symbol}"


def fetch_company_research(provider_symbol: str, dataset: str) -> dict[str, Any]:
    import akshare as ak

    if dataset == "financial":
        reports = []
        for report_type, provider_function in (
            ("income", ak.stock_profit_sheet_by_report_em),
            ("balance", ak.stock_balance_sheet_by_report_em),
            ("cash_flow", ak.stock_cash_flow_sheet_by_report_em),
        ):
            frame = provider_function(symbol=_code_market_prefix(provider_symbol))
            if frame is None or frame.empty:
                continue
            report_date_column = next(
                (column for column in ("REPORT_DATE", "REPORT_DATE_NAME", "REPORTDATE", "报告期") if column in frame),
                None,
            )
            available_on_column = next(
                (column for column in ("NOTICE_DATE", "ANN_DATE", "NOTICE_DATE_NAME", "公告日期") if column in frame),
                None,
            )
            if report_date_column is None:
                continue
            for _, row in frame.iterrows():
                report_date = pd.to_datetime(row.get(report_date_column), errors="coerce")
                if pd.isna(report_date):
                    continue
                available_on = (
                    pd.to_datetime(row.get(available_on_column), errors="coerce")
                    if available_on_column
                    else pd.NaT
                )
                metrics = {}
                for key, value in row.items():
                    if key in {report_date_column, available_on_column}:
                        continue
                    if value is None or pd.isna(value):
                        metrics[str(key)] = None
                    elif hasattr(value, "item"):
                        metrics[str(key)] = value.item()
                    else:
                        metrics[str(key)] = value
                reports.append({
                    "report_type": report_type,
                    "report_date": report_date.date().isoformat(),
                    "available_on": available_on.date().isoformat() if pd.notna(available_on) else None,
                    "metrics": metrics,
                    "source": "Eastmoney report-period statements (provider field names retained; values unscaled)",
                })
        return {"reports": reports}

    if dataset == "notices":
        market_now = pd.Timestamp.now(tz=MARKET_TIMEZONE)
        notices = ak.stock_zh_a_disclosure_report_cninfo(
            symbol=provider_symbol,
            market="沪深京",
            start_date=(market_now - pd.Timedelta(days=365 * 3)).strftime("%Y%m%d"),
            end_date=market_now.strftime("%Y%m%d"),
        )
        normalized_notices = []
        if notices is not None and not notices.empty:
            for _, row in notices.iterrows():
                title = str(row.get("公告标题", "")).strip()
                url = str(row.get("公告链接", "")).strip()
                timestamp = _market_timestamp(row.get("公告时间"))
                if timestamp is None or not title:
                    continue
                normalized_notices.append({
                    "external_id": url.rsplit("announcementId=", maxsplit=1)[-1].split("&", 1)[0][:64]
                        if "announcementId=" in url
                        else f"{timestamp.isoformat()}:{title[:48]}",
                    "disclosure_time": timestamp.tz_convert("UTC").isoformat(),
                    "announcement_date": timestamp.date().isoformat(),
                    "title": title,
                    "url": url,
                    "source": "CNINFO",
                })
        return {"notices": normalized_notices}

    if dataset == "chip":
        frame = ak.stock_cyq_em(symbol=provider_symbol)
        snapshots = []
        if frame is not None and not frame.empty:
            for _, row in frame.tail(90).iterrows():
                trade_date = pd.to_datetime(row.get("日期"), errors="coerce")
                if pd.isna(trade_date):
                    continue
                snapshots.append({
                    "trade_date": trade_date.date().isoformat(),
                    "profit_ratio": _number(row.get("获利比例")),
                    "average_cost": _number(row.get("平均成本")),
                    "cost_90_low": _number(row.get("90成本-低")),
                    "cost_90_high": _number(row.get("90成本-高")),
                    "concentration_90": _number(row.get("90集中度")),
                    "cost_70_low": _number(row.get("70成本-低")),
                    "cost_70_high": _number(row.get("70成本-高")),
                    "concentration_70": _number(row.get("70集中度")),
                    "price_distribution": None,
                    "distribution_available": False,
                })
        return {"snapshots": snapshots}

    if dataset == "fund_flow":
        market = (
            "sh" if provider_symbol.startswith(("6", "9"))
            else "bj" if provider_symbol.startswith(("4", "8"))
            else "sz"
        )
        frame = ak.stock_individual_fund_flow(stock=provider_symbol, market=market)
        columns = {
            "收盘价": "close_price", "涨跌幅": "change_pct",
            "主力净流入-净额": "main_net_inflow", "主力净流入-净占比": "main_net_inflow_pct",
            "超大单净流入-净额": "super_large_net_inflow",
            "超大单净流入-净占比": "super_large_net_inflow_pct",
            "大单净流入-净额": "large_net_inflow", "大单净流入-净占比": "large_net_inflow_pct",
            "中单净流入-净额": "medium_net_inflow", "中单净流入-净占比": "medium_net_inflow_pct",
            "小单净流入-净额": "small_net_inflow", "小单净流入-净占比": "small_net_inflow_pct",
        }
        bars = []
        if frame is not None and not frame.empty:
            for _, row in frame.iterrows():
                trade_date = pd.to_datetime(row.get("日期"), errors="coerce")
                if pd.isna(trade_date):
                    continue
                bars.append({
                    "trade_date": trade_date.date().isoformat(),
                    "metrics": {
                        metric: _number(row.get(column)) for column, metric in columns.items()
                    },
                    "units": {
                        "close_price": "CNY/share",
                        "change_pct": "%",
                        "main_net_inflow": "provider-native raw amount; not normalized",
                        "super_large_net_inflow": "provider-native raw amount; not normalized",
                        "large_net_inflow": "provider-native raw amount; not normalized",
                        "medium_net_inflow": "provider-native raw amount; not normalized",
                        "small_net_inflow": "provider-native raw amount; not normalized",
                        "main_net_inflow_pct": "%",
                        "super_large_net_inflow_pct": "%",
                        "large_net_inflow_pct": "%",
                        "medium_net_inflow_pct": "%",
                        "small_net_inflow_pct": "%",
                    },
                })
        return {"bars": bars}

    if dataset == "holders":
        frame = ak.stock_main_stock_holder(stock=provider_symbol)
        periods: dict[str, list[dict[str, Any]]] = {}
        if frame is not None and not frame.empty:
            for _, row in frame.iterrows():
                report_date = pd.to_datetime(row.get("report_date", row.get("截至日期")), errors="coerce")
                if pd.isna(report_date):
                    continue
                announcement = pd.to_datetime(
                    row.get("announce_date", row.get("公告日期")), errors="coerce"
                )
                periods.setdefault(report_date.date().isoformat(), []).append({
                    "rank": _number(row.get("rank", row.get("编号"))),
                    "name": str(row.get("holder_name", row.get("股东名称", ""))),
                    "hold_number": _number(row.get("hold_num", row.get("持股数量"))),
                    "hold_ratio": _number(row.get("hold_ratio", row.get("持股比例"))),
                    "share_type": str(row.get("share_type", row.get("股本性质", ""))),
                    "available_on": announcement.date().isoformat() if pd.notna(announcement) else None,
                    "total_holders": _number(row.get("total_holders", row.get("股东总数"))),
                    "average_hold_number": _number(row.get("avg_hold_num", row.get("平均持股数"))),
                })
        snapshots = []
        for report_date, holders in periods.items():
            snapshots.append({
                "report_date": report_date,
                "available_on": next((row["available_on"] for row in holders if row["available_on"]), None),
                "total_holders": next((row["total_holders"] for row in holders if row["total_holders"] is not None), None),
                "average_hold_number": next((row["average_hold_number"] for row in holders if row["average_hold_number"] is not None), None),
                "top_holders": holders[:10],
                "top10_hold_ratio": sum(row["hold_ratio"] or 0 for row in holders[:10]),
                "first_holder_name": holders[0]["name"] if holders else None,
                "first_holder_ratio": holders[0]["hold_ratio"] if holders else None,
            })
        return {"snapshots": snapshots}

    if dataset == "valuation":
        spot = ak.stock_individual_spot_xq(symbol=_code_market_prefix(provider_symbol))
        valuation_aliases = {
            "pe_ttm": "市盈率(TTM)", "pe_static": "市盈率(静)", "pb": "市净率",
            "total_mv": "资产净值/总市值", "circ_mv": "流通值", "dividend_yield": "股息率(TTM)",
        }
        metrics = {}
        if spot is not None and not spot.empty and "item" in spot and "value" in spot:
            for label, metric in (
                (label, metric) for metric, label in valuation_aliases.items()
            ):
                matching = spot[spot["item"] == label]
                if not matching.empty:
                    metrics[metric] = _number(matching.iloc[0]["value"])
        info = ak.stock_individual_info_em(symbol=provider_symbol)
        industry = None
        if info is not None and not info.empty and {"item", "value"}.issubset(info.columns):
            industry_rows = info[info["item"] == "行业"]
            if not industry_rows.empty:
                industry = str(industry_rows.iloc[0]["value"])
        observed_at_utc = pd.Timestamp.now(tz="UTC")
        now = observed_at_utc.tz_convert(MARKET_TIMEZONE)
        return {"snapshot": {
            "valuation_date": now.date().isoformat(),
            "observed_at": observed_at_utc.tz_localize(None).strftime("%Y-%m-%d %H:%M:%S"),
            "metrics": metrics,
            "units": {
                "pe_ttm": "倍", "pe_static": "倍", "pb": "倍", "dividend_yield": "%",
                "total_mv": "provider-native market-value scale; not normalized",
                "circ_mv": "provider-native market-value scale; not normalized",
            },
            "industry": industry,
        }}

    raise ValueError("unsupported company dataset")


def fetch_index_bars(
    provider_symbol: str, start_date: date, end_date: date
) -> dict[str, Any]:
    import akshare as ak

    frame = ak.stock_zh_index_daily(symbol=provider_symbol)
    records = normalize_daily_frame(
        frame, volume_scale=0.01, derive_change_pct=True
    )
    return {
        "records": _date_range(records, start_date, end_date),
        "source": SINA_INDEX_DAILY_SOURCE,
        "units": {
            "volume": "lot (Sina index shares converted at 100 shares per lot)",
            "amount": "not provided by Sina",
            "change_pct": "% (derived from consecutive closes)",
        },
    }
