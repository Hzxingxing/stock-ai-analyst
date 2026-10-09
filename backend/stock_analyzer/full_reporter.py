"""综合报告生成模块 - 整合技术面、公告、财务数据"""

from datetime import datetime
from typing import List, Optional, Dict
import pandas as pd

from .reporter import format_number


def generate_notice_section(notices: List[dict], classified_notices: Dict[str, List[dict]] = None) -> str:
    """生成公告部分报告"""
    lines = [
        "",
        "=" * 50,
        "【近期重要公告】",
        "-" * 50,
    ]

    if not notices and not classified_notices:
        lines.append("暂无公告数据")
        return "\n".join(lines) + "\n"

    # 如果有分类公告，显示分类统计
    if classified_notices:
        lines.append("公告分类统计:")
        for category, items in classified_notices.items():
            if items:
                lines.append(f"  {category}: {len(items)}条")
        lines.append("")
        lines.append("重要公告摘要:")
        lines.append("-" * 30)

    # 显示最近的重要公告
    for notice in notices[:15]:  # 最多显示15条
        date = notice.get("date", "")
        notice_type = notice.get("type", "")
        title = notice.get("title", "")
        lines.append(f"{date} [{notice_type}] {title}")

    return "\n".join(lines) + "\n"


def generate_financial_table(profit: pd.DataFrame, periods: int = 8) -> str:
    """生成财务数据表格"""
    if profit.empty:
        return """
==================================================
【财务数据概览】
--------------------------------------------------
暂无财务数据
"""

    lines = [
        "",
        "=" * 50,
        "【财务数据概览】(最近8个季度)",
        "-" * 50,
    ]

    # 取最近N期
    df = profit.head(periods)

    # 表头
    headers = []
    for _, row in df.iterrows():
        date = row.get("report_date")
        if pd.notna(date):
            if isinstance(date, str):
                date = pd.to_datetime(date)
            q = (date.month - 1) // 3 + 1
            headers.append(f"{date.year}Q{q}")
        else:
            headers.append("--")

    header_line = "          " + "  ".join(f"{h:>8}" for h in headers)
    lines.append(header_line)

    # 数据行
    def format_value(val):
        if pd.isna(val) or val is None:
            return "N/A"
        val = float(val)
        if abs(val) >= 1e8:
            return f"{val/1e8:.1f}亿"
        elif abs(val) >= 1e4:
            return f"{val/1e4:.1f}万"
        return f"{val:.2f}"

    # 营收
    if "revenue" in df.columns:
        values = [format_value(row.get("revenue")) for _, row in df.iterrows()]
        lines.append("营业收入  " + "  ".join(f"{v:>8}" for v in values))

    # 净利润
    if "net_profit" in df.columns:
        values = [format_value(row.get("net_profit")) for _, row in df.iterrows()]
        lines.append("净利润    " + "  ".join(f"{v:>8}" for v in values))

    # 每股收益
    if "eps" in df.columns:
        values = [f"{float(row.get('eps', 0)):.2f}" if pd.notna(row.get("eps")) else "N/A"
                  for _, row in df.iterrows()]
        lines.append("每股收益  " + "  ".join(f"{v:>8}" for v in values))

    # 同比增长
    if "revenue_yoy" in df.columns:
        values = [f"{float(row.get('revenue_yoy', 0)):.1f}%" if pd.notna(row.get("revenue_yoy")) else "N/A"
                  for _, row in df.iterrows()]
        lines.append("营收增速  " + "  ".join(f"{v:>8}" for v in values))

    # 净利润增速
    if "net_profit_yoy" in df.columns:
        values = [f"{float(row.get('net_profit_yoy', 0)):.1f}%" if pd.notna(row.get("net_profit_yoy")) else "N/A"
                  for _, row in df.iterrows()]
        lines.append("利润增速  " + "  ".join(f"{v:>8}" for v in values))

    return "\n".join(lines) + "\n"


def generate_yearly_summary(profit: pd.DataFrame) -> str:
    """生成年度汇总"""
    if profit.empty:
        return ""

    lines = [
        "",
        "=" * 50,
        "【年度业绩汇总】",
        "-" * 50,
    ]

    # 筛选年报数据 (Q4)
    df = profit.copy()
    df["report_date"] = pd.to_datetime(df["report_date"])
    annual = df[df["report_date"].dt.month == 12].head(3)  # 最近3年年报

    if annual.empty:
        return ""

    def format_value(val):
        if pd.isna(val) or val is None:
            return "N/A"
        val = float(val)
        if abs(val) >= 1e8:
            return f"{val/1e8:.2f}亿"
        elif abs(val) >= 1e4:
            return f"{val/1e4:.2f}万"
        return f"{val:.2f}"

    for _, row in annual.iterrows():
        year = row["report_date"].year
        revenue = format_value(row.get("revenue"))
        net_profit = format_value(row.get("net_profit"))
        eps = f"{float(row.get('eps', 0)):.2f}" if pd.notna(row.get("eps")) else "N/A"
        rev_yoy = f"{float(row.get('revenue_yoy', 0)):+.1f}%" if pd.notna(row.get("revenue_yoy")) else "N/A"
        profit_yoy = f"{float(row.get('net_profit_yoy', 0)):+.1f}%" if pd.notna(row.get("net_profit_yoy")) else "N/A"

        lines.append(f"{year}年: 营收 {revenue}, 净利 {net_profit}, EPS {eps}")
        lines.append(f"       营收增速 {rev_yoy}, 利润增速 {profit_yoy}")

    return "\n".join(lines) + "\n"


def generate_financial_analysis_section(analysis: dict) -> str:
    """生成财务分析部分"""
    lines = [
        "",
        "=" * 50,
        "【财务分析】",
        "-" * 50,
    ]

    # 盈利能力
    prof = analysis.get("profitability", {})
    prof_details = prof.get("details", {})
    lines.append(f"盈利能力: {prof.get('status', 'N/A')}")
    lines.append(f"  ROE: {prof_details.get('roe', 'N/A')} ({prof_details.get('roe_rating', '')}) "
                 f"趋势: {prof_details.get('roe_trend', 'N/A')}")
    lines.append(f"  净利率: {prof_details.get('net_margin', 'N/A')}  "
                 f"毛利率: {prof_details.get('gross_margin', 'N/A')}")

    # 成长能力
    growth = analysis.get("growth", {})
    growth_details = growth.get("details", {})
    lines.append("")
    lines.append(f"成长能力: {growth.get('status', 'N/A')}")
    lines.append(f"  营收增速: {growth_details.get('revenue_yoy', 'N/A')}  "
                 f"利润增速: {growth_details.get('profit_yoy', 'N/A')}")

    # 财务健康
    health = analysis.get("health", {})
    health_details = health.get("details", {})
    lines.append("")
    lines.append(f"财务健康: {health.get('status', 'N/A')}")
    lines.append(f"  资产负债率: {health_details.get('debt_ratio', 'N/A')} ({health_details.get('debt_rating', '')})")
    lines.append(f"  流动比率: {health_details.get('current_ratio', 'N/A')} ({health_details.get('current_rating', '')})")

    # 现金流
    cash = analysis.get("cash_flow", {})
    cash_details = cash.get("details", {})
    lines.append("")
    lines.append(f"现金流: {cash.get('status', 'N/A')}")
    lines.append(f"  经营活动: {cash_details.get('operating', 'N/A')}  "
                 f"投资活动: {cash_details.get('investing', 'N/A')}")
    lines.append(f"  类型: {cash_details.get('cash_type', 'N/A')}")

    return "\n".join(lines) + "\n"


def generate_deep_analysis_section(deep_analysis: dict) -> str:
    """生成深度分析部分报告"""
    lines = [
        "",
        "=" * 50,
        "【深度分析】",
        "-" * 50,
    ]

    # 资本策略分析
    capital = deep_analysis.get("capital_strategy", {})
    lines.append("")
    lines.append("▶ 资本运作策略")
    lines.append(f"  整体策略: {capital.get('overall_strategy', 'N/A')}")

    buyback = capital.get("buyback", {})
    if buyback.get("count", 0) > 0:
        lines.append(f"  回购: {buyback.get('trend', '')} ({buyback.get('count', 0)}次)")
        lines.append(f"        {buyback.get('interpretation', '')}")

    dividend = capital.get("dividend", {})
    if dividend.get("count", 0) > 0:
        lines.append(f"  分红: {dividend.get('trend', '')} ({dividend.get('count', 0)}次)")

    financing = capital.get("financing", {})
    if financing.get("count", 0) > 0:
        lines.append(f"  融资: {financing.get('trend', '')} ({financing.get('count', 0)}次)")

    # 业务扩张分析
    expansion = deep_analysis.get("business_expansion", {})
    lines.append("")
    lines.append("▶ 业务扩张动向")
    lines.append(f"  扩张强度: {expansion.get('expansion_intensity', 'N/A')}")

    directions = expansion.get("expansion_direction", [])
    if directions:
        lines.append(f"  扩张方向: {', '.join(directions)}")

    lines.append(f"  解读: {expansion.get('overall_interpretation', 'N/A')}")

    ma = expansion.get("ma", {})
    if ma.get("count", 0) > 0:
        lines.append(f"  投资并购: {ma.get('count', 0)}次")
        for detail in ma.get("details", [])[:3]:
            lines.append(f"    - {detail}")

    coop = expansion.get("cooperation", {})
    if coop.get("count", 0) > 0:
        lines.append(f"  对外合作: {coop.get('count', 0)}次")

    sub = expansion.get("subsidiary", {})
    if sub.get("count", 0) > 0:
        lines.append(f"  子公司动态: {sub.get('count', 0)}次")

    # 股东动向分析
    shareholder = deep_analysis.get("shareholder_dynamics", {})
    lines.append("")
    lines.append("▶ 股东动向")
    lines.append(f"  综合信号: {shareholder.get('overall_signal', 'N/A')}")

    holdings = shareholder.get("holdings_change", {})
    inc = holdings.get("increase", 0)
    dec = holdings.get("decrease", 0)
    if inc > 0 or dec > 0:
        lines.append(f"  增减持: 增持{inc}次, 减持{dec}次 ({holdings.get('net_direction', '')})")
        lines.append(f"          {holdings.get('interpretation', '')}")

    incentive = shareholder.get("equity_incentive", {})
    if incentive.get("count", 0) > 0:
        lines.append(f"  股权激励: {incentive.get('count', 0)}次 - {incentive.get('interpretation', '')}")

    mgmt = shareholder.get("management_change", {})
    if mgmt.get("count", 0) > 0:
        lines.append(f"  高管变动: {mgmt.get('count', 0)}次 - {mgmt.get('interpretation', '')}")

    # 风险因素
    risk = deep_analysis.get("risk_factors", {})
    lines.append("")
    lines.append("▶ 风险因素")
    lines.append(f"  整体风险: {risk.get('overall_risk', 'N/A')}")

    litigation = risk.get("litigation", {})
    if litigation.get("count", 0) > 0:
        lines.append(f"  诉讼仲裁: {litigation.get('count', 0)}次 (风险等级: {litigation.get('risk_level', '')})")

    penalty = risk.get("penalty", {})
    if penalty.get("count", 0) > 0:
        lines.append(f"  监管处罚: {penalty.get('count', 0)}次 (风险等级: {penalty.get('risk_level', '')})")

    risk_points = risk.get("risk_points", [])
    if risk_points:
        lines.append("  风险提示:")
        for point in risk_points:
            lines.append(f"    ⚠ {point}")

    # 财务趋势
    fin_trends = deep_analysis.get("financial_trends", {})
    lines.append("")
    lines.append("▶ 财务趋势")
    lines.append(f"  财务健康度: {fin_trends.get('financial_health', 'N/A')}")

    if fin_trends.get("revenue_trend"):
        lines.append(f"  营收趋势: {fin_trends.get('revenue_trend', 'N/A')}")
    if fin_trends.get("profit_trend"):
        lines.append(f"  利润趋势: {fin_trends.get('profit_trend', 'N/A')}")
    if fin_trends.get("roe_trend"):
        lines.append(f"  ROE趋势: {fin_trends.get('roe_trend', 'N/A')}")
    if fin_trends.get("cash_flow_trend"):
        lines.append(f"  现金流: {fin_trends.get('cash_flow_trend', 'N/A')}")

    key_insights = fin_trends.get("key_insights", [])
    if key_insights:
        lines.append("  关键发现:")
        for insight in key_insights:
            lines.append(f"    • {insight}")

    return "\n".join(lines) + "\n"


def generate_future_prediction_section(prediction: dict) -> str:
    """生成未来发展预测部分"""
    lines = [
        "",
        "=" * 50,
        "【发展方向预测】",
        "-" * 50,
    ]

    lines.append(f"总体展望: {prediction.get('overall_outlook', 'N/A')}")
    lines.append("")

    if prediction.get("strategic_direction"):
        lines.append(f"战略方向: {prediction.get('strategic_direction')}")

    if prediction.get("growth_outlook"):
        lines.append(f"成长前景: {prediction.get('growth_outlook')}")

    if prediction.get("risk_outlook"):
        lines.append(f"风险展望: {prediction.get('risk_outlook')}")

    # 投资逻辑
    thesis = prediction.get("investment_thesis", [])
    if thesis:
        lines.append("")
        lines.append("投资逻辑:")
        for t in thesis:
            lines.append(f"  ✓ {t}")

    # 关注要点
    watch = prediction.get("watch_points", [])
    if watch:
        lines.append("")
        lines.append("关注要点:")
        for w in watch:
            lines.append(f"  ⚠ {w}")

    return "\n".join(lines) + "\n"


def generate_comprehensive_summary(
    tech_analysis: dict,
    financial_analysis: dict,
    notices: List[dict]
) -> str:
    """生成综合研判"""
    lines = [
        "",
        "=" * 50,
        "【综合研判】",
        "-" * 50,
    ]

    # 技术面判断
    ma = tech_analysis.get("ma", {})
    macd = tech_analysis.get("macd", {})
    tech_status = f"{ma.get('trend', 'N/A')}，{macd.get('signal', 'N/A')}"
    lines.append(f"技术面: {tech_status}")

    # 基本面判断
    overall = financial_analysis.get("overall", "N/A")
    prof_status = financial_analysis.get("profitability", {}).get("status", "")
    growth_status = financial_analysis.get("growth", {}).get("status", "")
    lines.append(f"基本面: {overall} (盈利{prof_status}，{growth_status})")

    # 公告面判断
    if notices:
        # 检查是否有利空公告
        bad_keywords = ["减持", "亏损", "下滑", "违规", "处罚", "诉讼"]
        has_bad_news = any(
            any(kw in n.get("title", "") for kw in bad_keywords)
            for n in notices[:5]
        )
        if has_bad_news:
            notice_status = "近期有负面公告，需关注"
        else:
            notice_status = "无重大利空"
    else:
        notice_status = "公告数据不足"
    lines.append(f"公告面: {notice_status}")

    # 综合建议
    lines.append("")

    # 简单评分逻辑
    bullish = 0
    bearish = 0

    # 技术面
    if ma.get("trend") in ["多头", "强势多头"]:
        bullish += 1
    elif ma.get("trend") in ["空头", "强势空头"]:
        bearish += 1

    if "金叉" in macd.get("signal", ""):
        bullish += 1
    elif "死叉" in macd.get("signal", ""):
        bearish += 1

    # 基本面
    if overall in ["优秀", "良好"]:
        bullish += 2
    elif overall in ["较差"]:
        bearish += 2

    # 公告面
    if has_bad_news if notices else False:
        bearish += 1

    if bullish > bearish + 1:
        suggestion = "技术面和基本面共振向好，可积极关注"
    elif bearish > bullish + 1:
        suggestion = "技术面或基本面存在压力，建议谨慎"
    else:
        suggestion = "多空因素交织，建议观望等待明确信号"

    lines.append(f"建议: {suggestion}")
    lines.append("=" * 50)

    return "\n".join(lines) + "\n"


def generate_market_news_section(market_info: dict) -> str:
    """生成市场资讯部分报告"""
    if not market_info:
        return ""

    lines = [
        "",
        "=" * 50,
        "【市场资讯】",
        "-" * 50,
    ]

    # 新闻情感分析
    sentiment = market_info.get("sentiment_analysis", {})
    score = sentiment.get("sentiment_score", 0)
    pos = sentiment.get("positive_count", 0)
    neg = sentiment.get("negative_count", 0)
    lines.append(f"舆情分析: 正面{pos}条, 负面{neg}条, 情感分数: {score:+d}")

    # 近期新闻
    news = market_info.get("stock_news", [])
    if news:
        lines.append("")
        lines.append("近期新闻:")
        for n in news[:8]:
            date = n.get("date", "")[:10]
            title = n.get("title", "")[:45]
            source = n.get("source", "")
            lines.append(f"  {date} [{source}] {title}")

    # 研究报告
    research = market_info.get("research_reports", [])
    if research:
        lines.append("")
        lines.append("券商研报:")
        for r in research[:5]:
            institution = r.get("institution", "")[:8]
            rating = r.get("rating", "")
            title = r.get("title", "")[:30]
            lines.append(f"  [{institution}] {rating} - {title}")

    # 龙虎榜
    dragon = market_info.get("dragon_tiger", [])
    if dragon:
        lines.append("")
        lines.append(f"龙虎榜: 近期上榜{len(dragon)}次")
        for d in dragon[:3]:
            date = d.get("date", "")
            reason = d.get("reason", "")[:20]
            net = d.get("net_amount", "")
            lines.append(f"  {date} {reason} 净买入: {net}")

    # 大宗交易
    block = market_info.get("block_trades", [])
    if block:
        lines.append("")
        lines.append(f"大宗交易: 近期{len(block)}笔")
        for b in block[:3]:
            date = b.get("date", "")
            amount = b.get("amount", "")
            discount = b.get("discount", "")
            lines.append(f"  {date} 成交{amount} 折溢率{discount}")

    return "\n".join(lines) + "\n"


def generate_investment_highlights_section(notice_analysis: dict) -> str:
    """生成投资亮点部分报告"""
    if not notice_analysis:
        return ""

    inv = notice_analysis.get("investment_analysis", {})
    if not inv:
        return ""

    lines = [
        "",
        "=" * 50,
        "【重大投资动向】",
        "-" * 50,
    ]

    # 基金设立
    funds = inv.get("fund_establishments", [])
    if funds:
        lines.append("基金/合伙企业设立:")
        for f in funds[:5]:
            title = f.get("title", "")[:50]
            amounts = f.get("amounts", [])
            amt_str = ", ".join(amounts) if amounts else ""
            if amt_str:
                lines.append(f"  • {title} ({amt_str})")
            else:
                lines.append(f"  • {title}")

    # 重大交易
    deals = inv.get("significant_deals", [])
    if deals:
        lines.append("")
        lines.append("重大投资/合作:")
        for d in deals[:5]:
            title = d.get("title", "")[:50]
            score = d.get("score", 0)
            partners = d.get("partners", [])
            partner_str = ", ".join(partners) if partners else ""
            if partner_str:
                lines.append(f"  • {title}")
                lines.append(f"    合作方: {partner_str}")
            else:
                lines.append(f"  • {title}")

    # 关键合作方
    partners = inv.get("key_partners", [])
    if partners:
        lines.append("")
        lines.append(f"关键合作方: {', '.join(partners[:5])}")

    # 投资方向
    directions = inv.get("investment_directions", [])
    if directions:
        dir_str = ", ".join([f"{d[0]}({d[1]}次)" for d in directions[:5]])
        lines.append(f"投资方向: {dir_str}")

    # 投资金额估算
    total = inv.get("estimated_total_amount", "")
    if total:
        lines.append(f"投资规模: {total}")

    return "\n".join(lines) + "\n"


def generate_market_intelligence_section(deep_analysis: dict) -> str:
    """生成市场情报分析部分"""
    mi = deep_analysis.get("market_intelligence", {})
    if not mi or not any(mi.values()):
        return ""

    lines = [
        "",
        "=" * 50,
        "【市场情报分析】",
        "-" * 50,
    ]

    if mi.get("news_sentiment"):
        lines.append(f"舆情倾向: {mi.get('news_sentiment')}")

    if mi.get("institutional_view"):
        lines.append(f"机构观点: {mi.get('institutional_view')}")

    if mi.get("market_attention"):
        lines.append(f"市场关注: {mi.get('market_attention')}")

    signals = mi.get("trading_signals", [])
    if signals:
        lines.append(f"交易信号: {'; '.join(signals)}")

    events = mi.get("key_events", [])
    if events:
        lines.append("")
        lines.append("关键事件:")
        for e in events[:5]:
            lines.append(f"  • {e}")

    return "\n".join(lines) + "\n"


def generate_full_report(
    stock_code: str,
    stock_name: str,
    tech_report: str,
    tech_analysis: dict,
    notices: List[dict],
    financial_data: dict,
    financial_analysis: dict,
    years: int = 3,
    classified_notices: Dict[str, List[dict]] = None,
    deep_analysis: dict = None,
    market_info: dict = None,
    notice_analysis: dict = None
) -> str:
    """
    生成完整综合报告

    Args:
        stock_code: 股票代码
        stock_name: 股票名称
        tech_report: 技术分析报告文本
        tech_analysis: 技术分析结果
        notices: 公告列表
        financial_data: 财务数据
        financial_analysis: 财务分析结果
        years: 分析年限
        classified_notices: 分类后的公告
        deep_analysis: 深度分析结果
        market_info: 市场资讯
        notice_analysis: 增强版公告分析

    Returns:
        完整报告文本
    """
    # 组合报告
    report_parts = []

    # 技术分析部分 (现有报告)
    report_parts.append(tech_report)

    # 公告部分
    report_parts.append(generate_notice_section(notices, classified_notices))

    # 重大投资动向（新增）
    if notice_analysis:
        report_parts.append(generate_investment_highlights_section(notice_analysis))

    # 财务数据表格 (显示完整数据)
    profit = financial_data.get("profit", pd.DataFrame())
    report_parts.append(generate_financial_table(profit, periods=12))  # 显示12个季度

    # 年度业绩汇总
    report_parts.append(generate_yearly_summary(profit))

    # 财务分析
    report_parts.append(generate_financial_analysis_section(financial_analysis))

    # 市场资讯（新增）
    if market_info:
        report_parts.append(generate_market_news_section(market_info))

    # 深度分析部分
    if deep_analysis:
        report_parts.append(generate_deep_analysis_section(deep_analysis))

        # 市场情报分析（新增）
        report_parts.append(generate_market_intelligence_section(deep_analysis))

        # 未来发展预测
        future = deep_analysis.get("future_prediction", {})
        if future:
            report_parts.append(generate_future_prediction_section(future))

    # 综合研判
    report_parts.append(generate_comprehensive_summary(
        tech_analysis, financial_analysis, notices
    ))

    # 免责声明
    report_parts.append("""
※ 以上分析仅供参考，不构成投资建议。
※ 股市有风险，投资需谨慎。
""")

    return "".join(report_parts)
