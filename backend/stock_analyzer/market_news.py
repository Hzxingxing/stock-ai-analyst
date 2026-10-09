"""市场资讯获取模块 - 获取股票相关外部新闻和市场资讯"""

import re
import sys
from typing import List, Dict, Optional, Tuple
from datetime import datetime, timedelta
import akshare as ak


def get_stock_news(stock_code: str, stock_name: str = "", limit: int = 30) -> List[Dict]:
    """
    获取股票相关新闻（东方财富 + 研报）

    Args:
        stock_code: 股票代码
        stock_name: 股票名称（用于搜索）
        limit: 获取数量限制

    Returns:
        新闻列表
    """
    news_list = []
    seen_titles = set()  # 用于去重

    def add_news_if_unique(news_item):
        """添加新闻（去重）"""
        title = news_item.get("title", "")
        if title and title not in seen_titles:
            seen_titles.add(title)
            news_list.append(news_item)

    # 1. 东方财富个股新闻（最可靠的数据源）
    try:
        df = ak.stock_news_em(symbol=stock_code)
        if not df.empty:
            for _, row in df.iterrows():
                add_news_if_unique({
                    "source": "东方财富",
                    "title": row.get("新闻标题", ""),
                    "content": row.get("新闻内容", "")[:200] if row.get("新闻内容") else "",
                    "date": str(row.get("发布时间", ""))[:10],
                    "url": row.get("新闻链接", ""),
                })
    except Exception as e:
        print(f"获取东方财富新闻失败: {e}", file=sys.stderr)

    # 2. 获取券商研报（补充专业分析）
    try:
        df = ak.stock_research_report_em(symbol=stock_code)
        if not df.empty:
            for _, row in df.head(20).iterrows():  # 增加研报数量
                add_news_if_unique({
                    "source": row.get("研报机构", "券商研报"),
                    "title": f"【研报】{row.get('报告名称', '')}",
                    "content": f"评级: {row.get('最新评级', 'N/A')} | 目标价: {row.get('目标价', 'N/A')}",
                    "date": str(row.get("发布日期", ""))[:10],
                    "url": "",
                })
                if len(news_list) >= limit:
                    break
    except Exception as e:
        print(f"获取研报失败: {e}", file=sys.stderr)

    return news_list[:limit]


def get_market_hot_news(keywords: List[str] = None, limit: int = 20) -> List[Dict]:
    """
    获取市场热点新闻（可按关键词筛选）

    Args:
        keywords: 关键词列表
        limit: 获取数量限制

    Returns:
        新闻列表
    """
    news_list = []

    # 获取财经新闻
    try:
        df = ak.stock_news_main_sina()
        if not df.empty:
            for _, row in df.head(limit * 2).iterrows():
                title = row.get("标题", "")
                content = row.get("内容", "")

                # 关键词筛选
                if keywords:
                    match = any(kw in title or kw in str(content) for kw in keywords)
                    if not match:
                        continue

                news_list.append({
                    "source": "新浪财经",
                    "title": title,
                    "content": content[:200] if content else "",
                    "date": str(row.get("时间", ""))[:10],
                    "url": row.get("链接", ""),
                })

                if len(news_list) >= limit:
                    break
    except Exception as e:
        print(f"获取市场新闻失败: {e}", file=sys.stderr)

    return news_list


def search_acquisition_news(stock_name: str, target_name: str = "") -> List[Dict]:
    """
    搜索并购/收购相关新闻

    Args:
        stock_name: 公司名称
        target_name: 标的公司名称（可选）

    Returns:
        并购相关新闻
    """
    keywords = [stock_name]
    if target_name:
        keywords.append(target_name)

    # 添加并购相关关键词
    ma_keywords = ["收购", "并购", "竞购", "要约", "重组", "借壳"]

    news = get_market_hot_news(keywords=keywords, limit=50)

    # 筛选并购相关
    ma_news = []
    for n in news:
        title = n.get("title", "")
        content = n.get("content", "")
        if any(kw in title or kw in content for kw in ma_keywords):
            ma_news.append(n)

    return ma_news


def get_industry_news(industry: str, limit: int = 20) -> List[Dict]:
    """
    获取行业新闻

    Args:
        industry: 行业名称
        limit: 获取数量限制

    Returns:
        行业新闻列表
    """
    # 行业关键词映射
    industry_keywords = {
        "游戏": ["游戏", "手游", "网游", "电竞", "游戏版号"],
        "AI": ["人工智能", "AI", "大模型", "ChatGPT", "智算"],
        "数据中心": ["数据中心", "IDC", "算力", "云计算"],
        "半导体": ["芯片", "半导体", "集成电路", "晶圆"],
        "新能源": ["新能源", "光伏", "储能", "锂电池"],
    }

    keywords = industry_keywords.get(industry, [industry])
    return get_market_hot_news(keywords=keywords, limit=limit)


def analyze_news_sentiment(news_list: List[Dict]) -> Dict:
    """
    分析新闻情感倾向

    Args:
        news_list: 新闻列表

    Returns:
        情感分析结果
    """
    positive_words = ["利好", "增长", "突破", "创新高", "大涨", "获批", "中标",
                      "战略合作", "签约", "业绩增长", "超预期"]
    negative_words = ["利空", "下跌", "亏损", "减持", "失败", "终止", "暴跌",
                      "处罚", "诉讼", "违规", "风险", "退市"]

    result = {
        "positive_count": 0,
        "negative_count": 0,
        "neutral_count": 0,
        "positive_news": [],
        "negative_news": [],
        "sentiment_score": 0,
    }

    for news in news_list:
        title = news.get("title", "")
        content = news.get("content", "")
        text = title + content

        pos_hits = sum(1 for w in positive_words if w in text)
        neg_hits = sum(1 for w in negative_words if w in text)

        if pos_hits > neg_hits:
            result["positive_count"] += 1
            result["positive_news"].append(title[:50])
        elif neg_hits > pos_hits:
            result["negative_count"] += 1
            result["negative_news"].append(title[:50])
        else:
            result["neutral_count"] += 1

    total = len(news_list)
    if total > 0:
        # 情感分数: -100 到 +100
        result["sentiment_score"] = int(
            (result["positive_count"] - result["negative_count"]) / total * 100
        )

    return result


def get_stock_research_reports(stock_code: str, limit: int = 10) -> List[Dict]:
    """
    获取券商研报

    Args:
        stock_code: 股票代码
        limit: 获取数量限制

    Returns:
        研报列表
    """
    reports = []

    try:
        df = ak.stock_research_report_em(symbol=stock_code)
        if not df.empty:
            for _, row in df.head(limit).iterrows():
                reports.append({
                    "title": row.get("报告名称", ""),
                    "institution": row.get("研报机构", ""),
                    "author": row.get("报告作者", ""),
                    "date": str(row.get("发布日期", ""))[:10],
                    "rating": row.get("最新评级", ""),
                    "target_price": row.get("目标价", ""),
                })
    except Exception as e:
        print(f"获取研报失败: {e}", file=sys.stderr)

    return reports


def get_dragon_tiger_list(stock_code: str, days: int = 30) -> List[Dict]:
    """
    获取龙虎榜数据

    Args:
        stock_code: 股票代码
        days: 获取天数

    Returns:
        龙虎榜数据
    """
    data = []

    try:
        end_date = datetime.now().strftime("%Y%m%d")
        start_date = (datetime.now() - timedelta(days=days)).strftime("%Y%m%d")

        df = ak.stock_lhb_detail_em(
            symbol=stock_code,
            start_date=start_date,
            end_date=end_date
        )

        if not df.empty:
            for _, row in df.iterrows():
                data.append({
                    "date": str(row.get("上榜日期", ""))[:10],
                    "reason": row.get("上榜原因", ""),
                    "close": row.get("收盘价", ""),
                    "change_pct": row.get("涨跌幅", ""),
                    "buy_amount": row.get("买入金额", ""),
                    "sell_amount": row.get("卖出金额", ""),
                    "net_amount": row.get("净买入", ""),
                })
    except Exception:
        # 部分股票无龙虎榜数据或接口不支持，静默处理
        pass

    return data


def get_block_trades(stock_code: str, days: int = 90) -> List[Dict]:
    """
    获取大宗交易数据

    Args:
        stock_code: 股票代码
        days: 获取天数

    Returns:
        大宗交易数据
    """
    trades = []

    try:
        df = ak.stock_dzjy_mrmx(symbol=stock_code)
        if not df.empty:
            for _, row in df.head(20).iterrows():
                trades.append({
                    "date": str(row.get("交易日期", ""))[:10],
                    "price": row.get("成交价", ""),
                    "volume": row.get("成交量", ""),
                    "amount": row.get("成交额", ""),
                    "buyer": row.get("买方营业部", ""),
                    "seller": row.get("卖方营业部", ""),
                    "discount": row.get("折溢率", ""),
                })
    except Exception:
        # 部分股票无大宗交易数据，静默处理
        pass

    return trades


def get_comprehensive_market_info(stock_code: str, stock_name: str) -> Dict:
    """
    获取综合市场资讯

    Args:
        stock_code: 股票代码
        stock_name: 股票名称

    Returns:
        综合市场资讯
    """
    print("正在获取市场资讯...", file=sys.stderr)

    # 1. 个股新闻
    print("  获取个股新闻...", file=sys.stderr)
    stock_news = get_stock_news(stock_code, stock_name, limit=20)

    # 2. 新闻情感分析
    sentiment = analyze_news_sentiment(stock_news)

    # 3. 研究报告
    print("  获取研究报告...", file=sys.stderr)
    research = get_stock_research_reports(stock_code, limit=5)

    # 4. 龙虎榜
    print("  获取龙虎榜数据...", file=sys.stderr)
    dragon_tiger = get_dragon_tiger_list(stock_code, days=60)

    # 5. 大宗交易
    print("  获取大宗交易...", file=sys.stderr)
    block_trades = get_block_trades(stock_code, days=90)

    # 汇总分析
    market_summary = {
        "news_count": len(stock_news),
        "sentiment": sentiment,
        "research_count": len(research),
        "latest_ratings": [r.get("rating") for r in research[:3]],
        "dragon_tiger_count": len(dragon_tiger),
        "block_trade_count": len(block_trades),
    }

    # 大宗交易净买入统计
    if block_trades:
        total_amount = sum(
            float(str(t.get("amount", "0")).replace(",", "").replace("万", "0000"))
            for t in block_trades
            if t.get("amount")
        )
        market_summary["block_trade_total"] = f"{total_amount / 10000:.2f}万" if total_amount else "N/A"

    return {
        "stock_news": stock_news[:15],
        "sentiment_analysis": sentiment,
        "research_reports": research,
        "dragon_tiger": dragon_tiger[:10],
        "block_trades": block_trades[:10],
        "summary": market_summary,
    }


def search_specific_event(stock_name: str, event_keywords: List[str]) -> Dict:
    """
    搜索特定事件

    Args:
        stock_name: 公司名称
        event_keywords: 事件关键词列表

    Returns:
        搜索结果
    """
    result = {
        "found": False,
        "related_news": [],
        "summary": "",
    }

    # 组合搜索关键词
    search_keywords = [stock_name] + event_keywords

    news = get_market_hot_news(keywords=search_keywords, limit=30)

    # 进一步过滤
    for n in news:
        title = n.get("title", "")
        content = n.get("content", "")
        text = title + content

        # 检查是否同时包含公司名和事件关键词
        has_company = stock_name in text
        has_event = any(kw in text for kw in event_keywords)

        if has_company and has_event:
            result["found"] = True
            result["related_news"].append(n)

    if result["related_news"]:
        result["summary"] = f"找到{len(result['related_news'])}条相关新闻"

    return result
