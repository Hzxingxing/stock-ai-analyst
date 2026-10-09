from datetime import date, datetime
from typing import Any
from zoneinfo import ZoneInfo

import pandas as pd

MARKET_TIMEZONE = ZoneInfo("Asia/Shanghai")


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


def normalize_daily_frame(frame: pd.DataFrame) -> list[dict[str, Any]]:
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
        "turnover_rate": ("换手率", "turnover_rate"),
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
                normalized[key] = _number(row[column]) if column is not None else None
        rows.append(normalized)
    return rows


def fetch_daily_bars(
    provider_symbol: str,
    instrument_type: str,
    start_date: date,
    end_date: date,
    adjustment: str,
) -> list[dict[str, Any]]:
    import akshare as ak

    start = start_date.strftime("%Y%m%d")
    end = end_date.strftime("%Y%m%d")
    if instrument_type == "index":
        frame = ak.stock_zh_index_daily_em(
            symbol=provider_symbol, start_date=start, end_date=end
        )
    else:
        adjustment_code = {"qfq": "qfq", "hfq": "hfq", "none": ""}[adjustment]
        frame = ak.stock_zh_a_hist(
            symbol=provider_symbol,
            period="daily",
            start_date=start,
            end_date=end,
            adjust=adjustment_code,
            timeout=20,
        )
    return normalize_daily_frame(frame)


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


def search_equities(query: str) -> list[dict[str, str]]:
    import akshare as ak

    frame = ak.stock_info_a_code_name()
    if frame is None or frame.empty:
        return []
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


def fetch_market_snapshot() -> list[dict[str, Any]]:
    import akshare as ak

    frame = ak.stock_zh_a_spot_em()
    if frame is None or frame.empty:
        return []
    records = []
    for _, row in frame.iterrows():
        record = {}
        for key, value in row.items():
            if value is None or pd.isna(value):
                record[str(key)] = None
            elif hasattr(value, "item"):
                record[str(key)] = value.item()
            else:
                record[str(key)] = value
        records.append(record)
    return records


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


def fetch_index_bars(provider_symbol: str, start_date: date, end_date: date) -> list[dict[str, Any]]:
    import akshare as ak

    frame = ak.stock_zh_index_daily_em(
        symbol=provider_symbol,
        start_date=start_date.strftime("%Y%m%d"),
        end_date=end_date.strftime("%Y%m%d"),
    )
    return normalize_daily_frame(frame)
