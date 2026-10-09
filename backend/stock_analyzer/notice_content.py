"""公告内容解析模块 - 获取并解析公告PDF内容"""

import re
import sys
from typing import List, Dict, Optional, Tuple
from datetime import datetime
import akshare as ak


# 关键信息提取模式
KEY_PATTERNS = {
    "金额": [
        r"(\d+(?:,\d{3})*(?:\.\d+)?)\s*(?:万元|亿元|元)",
        r"(?:投资|出资|认缴|金额|规模).*?(\d+(?:,\d{3})*(?:\.\d+)?)\s*(?:万元|亿元|元)",
        r"人民币\s*(\d+(?:,\d{3})*(?:\.\d+)?)\s*(?:万元|亿元|元)",
    ],
    "合作方": [
        r"(?:与|联合|携手|协同)\s*([^，。、\n]+(?:公司|集团|基金|有限|投资))",
        r"([^，。\n]+(?:国资委|国资|政府|基金会))",
        r"合作方[：:]\s*([^\n，。]+)",
    ],
    "投资标的": [
        r"(?:投资|收购|并购|入股)\s*([^，。\n]+(?:公司|项目|资产))",
        r"(?:标的|目标)[：:]\s*([^\n，。]+)",
    ],
    "持股比例": [
        r"(?:持股|占股|股权|出资)(?:比例)?[：:]?\s*(\d+(?:\.\d+)?)\s*%",
        r"(\d+(?:\.\d+)?)\s*%\s*(?:股权|股份|权益)",
    ],
    "基金规模": [
        r"(?:基金|基金规模|总规模|认缴规模)[：:]?\s*(\d+(?:,\d{3})*(?:\.\d+)?)\s*(?:万元|亿元)",
        r"(?:募集|规模).*?(\d+(?:,\d{3})*(?:\.\d+)?)\s*(?:万元|亿元)",
    ],
}

# 重要公告类型关键词
IMPORTANT_KEYWORDS = {
    "投资并购": ["投资", "并购", "收购", "入股", "合资", "参股", "战略投资"],
    "基金设立": ["基金", "合伙企业", "有限合伙", "LP", "GP"],
    "对外合作": ["合作", "战略协议", "框架协议", "合作协议"],
    "资产交易": ["资产", "转让", "出售", "处置"],
    "增资扩股": ["增资", "扩股", "注资"],
}


def get_notice_content_url(notice_info: dict) -> Optional[str]:
    """
    获取公告PDF下载链接

    Args:
        notice_info: 公告信息字典，包含announcement_id等

    Returns:
        PDF下载URL
    """
    # CNINFO公告URL格式
    ann_id = notice_info.get("announcement_id") or notice_info.get("ann_id")
    if ann_id:
        return f"http://static.cninfo.com.cn/finalpage/2025-01-01/{ann_id}.PDF"
    return None


def extract_key_info_from_title(title: str) -> Dict:
    """
    从公告标题提取关键信息

    Args:
        title: 公告标题

    Returns:
        提取的关键信息
    """
    info = {
        "title": title,
        "amounts": [],
        "partners": [],
        "targets": [],
        "percentages": [],
        "keywords_found": [],
    }

    # 提取金额
    for pattern in KEY_PATTERNS["金额"]:
        matches = re.findall(pattern, title)
        for m in matches:
            # 清理数字格式
            num = m.replace(",", "")
            info["amounts"].append(num)

    # 提取合作方
    for pattern in KEY_PATTERNS["合作方"]:
        matches = re.findall(pattern, title)
        info["partners"].extend(matches)

    # 提取投资标的
    for pattern in KEY_PATTERNS["投资标的"]:
        matches = re.findall(pattern, title)
        info["targets"].extend(matches)

    # 提取持股比例
    for pattern in KEY_PATTERNS["持股比例"]:
        matches = re.findall(pattern, title)
        info["percentages"].extend(matches)

    # 检查重要关键词
    for category, keywords in IMPORTANT_KEYWORDS.items():
        for kw in keywords:
            if kw in title:
                info["keywords_found"].append((category, kw))

    return info


def get_notice_details_batch(stock_code: str, years: int = 3, limit: int = 50) -> List[Dict]:
    """
    批量获取公告详细信息（包括解析的关键信息）

    Args:
        stock_code: 股票代码
        years: 获取年数
        limit: 获取数量限制

    Returns:
        公告详情列表
    """
    from .notice_fetcher import get_stock_notices

    df = get_stock_notices(stock_code, years=years)

    if df.empty:
        return []

    notices = []
    for _, row in df.head(limit).iterrows():
        notices.append({
            "title": row.get("title", ""),
            "date": str(row.get("date", ""))[:10],
            "url": row.get("url", ""),
        })

    detailed_notices = []
    for notice in notices:
        title = notice.get("title", "")

        # 提取关键信息
        key_info = extract_key_info_from_title(title)

        detailed = {
            **notice,
            "key_info": key_info,
            "has_amount": len(key_info["amounts"]) > 0,
            "has_partner": len(key_info["partners"]) > 0,
            "importance_score": calculate_importance_score(notice, key_info),
        }
        detailed_notices.append(detailed)

    # 按重要性排序
    detailed_notices.sort(key=lambda x: x["importance_score"], reverse=True)

    return detailed_notices


def calculate_importance_score(notice: dict, key_info: dict) -> int:
    """
    计算公告重要性评分

    Args:
        notice: 公告信息
        key_info: 提取的关键信息

    Returns:
        重要性评分 (0-100)
    """
    score = 0

    # 有金额信息 +20
    if key_info["amounts"]:
        score += 20
        # 金额越大越重要
        for amt in key_info["amounts"]:
            try:
                num = float(amt)
                if num >= 10:  # 假设是亿元级别
                    score += 20
                elif num >= 1:
                    score += 10
            except:
                pass

    # 有合作方信息 +15
    if key_info["partners"]:
        score += 15
        # 国资合作更重要
        for partner in key_info["partners"]:
            if "国资" in partner or "政府" in partner:
                score += 10

    # 有投资标的 +10
    if key_info["targets"]:
        score += 10

    # 关键词加分
    keyword_scores = {
        "投资并购": 15,
        "基金设立": 15,
        "对外合作": 10,
        "资产交易": 12,
        "增资扩股": 10,
    }

    seen_categories = set()
    for category, _ in key_info["keywords_found"]:
        if category not in seen_categories:
            score += keyword_scores.get(category, 5)
            seen_categories.add(category)

    # 公告类型加分
    notice_type = notice.get("type", "")
    type_scores = {
        "投资并购": 15,
        "对外合作": 12,
        "子公司": 8,
        "融资": 10,
        "股份回购": 8,
    }
    for t, s in type_scores.items():
        if t in notice_type:
            score += s
            break

    return min(score, 100)


def analyze_investment_activities(notices: List[Dict]) -> Dict:
    """
    分析投资活动汇总

    Args:
        notices: 公告列表（带详细信息）

    Returns:
        投资活动分析结果
    """
    analysis = {
        "total_investments": 0,
        "estimated_total_amount": "",
        "key_partners": [],
        "investment_directions": [],
        "fund_establishments": [],
        "significant_deals": [],
    }

    amounts_wan = []  # 收集万元金额
    amounts_yi = []   # 收集亿元金额
    partners_set = set()
    directions_count = {}

    for notice in notices:
        key_info = notice.get("key_info", {})
        title = notice.get("title", "")

        # 检查是否为投资类公告
        is_investment = any(
            cat == "投资并购" or cat == "基金设立"
            for cat, _ in key_info.get("keywords_found", [])
        )

        if is_investment or key_info.get("amounts"):
            analysis["total_investments"] += 1

            # 收集金额
            for amt in key_info.get("amounts", []):
                try:
                    num = float(amt)
                    if "亿" in title:
                        amounts_yi.append(num)
                    else:
                        amounts_wan.append(num)
                except:
                    pass

            # 收集合作方
            for partner in key_info.get("partners", []):
                partners_set.add(partner)

            # 统计投资方向
            for direction_kw in ["智算", "数据中心", "云计算", "AI", "人工智能",
                                  "半导体", "芯片", "新能源", "游戏", "文娱"]:
                if direction_kw in title:
                    directions_count[direction_kw] = directions_count.get(direction_kw, 0) + 1

            # 基金设立
            if "基金" in title or "合伙" in title:
                analysis["fund_establishments"].append({
                    "title": title[:60],
                    "date": notice.get("date"),
                    "amounts": key_info.get("amounts", []),
                })

            # 重大交易（高评分）
            if notice.get("importance_score", 0) >= 40:
                analysis["significant_deals"].append({
                    "title": title[:60],
                    "date": notice.get("date"),
                    "score": notice.get("importance_score"),
                    "amounts": key_info.get("amounts", []),
                    "partners": key_info.get("partners", []),
                })

    # 汇总金额
    total_yi = sum(amounts_yi)
    total_wan = sum(amounts_wan) / 10000  # 转亿元
    if total_yi + total_wan > 0:
        analysis["estimated_total_amount"] = f"约{total_yi + total_wan:.1f}亿元(估算)"

    analysis["key_partners"] = list(partners_set)[:10]
    analysis["investment_directions"] = sorted(
        directions_count.items(),
        key=lambda x: x[1],
        reverse=True
    )[:5]

    return analysis


def get_enhanced_notice_analysis(stock_code: str, years: int = 3) -> Dict:
    """
    获取增强版公告分析

    Args:
        stock_code: 股票代码
        years: 分析年数

    Returns:
        增强版公告分析结果
    """
    print("正在获取公告详情...", file=sys.stderr)
    detailed_notices = get_notice_details_batch(stock_code, years=years, limit=100)

    print("正在分析投资活动...", file=sys.stderr)
    investment_analysis = analyze_investment_activities(detailed_notices)

    # 按类型分组重要公告
    important_by_type = {}
    for notice in detailed_notices:
        if notice.get("importance_score", 0) >= 30:
            notice_type = notice.get("type", "其他")
            if notice_type not in important_by_type:
                important_by_type[notice_type] = []
            important_by_type[notice_type].append(notice)

    return {
        "detailed_notices": detailed_notices[:50],  # 限制数量
        "investment_analysis": investment_analysis,
        "important_by_type": important_by_type,
        "total_analyzed": len(detailed_notices),
    }
