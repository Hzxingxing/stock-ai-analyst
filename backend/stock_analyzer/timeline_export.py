"""结构化数据导出模块 - 导出时间线格式的分析数据"""

import json
from datetime import datetime
from typing import List, Dict, Optional
import pandas as pd


def export_timeline_data(
    stock_code: str,
    stock_name: str,
    notices: List[dict],
    classified_notices: Dict[str, List[dict]],
    financial_data: dict,
    market_info: dict = None,
    notice_analysis: dict = None
) -> List[Dict]:
    """
    导出时间线格式的结构化数据

    Args:
        stock_code: 股票代码
        stock_name: 股票名称
        notices: 公告列表
        classified_notices: 分类公告
        financial_data: 财务数据
        market_info: 市场资讯
        notice_analysis: 增强版公告分析

    Returns:
        时间线数据列表，每条包含 date, type, title, summary
    """
    timeline = []

    # 1. 公告数据
    for notice in notices:
        date = notice.get("date", "")
        if isinstance(date, pd.Timestamp):
            date = date.strftime("%Y-%m-%d")
        else:
            date = str(date)[:10]

        timeline.append({
            "date": date,
            "type": "公告",
            "category": notice.get("type", "其他"),
            "title": notice.get("title", ""),
            "summary": extract_notice_summary(notice),
            "source": "巨潮资讯",
            "importance": calculate_notice_importance(notice),
        })

    # 2. 财务数据（季度报告）
    profit = financial_data.get("profit", pd.DataFrame())
    if not profit.empty:
        for _, row in profit.iterrows():
            report_date = row.get("report_date")
            if pd.notna(report_date):
                if isinstance(report_date, pd.Timestamp):
                    date_str = report_date.strftime("%Y-%m-%d")
                    q = (report_date.month - 1) // 3 + 1
                    year = report_date.year
                else:
                    date_str = str(report_date)[:10]
                    q = 4
                    year = 2024

                revenue = row.get("revenue")
                net_profit = row.get("net_profit")
                eps = row.get("eps")
                revenue_yoy = row.get("revenue_yoy")
                profit_yoy = row.get("net_profit_yoy")

                # 格式化数值
                revenue_str = format_amount(revenue) if pd.notna(revenue) else "N/A"
                profit_str = format_amount(net_profit) if pd.notna(net_profit) else "N/A"
                eps_str = f"{float(eps):.2f}" if pd.notna(eps) else "N/A"
                rev_yoy_str = f"{float(revenue_yoy):+.1f}%" if pd.notna(revenue_yoy) else "N/A"
                profit_yoy_str = f"{float(profit_yoy):+.1f}%" if pd.notna(profit_yoy) else "N/A"

                summary = f"营收{revenue_str}({rev_yoy_str})，净利润{profit_str}({profit_yoy_str})，EPS {eps_str}"

                timeline.append({
                    "date": date_str,
                    "type": "财报",
                    "category": f"{year}Q{q}",
                    "title": f"{year}年第{q}季度财务报告",
                    "summary": summary,
                    "source": "东方财富",
                    "importance": "high" if q == 4 else "medium",
                    "data": {
                        "revenue": float(revenue) if pd.notna(revenue) else None,
                        "net_profit": float(net_profit) if pd.notna(net_profit) else None,
                        "eps": float(eps) if pd.notna(eps) else None,
                        "revenue_yoy": float(revenue_yoy) if pd.notna(revenue_yoy) else None,
                        "net_profit_yoy": float(profit_yoy) if pd.notna(profit_yoy) else None,
                    }
                })

    # 3. 市场新闻
    if market_info:
        news_list = market_info.get("stock_news", [])
        for news in news_list:
            date = news.get("date", "")[:10]
            timeline.append({
                "date": date,
                "type": "新闻",
                "category": news.get("source", "财经"),
                "title": news.get("title", ""),
                "summary": news.get("content", "")[:200] if news.get("content") else "",
                "source": news.get("source", ""),
                "importance": analyze_news_importance(news),
                "url": news.get("url", ""),
            })

        # 研报
        research = market_info.get("research_reports", [])
        for report in research:
            date = report.get("date", "")[:10]
            rating = report.get("rating", "")
            institution = report.get("institution", "")
            target = report.get("target_price", "")

            summary_parts = []
            if rating:
                summary_parts.append(f"评级: {rating}")
            if target:
                summary_parts.append(f"目标价: {target}")
            if institution:
                summary_parts.append(f"机构: {institution}")

            timeline.append({
                "date": date,
                "type": "研报",
                "category": institution,
                "title": report.get("title", ""),
                "summary": ", ".join(summary_parts),
                "source": institution,
                "importance": "medium",
                "data": {
                    "rating": rating,
                    "target_price": target,
                    "author": report.get("author", ""),
                }
            })

        # 龙虎榜
        dragon = market_info.get("dragon_tiger", [])
        for d in dragon:
            date = d.get("date", "")[:10]
            reason = d.get("reason", "")
            net = d.get("net_amount", "")
            buy = d.get("buy_amount", "")
            sell = d.get("sell_amount", "")

            timeline.append({
                "date": date,
                "type": "龙虎榜",
                "category": "交易数据",
                "title": f"上榜原因: {reason}",
                "summary": f"净买入{net}，买入{buy}，卖出{sell}",
                "source": "东方财富",
                "importance": "high",
                "data": {
                    "reason": reason,
                    "net_amount": net,
                    "buy_amount": buy,
                    "sell_amount": sell,
                }
            })

        # 大宗交易
        block = market_info.get("block_trades", [])
        for b in block:
            date = b.get("date", "")[:10]
            amount = b.get("amount", "")
            price = b.get("price", "")
            discount = b.get("discount", "")

            timeline.append({
                "date": date,
                "type": "大宗交易",
                "category": "交易数据",
                "title": f"大宗交易成交{amount}",
                "summary": f"成交价{price}，折溢率{discount}",
                "source": "东方财富",
                "importance": "medium",
                "data": {
                    "amount": amount,
                    "price": price,
                    "discount": discount,
                    "buyer": b.get("buyer", ""),
                    "seller": b.get("seller", ""),
                }
            })

    # 按日期排序（最新在前）
    timeline.sort(key=lambda x: x.get("date", ""), reverse=True)

    return timeline


def format_amount(value) -> str:
    """格式化金额"""
    if pd.isna(value) or value is None:
        return "N/A"
    value = float(value)
    if abs(value) >= 1e8:
        return f"{value/1e8:.2f}亿"
    elif abs(value) >= 1e4:
        return f"{value/1e4:.2f}万"
    return f"{value:.2f}"


def extract_notice_summary(notice: dict) -> str:
    """从公告提取摘要"""
    title = notice.get("title", "")
    notice_type = notice.get("type", "")

    # 根据类型生成摘要
    if notice_type == "业绩公告":
        if "预告" in title:
            return "业绩预告公告"
        elif "快报" in title:
            return "业绩快报公告"
        else:
            return "定期报告披露"
    elif notice_type == "股份回购":
        if "注销" in title:
            return "回购股份注销，减少注册资本"
        else:
            return "股份回购相关公告"
    elif notice_type == "增减持":
        if "减持" in title:
            return "股东/高管减持股份"
        else:
            return "股东/高管增持股份"
    elif notice_type == "投资并购":
        if "投资" in title:
            return "对外投资公告"
        elif "收购" in title:
            return "收购相关公告"
        else:
            return "投资并购事项"
    elif notice_type == "子公司":
        return "子公司相关事项"
    elif notice_type == "股权激励":
        return "员工股权激励计划"
    elif notice_type == "高管变动":
        return "董监高人事变动"
    elif notice_type == "分红送转":
        return "利润分配/分红方案"
    elif notice_type == "诉讼仲裁":
        return "涉及诉讼/仲裁事项"
    elif notice_type == "处罚":
        return "监管处罚/问询相关"
    else:
        return title[:50] if len(title) > 50 else title


def calculate_notice_importance(notice: dict) -> str:
    """计算公告重要性"""
    title = notice.get("title", "")
    notice_type = notice.get("type", "")

    high_importance = ["业绩公告", "股份回购", "增减持", "投资并购", "诉讼仲裁", "处罚"]
    medium_importance = ["分红送转", "股权激励", "子公司", "融资"]

    if notice_type in high_importance:
        return "high"
    elif notice_type in medium_importance:
        return "medium"
    else:
        return "low"


def analyze_news_importance(news: dict) -> str:
    """分析新闻重要性"""
    title = news.get("title", "")
    content = news.get("content", "")
    text = title + content

    high_keywords = ["收购", "并购", "重组", "涨停", "暴跌", "利好", "利空",
                     "战略合作", "重大", "突破", "创新高", "违规", "处罚"]
    medium_keywords = ["投资", "合作", "签约", "业绩", "增长", "下滑"]

    for kw in high_keywords:
        if kw in text:
            return "high"

    for kw in medium_keywords:
        if kw in text:
            return "medium"

    return "low"


def export_to_json(timeline: List[Dict], filepath: str = None) -> str:
    """导出为JSON格式"""
    output = json.dumps(timeline, ensure_ascii=False, indent=2)
    if filepath:
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(output)
    return output


def export_to_text(timeline: List[Dict]) -> str:
    """导出为文本格式"""
    lines = []
    lines.append("=" * 60)
    lines.append("时间线数据汇总")
    lines.append("=" * 60)
    lines.append("")

    current_month = ""
    for item in timeline:
        date = item.get("date", "")
        month = date[:7] if date else ""

        # 月份分隔
        if month != current_month:
            current_month = month
            lines.append("")
            lines.append(f"### {month}")
            lines.append("-" * 40)

        item_type = item.get("type", "")
        category = item.get("category", "")
        title = item.get("title", "")
        summary = item.get("summary", "")
        importance = item.get("importance", "")

        importance_mark = ""
        if importance == "high":
            importance_mark = " [重要]"
        elif importance == "medium":
            importance_mark = " [关注]"

        lines.append(f"{date} [{item_type}:{category}]{importance_mark}")
        lines.append(f"  标题: {title}")
        if summary:
            lines.append(f"  摘要: {summary}")
        lines.append("")

    return "\n".join(lines)


def get_timeline_summary(timeline: List[Dict]) -> Dict:
    """获取时间线统计摘要"""
    summary = {
        "total_count": len(timeline),
        "by_type": {},
        "high_importance_count": 0,
        "date_range": {"start": "", "end": ""},
    }

    dates = []
    for item in timeline:
        item_type = item.get("type", "其他")
        summary["by_type"][item_type] = summary["by_type"].get(item_type, 0) + 1

        if item.get("importance") == "high":
            summary["high_importance_count"] += 1

        date = item.get("date", "")
        if date:
            dates.append(date)

    if dates:
        summary["date_range"]["start"] = min(dates)
        summary["date_range"]["end"] = max(dates)

    return summary
