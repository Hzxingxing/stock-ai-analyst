"""财务分析模块 - 分析财务数据生成结论"""

from typing import Optional
import pandas as pd


def analyze_profitability(indicators: pd.DataFrame) -> dict:
    """
    分析盈利能力

    Returns:
        盈利能力分析结果
    """
    if indicators.empty:
        return {"status": "数据不足", "details": {}}

    latest = indicators.iloc[0]

    # 获取关键指标
    roe = latest.get("roe") or latest.get("roe_weighted")
    net_margin = latest.get("net_profit_margin")
    gross_margin = latest.get("gross_margin")

    # 处理 NaN 值
    if pd.isna(roe):
        roe = None
    if pd.isna(net_margin):
        net_margin = None
    if pd.isna(gross_margin):
        gross_margin = None

    # 评级标准
    def rate_roe(val):
        if val is None:
            return "N/A"
        val = float(val)
        if val >= 20:
            return "优秀"
        elif val >= 15:
            return "良好"
        elif val >= 10:
            return "一般"
        else:
            return "较差"

    def rate_margin(val):
        if val is None:
            return "N/A"
        val = float(val)
        if val >= 30:
            return "优秀"
        elif val >= 15:
            return "良好"
        elif val >= 5:
            return "一般"
        else:
            return "较差"

    # ROE趋势
    roe_trend = "N/A"
    if len(indicators) >= 4 and "roe" in indicators.columns:
        recent_roe = indicators["roe"].head(4).mean()
        older_roe = indicators["roe"].tail(4).mean() if len(indicators) >= 8 else recent_roe
        if pd.notna(recent_roe) and pd.notna(older_roe):
            if recent_roe > older_roe * 1.1:
                roe_trend = "上升"
            elif recent_roe < older_roe * 0.9:
                roe_trend = "下降"
            else:
                roe_trend = "稳定"

    return {
        "status": rate_roe(roe),
        "details": {
            "roe": f"{float(roe):.2f}%" if roe else "N/A",
            "roe_rating": rate_roe(roe),
            "roe_trend": roe_trend,
            "net_margin": f"{float(net_margin):.2f}%" if net_margin else "N/A",
            "net_margin_rating": rate_margin(net_margin),
            "gross_margin": f"{float(gross_margin):.2f}%" if gross_margin else "N/A",
            "gross_margin_rating": rate_margin(gross_margin),
        }
    }


def analyze_growth(profit: pd.DataFrame, indicators: pd.DataFrame) -> dict:
    """
    分析成长能力

    Returns:
        成长能力分析结果
    """
    if profit.empty:
        return {"status": "数据不足", "details": {}}

    latest = profit.iloc[0]

    revenue_yoy = latest.get("revenue_yoy")
    profit_yoy = latest.get("net_profit_yoy")

    # 从指标表获取增长率
    if indicators is not None and not indicators.empty:
        ind_latest = indicators.iloc[0]
        if revenue_yoy is None:
            revenue_yoy = ind_latest.get("revenue_growth")
        if profit_yoy is None:
            profit_yoy = ind_latest.get("profit_growth")

    def rate_growth(val):
        if val is None:
            return "N/A"
        val = float(val)
        if val >= 30:
            return "高速增长"
        elif val >= 15:
            return "稳健增长"
        elif val >= 0:
            return "低速增长"
        elif val >= -15:
            return "小幅下滑"
        else:
            return "大幅下滑"

    return {
        "status": rate_growth(profit_yoy) if profit_yoy else rate_growth(revenue_yoy),
        "details": {
            "revenue_yoy": f"{float(revenue_yoy):.2f}%" if revenue_yoy else "N/A",
            "revenue_rating": rate_growth(revenue_yoy),
            "profit_yoy": f"{float(profit_yoy):.2f}%" if profit_yoy else "N/A",
            "profit_rating": rate_growth(profit_yoy),
        }
    }


def analyze_financial_health(balance: pd.DataFrame, indicators: pd.DataFrame) -> dict:
    """
    分析财务健康度

    Returns:
        财务健康度分析结果
    """
    if balance.empty and (indicators is None or indicators.empty):
        return {"status": "数据不足", "details": {}}

    # 从资产负债表计算
    debt_ratio = None
    current_ratio = None
    cash = None

    if not balance.empty:
        latest_balance = balance.iloc[0]
        total_assets = latest_balance.get("total_assets")
        total_liab = latest_balance.get("total_liabilities")
        current_assets = latest_balance.get("current_assets")
        current_liab = latest_balance.get("current_liabilities")
        cash = latest_balance.get("cash")

        if total_assets and total_liab:
            debt_ratio = float(total_liab) / float(total_assets) * 100

        if current_assets and current_liab and float(current_liab) > 0:
            current_ratio = float(current_assets) / float(current_liab)

    # 从指标表获取
    if indicators is not None and not indicators.empty:
        ind_latest = indicators.iloc[0]
        if debt_ratio is None:
            debt_ratio = ind_latest.get("debt_ratio")
        if current_ratio is None:
            current_ratio = ind_latest.get("current_ratio")

    def rate_debt(val):
        if val is None:
            return "N/A"
        val = float(val)
        if val <= 30:
            return "优秀"
        elif val <= 50:
            return "良好"
        elif val <= 70:
            return "一般"
        else:
            return "较高"

    def rate_current(val):
        if val is None:
            return "N/A"
        val = float(val)
        if val >= 2:
            return "充裕"
        elif val >= 1.5:
            return "良好"
        elif val >= 1:
            return "一般"
        else:
            return "紧张"

    # 综合评级
    debt_rating = rate_debt(debt_ratio)
    current_rating = rate_current(current_ratio)

    if debt_rating in ["优秀", "良好"] and current_rating in ["充裕", "良好"]:
        status = "健康"
    elif debt_rating in ["较高"] or current_rating in ["紧张"]:
        status = "需关注"
    else:
        status = "一般"

    return {
        "status": status,
        "details": {
            "debt_ratio": f"{float(debt_ratio):.2f}%" if debt_ratio else "N/A",
            "debt_rating": debt_rating,
            "current_ratio": f"{float(current_ratio):.2f}" if current_ratio else "N/A",
            "current_rating": current_rating,
            "cash": cash,
        }
    }


def analyze_cash_flow(cash_flow: pd.DataFrame) -> dict:
    """
    分析现金流状况

    Returns:
        现金流分析结果
    """
    if cash_flow.empty:
        return {"status": "数据不足", "details": {}}

    latest = cash_flow.iloc[0]

    operating = latest.get("cash_from_operating")
    investing = latest.get("cash_from_investing")
    financing = latest.get("cash_from_financing")

    def format_cash(val):
        if val is None:
            return "N/A"
        val = float(val)
        if abs(val) >= 1e8:
            return f"{val/1e8:.2f}亿"
        elif abs(val) >= 1e4:
            return f"{val/1e4:.2f}万"
        return f"{val:.2f}"

    # 判断现金流类型
    if operating and float(operating) > 0:
        if investing and float(investing) < 0:
            if financing and float(financing) < 0:
                cash_type = "成熟期(经营+投资-筹资-)"
                status = "良好"
            else:
                cash_type = "扩张期(经营+投资-筹资+)"
                status = "正常"
        else:
            cash_type = "收缩期(经营+投资+)"
            status = "关注"
    else:
        cash_type = "经营现金流为负"
        status = "警惕"

    return {
        "status": status,
        "details": {
            "operating": format_cash(operating),
            "operating_positive": operating and float(operating) > 0,
            "investing": format_cash(investing),
            "financing": format_cash(financing),
            "cash_type": cash_type,
        }
    }


def run_financial_analysis(financial_data: dict) -> dict:
    """
    运行完整财务分析

    Args:
        financial_data: get_all_financial_data() 返回的数据

    Returns:
        完整财务分析结果
    """
    profit = financial_data.get("profit", pd.DataFrame())
    balance = financial_data.get("balance", pd.DataFrame())
    cash_flow = financial_data.get("cash_flow", pd.DataFrame())
    indicators = financial_data.get("indicators", pd.DataFrame())

    profitability = analyze_profitability(indicators)
    growth = analyze_growth(profit, indicators)
    health = analyze_financial_health(balance, indicators)
    cash = analyze_cash_flow(cash_flow)

    # 综合评分
    scores = []
    score_map = {"优秀": 5, "良好": 4, "健康": 4, "稳健增长": 4, "高速增长": 5,
                 "一般": 3, "正常": 3, "低速增长": 3,
                 "较差": 2, "需关注": 2, "小幅下滑": 2,
                 "警惕": 1, "大幅下滑": 1, "较高": 2, "紧张": 1}

    for analysis in [profitability, growth, health, cash]:
        status = analysis.get("status", "")
        if status in score_map:
            scores.append(score_map[status])

    avg_score = sum(scores) / len(scores) if scores else 0

    if avg_score >= 4:
        overall = "优秀"
    elif avg_score >= 3:
        overall = "良好"
    elif avg_score >= 2:
        overall = "一般"
    else:
        overall = "较差"

    return {
        "profitability": profitability,
        "growth": growth,
        "health": health,
        "cash_flow": cash,
        "overall": overall,
        "score": avg_score
    }
