"""深度分析模块 - 综合分析公司意图和发展方向"""

from typing import List, Dict, Optional
import pandas as pd
from datetime import datetime, timedelta


def analyze_capital_strategy(notices: Dict[str, List[dict]], financial_data: dict) -> dict:
    """
    分析公司资本运作策略

    Args:
        notices: 分类后的公告
        financial_data: 财务数据

    Returns:
        资本策略分析结果
    """
    analysis = {
        "buyback": {"count": 0, "trend": "", "interpretation": ""},
        "dividend": {"count": 0, "trend": "", "interpretation": ""},
        "financing": {"count": 0, "trend": "", "interpretation": ""},
        "overall_strategy": ""
    }

    # 回购分析
    buyback_notices = notices.get("股份回购", [])
    analysis["buyback"]["count"] = len(buyback_notices)

    if len(buyback_notices) >= 3:
        analysis["buyback"]["trend"] = "频繁回购"
        analysis["buyback"]["interpretation"] = "公司认为股价被低估，通过回购提振市场信心"
    elif len(buyback_notices) >= 1:
        analysis["buyback"]["trend"] = "有回购动作"
        analysis["buyback"]["interpretation"] = "公司对股价有一定支撑意愿"
    else:
        analysis["buyback"]["trend"] = "无回购"
        analysis["buyback"]["interpretation"] = "公司未进行股份回购"

    # 分红分析
    dividend_notices = notices.get("分红送转", [])
    analysis["dividend"]["count"] = len(dividend_notices)

    if len(dividend_notices) >= 3:
        analysis["dividend"]["trend"] = "持续分红"
        analysis["dividend"]["interpretation"] = "公司重视股东回报，现金流充裕"
    elif len(dividend_notices) >= 1:
        analysis["dividend"]["trend"] = "有分红"
        analysis["dividend"]["interpretation"] = "公司有一定的股东回报意识"
    else:
        analysis["dividend"]["trend"] = "无分红记录"
        analysis["dividend"]["interpretation"] = "可能处于成长期或现金流紧张"

    # 融资分析
    financing_notices = notices.get("融资", [])
    analysis["financing"]["count"] = len(financing_notices)

    if len(financing_notices) >= 3:
        analysis["financing"]["trend"] = "频繁融资"
        analysis["financing"]["interpretation"] = "公司资金需求大，可能处于快速扩张期或现金流压力"
    elif len(financing_notices) >= 1:
        analysis["financing"]["trend"] = "有融资动作"
        analysis["financing"]["interpretation"] = "公司有外部资金需求"
    else:
        analysis["financing"]["trend"] = "无融资"
        analysis["financing"]["interpretation"] = "公司资金自给自足"

    # 综合资本策略判断
    if analysis["buyback"]["count"] >= 2 and analysis["dividend"]["count"] >= 2:
        analysis["overall_strategy"] = "股东回报型：公司重视股东回报，通过回购和分红回馈投资者"
    elif analysis["financing"]["count"] >= 2 and analysis["buyback"]["count"] == 0:
        analysis["overall_strategy"] = "资本扩张型：公司积极融资扩张，处于快速发展期"
    elif analysis["buyback"]["count"] >= 2 and analysis["financing"]["count"] == 0:
        analysis["overall_strategy"] = "价值回归型：公司认为股价低估，积极回购提振市值"
    elif analysis["dividend"]["count"] >= 2:
        analysis["overall_strategy"] = "稳健分红型：公司经营稳定，持续回报股东"
    else:
        analysis["overall_strategy"] = "观望型：公司在资本运作上较为保守"

    return analysis


def analyze_business_expansion(notices: Dict[str, List[dict]]) -> dict:
    """
    分析公司业务扩张动向

    Args:
        notices: 分类后的公告

    Returns:
        业务扩张分析结果
    """
    analysis = {
        "ma": {"count": 0, "details": [], "interpretation": ""},
        "cooperation": {"count": 0, "details": [], "interpretation": ""},
        "subsidiary": {"count": 0, "details": [], "interpretation": ""},
        "expansion_direction": [],
        "expansion_intensity": "",
        "overall_interpretation": ""
    }

    # 投资并购分析
    ma_notices = notices.get("投资并购", [])
    analysis["ma"]["count"] = len(ma_notices)
    analysis["ma"]["details"] = [n["title"][:50] for n in ma_notices[:5]]

    if len(ma_notices) >= 5:
        analysis["ma"]["interpretation"] = "公司积极进行并购扩张，寻求外延式增长"
    elif len(ma_notices) >= 2:
        analysis["ma"]["interpretation"] = "公司有选择性进行并购"
    else:
        analysis["ma"]["interpretation"] = "公司并购活动较少"

    # 对外合作分析
    coop_notices = notices.get("对外合作", [])
    analysis["cooperation"]["count"] = len(coop_notices)
    analysis["cooperation"]["details"] = [n["title"][:50] for n in coop_notices[:5]]

    if len(coop_notices) >= 5:
        analysis["cooperation"]["interpretation"] = "公司积极拓展合作伙伴，构建生态体系"
    elif len(coop_notices) >= 2:
        analysis["cooperation"]["interpretation"] = "公司有一定的对外合作"
    else:
        analysis["cooperation"]["interpretation"] = "公司对外合作较少"

    # 子公司分析
    sub_notices = notices.get("子公司", [])
    analysis["subsidiary"]["count"] = len(sub_notices)
    analysis["subsidiary"]["details"] = [n["title"][:50] for n in sub_notices[:5]]

    if len(sub_notices) >= 5:
        analysis["subsidiary"]["interpretation"] = "公司频繁设立/调整子公司，业务架构活跃"
    elif len(sub_notices) >= 2:
        analysis["subsidiary"]["interpretation"] = "公司有一定的子公司运营调整"
    else:
        analysis["subsidiary"]["interpretation"] = "公司组织架构相对稳定"

    # 分析扩张方向
    all_expansion = ma_notices + coop_notices + sub_notices
    keywords_map = {
        "新能源": "新能源领域",
        "智能": "智能化/AI领域",
        "数字": "数字化领域",
        "海外": "海外市场",
        "出海": "海外市场",
        "医疗": "医疗健康领域",
        "半导体": "半导体/芯片领域",
        "芯片": "半导体/芯片领域",
        "消费": "消费领域",
        "金融": "金融领域",
        "科技": "科技领域",
        "互联网": "互联网领域",
        "地产": "房地产领域",
        "物流": "物流领域",
        "电商": "电商领域"
    }

    direction_counts = {}
    for notice in all_expansion:
        title = notice.get("title", "")
        for kw, direction in keywords_map.items():
            if kw in title:
                direction_counts[direction] = direction_counts.get(direction, 0) + 1

    # 排序取前3个方向
    sorted_directions = sorted(direction_counts.items(), key=lambda x: x[1], reverse=True)
    analysis["expansion_direction"] = [d[0] for d in sorted_directions[:3]]

    # 扩张强度评估
    total_expansion = len(all_expansion)
    if total_expansion >= 15:
        analysis["expansion_intensity"] = "高强度扩张"
    elif total_expansion >= 8:
        analysis["expansion_intensity"] = "中等强度扩张"
    elif total_expansion >= 3:
        analysis["expansion_intensity"] = "低强度扩张"
    else:
        analysis["expansion_intensity"] = "保守/收缩"

    # 综合解读
    if total_expansion >= 10:
        direction_str = "、".join(analysis["expansion_direction"]) if analysis["expansion_direction"] else "多个领域"
        analysis["overall_interpretation"] = f"公司处于积极扩张期，主要方向为{direction_str}"
    elif total_expansion >= 5:
        analysis["overall_interpretation"] = "公司有选择性地进行业务拓展"
    else:
        analysis["overall_interpretation"] = "公司业务扩张较为保守，专注主业"

    return analysis


def analyze_shareholder_dynamics(notices: Dict[str, List[dict]]) -> dict:
    """
    分析股东动向

    Args:
        notices: 分类后的公告

    Returns:
        股东动向分析结果
    """
    analysis = {
        "holdings_change": {
            "increase": 0,
            "decrease": 0,
            "net_direction": "",
            "interpretation": ""
        },
        "equity_incentive": {
            "count": 0,
            "interpretation": ""
        },
        "management_change": {
            "count": 0,
            "interpretation": ""
        },
        "overall_signal": ""
    }

    # 增减持分析
    holdings_notices = notices.get("增减持", [])
    for notice in holdings_notices:
        title = notice.get("title", "")
        if "增持" in title:
            analysis["holdings_change"]["increase"] += 1
        if "减持" in title:
            analysis["holdings_change"]["decrease"] += 1

    increase = analysis["holdings_change"]["increase"]
    decrease = analysis["holdings_change"]["decrease"]

    if increase > decrease * 1.5:
        analysis["holdings_change"]["net_direction"] = "净增持"
        analysis["holdings_change"]["interpretation"] = "股东/高管看好公司前景，持续增持"
    elif decrease > increase * 1.5:
        analysis["holdings_change"]["net_direction"] = "净减持"
        analysis["holdings_change"]["interpretation"] = "股东/高管减持较多，需关注减持原因"
    elif increase > 0 or decrease > 0:
        analysis["holdings_change"]["net_direction"] = "增减持平衡"
        analysis["holdings_change"]["interpretation"] = "股东增减持较为均衡"
    else:
        analysis["holdings_change"]["net_direction"] = "无明显变动"
        analysis["holdings_change"]["interpretation"] = "股东持股相对稳定"

    # 股权激励分析
    incentive_notices = notices.get("股权激励", [])
    analysis["equity_incentive"]["count"] = len(incentive_notices)

    if len(incentive_notices) >= 3:
        analysis["equity_incentive"]["interpretation"] = "公司重视激励机制，员工利益与公司绑定紧密"
    elif len(incentive_notices) >= 1:
        analysis["equity_incentive"]["interpretation"] = "公司有股权激励计划"
    else:
        analysis["equity_incentive"]["interpretation"] = "暂无股权激励信息"

    # 高管变动分析
    mgmt_notices = notices.get("高管变动", [])
    analysis["management_change"]["count"] = len(mgmt_notices)

    if len(mgmt_notices) >= 5:
        analysis["management_change"]["interpretation"] = "高管变动频繁，管理层不稳定，需关注"
    elif len(mgmt_notices) >= 2:
        analysis["management_change"]["interpretation"] = "有一定高管变动"
    else:
        analysis["management_change"]["interpretation"] = "管理层相对稳定"

    # 综合股东信号
    if analysis["holdings_change"]["net_direction"] == "净增持" and len(incentive_notices) >= 1:
        analysis["overall_signal"] = "积极信号：股东增持叠加股权激励，利益一致"
    elif analysis["holdings_change"]["net_direction"] == "净减持" and len(mgmt_notices) >= 3:
        analysis["overall_signal"] = "警示信号：股东减持叠加高管变动，需谨慎"
    elif analysis["holdings_change"]["net_direction"] == "净增持":
        analysis["overall_signal"] = "正面信号：股东看好公司前景"
    elif analysis["holdings_change"]["net_direction"] == "净减持":
        analysis["overall_signal"] = "关注信号：股东减持，关注原因"
    else:
        analysis["overall_signal"] = "中性信号：股东动向无明显倾向"

    return analysis


def analyze_risk_factors(notices: Dict[str, List[dict]]) -> dict:
    """
    分析风险因素

    Args:
        notices: 分类后的公告

    Returns:
        风险因素分析结果
    """
    analysis = {
        "litigation": {"count": 0, "details": [], "risk_level": ""},
        "penalty": {"count": 0, "details": [], "risk_level": ""},
        "overall_risk": "",
        "risk_points": []
    }

    # 诉讼仲裁分析
    litigation_notices = notices.get("诉讼仲裁", [])
    analysis["litigation"]["count"] = len(litigation_notices)
    analysis["litigation"]["details"] = [n["title"][:50] for n in litigation_notices[:5]]

    if len(litigation_notices) >= 5:
        analysis["litigation"]["risk_level"] = "高风险"
    elif len(litigation_notices) >= 2:
        analysis["litigation"]["risk_level"] = "中风险"
    elif len(litigation_notices) >= 1:
        analysis["litigation"]["risk_level"] = "低风险"
    else:
        analysis["litigation"]["risk_level"] = "无风险"

    # 处罚分析
    penalty_notices = notices.get("处罚", [])
    analysis["penalty"]["count"] = len(penalty_notices)
    analysis["penalty"]["details"] = [n["title"][:50] for n in penalty_notices[:5]]

    if len(penalty_notices) >= 3:
        analysis["penalty"]["risk_level"] = "高风险"
    elif len(penalty_notices) >= 1:
        analysis["penalty"]["risk_level"] = "中风险"
    else:
        analysis["penalty"]["risk_level"] = "无风险"

    # 综合风险评估
    total_risk_count = len(litigation_notices) + len(penalty_notices)

    if total_risk_count >= 8:
        analysis["overall_risk"] = "高风险"
        analysis["risk_points"].append("诉讼/处罚事项较多，合规风险较高")
    elif total_risk_count >= 3:
        analysis["overall_risk"] = "中等风险"
        analysis["risk_points"].append("存在一定诉讼/处罚记录，需持续关注")
    elif total_risk_count >= 1:
        analysis["overall_risk"] = "低风险"
        analysis["risk_points"].append("有少量诉讼/处罚，整体可控")
    else:
        analysis["overall_risk"] = "低风险"

    # 检查其他风险信号
    holdings = notices.get("增减持", [])
    decrease_count = sum(1 for n in holdings if "减持" in n.get("title", ""))
    if decrease_count >= 5:
        analysis["risk_points"].append(f"股东减持次数较多({decrease_count}次)，需关注")

    mgmt = notices.get("高管变动", [])
    if len(mgmt) >= 5:
        analysis["risk_points"].append(f"高管变动频繁({len(mgmt)}次)，管理层不稳定")

    return analysis


def analyze_financial_trends(financial_data: dict) -> dict:
    """
    分析财务趋势

    Args:
        financial_data: 财务数据

    Returns:
        财务趋势分析结果
    """
    analysis = {
        "revenue_trend": "",
        "profit_trend": "",
        "roe_trend": "",
        "debt_trend": "",
        "cash_flow_trend": "",
        "financial_health": "",
        "key_insights": []
    }

    profit = financial_data.get("profit", pd.DataFrame())
    indicators = financial_data.get("indicators", pd.DataFrame())
    cash_flow = financial_data.get("cash_flow", pd.DataFrame())

    if profit.empty:
        analysis["financial_health"] = "数据不足"
        return analysis

    # 营收趋势分析 (比较最近4季度与之前4季度)
    if len(profit) >= 8 and "revenue" in profit.columns:
        recent_revenue = profit["revenue"].head(4).mean()
        older_revenue = profit["revenue"].iloc[4:8].mean()
        if pd.notna(recent_revenue) and pd.notna(older_revenue) and older_revenue > 0:
            change = (recent_revenue - older_revenue) / older_revenue * 100
            if change > 15:
                analysis["revenue_trend"] = f"快速增长(+{change:.1f}%)"
                analysis["key_insights"].append("营收保持快速增长态势")
            elif change > 5:
                analysis["revenue_trend"] = f"稳健增长(+{change:.1f}%)"
            elif change > -5:
                analysis["revenue_trend"] = f"基本持平({change:+.1f}%)"
            elif change > -15:
                analysis["revenue_trend"] = f"小幅下滑({change:.1f}%)"
                analysis["key_insights"].append("营收出现下滑，需关注")
            else:
                analysis["revenue_trend"] = f"大幅下滑({change:.1f}%)"
                analysis["key_insights"].append("营收大幅下滑，业绩承压")

    # 净利润趋势分析
    if len(profit) >= 8 and "net_profit" in profit.columns:
        recent_profit = profit["net_profit"].head(4).mean()
        older_profit = profit["net_profit"].iloc[4:8].mean()
        if pd.notna(recent_profit) and pd.notna(older_profit) and older_profit > 0:
            change = (recent_profit - older_profit) / older_profit * 100
            if change > 20:
                analysis["profit_trend"] = f"高速增长(+{change:.1f}%)"
                analysis["key_insights"].append("盈利能力持续提升")
            elif change > 5:
                analysis["profit_trend"] = f"稳健增长(+{change:.1f}%)"
            elif change > -5:
                analysis["profit_trend"] = f"基本持平({change:+.1f}%)"
            elif change > -20:
                analysis["profit_trend"] = f"利润下滑({change:.1f}%)"
                analysis["key_insights"].append("利润出现下滑")
            else:
                analysis["profit_trend"] = f"利润大幅下滑({change:.1f}%)"
                analysis["key_insights"].append("利润大幅下滑，需警惕")

    # ROE趋势分析
    if not indicators.empty and "roe" in indicators.columns:
        roe_values = indicators["roe"].dropna()
        if len(roe_values) >= 4:
            recent_roe = roe_values.head(2).mean()
            older_roe = roe_values.iloc[2:4].mean()
            if pd.notna(recent_roe) and pd.notna(older_roe):
                if recent_roe > 15 and recent_roe > older_roe:
                    analysis["roe_trend"] = f"优秀且上升({recent_roe:.1f}%)"
                    analysis["key_insights"].append("ROE表现优秀，盈利质量高")
                elif recent_roe > 10:
                    analysis["roe_trend"] = f"良好({recent_roe:.1f}%)"
                elif recent_roe > 5:
                    analysis["roe_trend"] = f"一般({recent_roe:.1f}%)"
                else:
                    analysis["roe_trend"] = f"较低({recent_roe:.1f}%)"
                    analysis["key_insights"].append("ROE偏低，盈利效率需改善")

    # 现金流分析
    if not cash_flow.empty and "cash_from_operating" in cash_flow.columns:
        recent_cf = cash_flow["cash_from_operating"].head(4)
        positive_count = (recent_cf > 0).sum()
        if positive_count == 4:
            analysis["cash_flow_trend"] = "经营现金流持续为正"
            analysis["key_insights"].append("经营现金流健康")
        elif positive_count >= 2:
            analysis["cash_flow_trend"] = "经营现金流波动"
        else:
            analysis["cash_flow_trend"] = "经营现金流承压"
            analysis["key_insights"].append("经营现金流为负，需关注")

    # 综合财务健康度
    positive_signals = 0
    negative_signals = 0

    if "增长" in analysis.get("revenue_trend", ""):
        positive_signals += 1
    if "下滑" in analysis.get("revenue_trend", ""):
        negative_signals += 1

    if "增长" in analysis.get("profit_trend", ""):
        positive_signals += 1
    if "下滑" in analysis.get("profit_trend", ""):
        negative_signals += 1

    if "优秀" in analysis.get("roe_trend", "") or "良好" in analysis.get("roe_trend", ""):
        positive_signals += 1
    if "较低" in analysis.get("roe_trend", ""):
        negative_signals += 1

    if "持续为正" in analysis.get("cash_flow_trend", ""):
        positive_signals += 1
    if "承压" in analysis.get("cash_flow_trend", ""):
        negative_signals += 1

    if positive_signals >= 3:
        analysis["financial_health"] = "优秀"
    elif positive_signals >= 2 and negative_signals == 0:
        analysis["financial_health"] = "良好"
    elif negative_signals >= 2:
        analysis["financial_health"] = "需关注"
    else:
        analysis["financial_health"] = "一般"

    return analysis


def predict_future_direction(
    capital_analysis: dict,
    expansion_analysis: dict,
    shareholder_analysis: dict,
    financial_analysis: dict
) -> dict:
    """
    预测公司未来发展方向

    Args:
        capital_analysis: 资本策略分析
        expansion_analysis: 业务扩张分析
        shareholder_analysis: 股东动向分析
        financial_analysis: 财务趋势分析

    Returns:
        未来发展预测
    """
    prediction = {
        "strategic_direction": "",
        "growth_outlook": "",
        "risk_outlook": "",
        "investment_thesis": [],
        "watch_points": [],
        "overall_outlook": ""
    }

    # 战略方向判断
    expansion_intensity = expansion_analysis.get("expansion_intensity", "")
    expansion_directions = expansion_analysis.get("expansion_direction", [])
    capital_strategy = capital_analysis.get("overall_strategy", "")

    if "高强度" in expansion_intensity:
        if expansion_directions:
            prediction["strategic_direction"] = f"积极扩张，重点布局{', '.join(expansion_directions[:2])}"
        else:
            prediction["strategic_direction"] = "积极扩张，多元化发展"
    elif "中等强度" in expansion_intensity:
        prediction["strategic_direction"] = "稳健扩张，有选择性发展新业务"
    else:
        if "股东回报" in capital_strategy or "分红" in capital_strategy:
            prediction["strategic_direction"] = "聚焦主业，重视股东回报"
        else:
            prediction["strategic_direction"] = "保守发展，专注现有业务"

    # 成长前景判断
    financial_health = financial_analysis.get("financial_health", "")
    revenue_trend = financial_analysis.get("revenue_trend", "")
    profit_trend = financial_analysis.get("profit_trend", "")

    if "优秀" in financial_health or "良好" in financial_health:
        if "增长" in revenue_trend and "增长" in profit_trend:
            prediction["growth_outlook"] = "成长前景乐观，业绩有望持续增长"
        else:
            prediction["growth_outlook"] = "基本面稳健，成长性一般"
    elif "需关注" in financial_health:
        prediction["growth_outlook"] = "成长承压，需观察业绩拐点"
    else:
        prediction["growth_outlook"] = "成长前景中性"

    # 风险展望
    shareholder_signal = shareholder_analysis.get("overall_signal", "")
    mgmt_changes = shareholder_analysis.get("management_change", {}).get("count", 0)

    if "警示" in shareholder_signal or mgmt_changes >= 5:
        prediction["risk_outlook"] = "风险偏高，股东减持/管理层不稳定"
    elif "积极" in shareholder_signal or "正面" in shareholder_signal:
        prediction["risk_outlook"] = "风险可控，股东信心较强"
    else:
        prediction["risk_outlook"] = "风险中性"

    # 投资逻辑
    if "优秀" in financial_health:
        prediction["investment_thesis"].append("财务基本面优秀，具备长期投资价值")
    if "净增持" in shareholder_analysis.get("holdings_change", {}).get("net_direction", ""):
        prediction["investment_thesis"].append("股东增持彰显信心")
    if expansion_directions:
        prediction["investment_thesis"].append(f"积极布局{expansion_directions[0]}，打开成长空间")
    if "回购" in capital_strategy or capital_analysis.get("buyback", {}).get("count", 0) >= 2:
        prediction["investment_thesis"].append("回购计划支撑股价")

    # 关注要点
    if "减持" in shareholder_analysis.get("holdings_change", {}).get("net_direction", ""):
        prediction["watch_points"].append("关注股东减持进展")
    if "下滑" in revenue_trend or "下滑" in profit_trend:
        prediction["watch_points"].append("关注业绩拐点")
    if mgmt_changes >= 3:
        prediction["watch_points"].append("关注管理层稳定性")
    if "频繁融资" in capital_analysis.get("financing", {}).get("trend", ""):
        prediction["watch_points"].append("关注融资后的资金用途")

    # 综合展望
    positive_factors = len(prediction["investment_thesis"])
    negative_factors = len(prediction["watch_points"])

    if positive_factors >= 3 and negative_factors <= 1:
        prediction["overall_outlook"] = "积极看好"
    elif positive_factors >= 2 and negative_factors <= 2:
        prediction["overall_outlook"] = "谨慎乐观"
    elif negative_factors >= 3:
        prediction["overall_outlook"] = "需要观望"
    else:
        prediction["overall_outlook"] = "中性"

    return prediction


def analyze_market_intelligence(market_info: dict) -> dict:
    """
    分析市场资讯

    Args:
        market_info: 市场资讯数据

    Returns:
        市场资讯分析结果
    """
    analysis = {
        "news_sentiment": "",
        "institutional_view": "",
        "trading_signals": [],
        "market_attention": "",
        "key_events": [],
    }

    if not market_info:
        return analysis

    # 新闻情感
    sentiment = market_info.get("sentiment_analysis", {})
    score = sentiment.get("sentiment_score", 0)
    if score > 30:
        analysis["news_sentiment"] = "正面情绪主导"
    elif score < -30:
        analysis["news_sentiment"] = "负面情绪主导"
    else:
        analysis["news_sentiment"] = "情绪中性"

    # 机构观点
    research = market_info.get("research_reports", [])
    if research:
        ratings = [r.get("rating", "") for r in research if r.get("rating")]
        buy_ratings = sum(1 for r in ratings if "买入" in r or "推荐" in r or "增持" in r)
        if buy_ratings >= len(ratings) * 0.6:
            analysis["institutional_view"] = "机构普遍看好"
        elif buy_ratings >= len(ratings) * 0.3:
            analysis["institutional_view"] = "机构观点分化"
        else:
            analysis["institutional_view"] = "机构态度谨慎"

    # 交易信号
    dragon_tiger = market_info.get("dragon_tiger", [])
    if dragon_tiger:
        analysis["trading_signals"].append(f"近期{len(dragon_tiger)}次上龙虎榜")

    block_trades = market_info.get("block_trades", [])
    if block_trades:
        analysis["trading_signals"].append(f"近期{len(block_trades)}笔大宗交易")

    # 市场关注度
    news_count = market_info.get("summary", {}).get("news_count", 0)
    if news_count >= 15:
        analysis["market_attention"] = "高关注度"
    elif news_count >= 5:
        analysis["market_attention"] = "中等关注度"
    else:
        analysis["market_attention"] = "低关注度"

    # 关键事件提取
    positive_news = sentiment.get("positive_news", [])
    negative_news = sentiment.get("negative_news", [])
    analysis["key_events"] = positive_news[:3] + negative_news[:3]

    return analysis


def analyze_investment_highlights(notice_analysis: dict) -> dict:
    """
    分析投资亮点

    Args:
        notice_analysis: 公告分析数据

    Returns:
        投资亮点分析
    """
    highlights = {
        "major_investments": [],
        "strategic_moves": [],
        "fund_activities": [],
        "key_partners": [],
        "investment_directions": [],
    }

    if not notice_analysis:
        return highlights

    inv_analysis = notice_analysis.get("investment_analysis", {})

    # 重大投资
    significant = inv_analysis.get("significant_deals", [])
    for deal in significant[:5]:
        highlights["major_investments"].append({
            "title": deal.get("title", ""),
            "date": deal.get("date", ""),
            "importance": deal.get("score", 0),
        })

    # 基金活动
    funds = inv_analysis.get("fund_establishments", [])
    for fund in funds[:3]:
        highlights["fund_activities"].append({
            "title": fund.get("title", ""),
            "amounts": fund.get("amounts", []),
        })

    # 关键合作方
    highlights["key_partners"] = inv_analysis.get("key_partners", [])[:5]

    # 投资方向
    directions = inv_analysis.get("investment_directions", [])
    highlights["investment_directions"] = [d[0] for d in directions[:3]]

    return highlights


def run_deep_analysis(
    notices: Dict[str, List[dict]],
    financial_data: dict,
    market_info: dict = None,
    notice_analysis: dict = None
) -> dict:
    """
    运行完整深度分析

    Args:
        notices: 分类后的公告字典
        financial_data: 财务数据
        market_info: 市场资讯数据（可选）
        notice_analysis: 增强版公告分析（可选）

    Returns:
        深度分析结果
    """
    # 各维度分析
    capital_analysis = analyze_capital_strategy(notices, financial_data)
    expansion_analysis = analyze_business_expansion(notices)
    shareholder_analysis = analyze_shareholder_dynamics(notices)
    risk_analysis = analyze_risk_factors(notices)
    financial_trends = analyze_financial_trends(financial_data)

    # 市场资讯分析（新增）
    market_intelligence = {}
    if market_info:
        market_intelligence = analyze_market_intelligence(market_info)

    # 投资亮点分析（新增）
    investment_highlights = {}
    if notice_analysis:
        investment_highlights = analyze_investment_highlights(notice_analysis)

    # 综合预测
    future_prediction = predict_future_direction(
        capital_analysis,
        expansion_analysis,
        shareholder_analysis,
        financial_trends
    )

    # 如果有市场资讯，补充预测信息
    if market_intelligence:
        if market_intelligence.get("news_sentiment") == "正面情绪主导":
            future_prediction["investment_thesis"].append("市场情绪正面，舆论环境有利")
        elif market_intelligence.get("news_sentiment") == "负面情绪主导":
            future_prediction["watch_points"].append("市场情绪偏负面，关注舆论风险")

        if market_intelligence.get("institutional_view") == "机构普遍看好":
            future_prediction["investment_thesis"].append("机构研报普遍看好")

    return {
        "capital_strategy": capital_analysis,
        "business_expansion": expansion_analysis,
        "shareholder_dynamics": shareholder_analysis,
        "risk_factors": risk_analysis,
        "financial_trends": financial_trends,
        "future_prediction": future_prediction,
        "market_intelligence": market_intelligence,
        "investment_highlights": investment_highlights,
    }
