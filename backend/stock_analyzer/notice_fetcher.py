"""公告获取模块 - 获取A股公告信息"""

from datetime import datetime, timedelta
from typing import Optional, List, Dict
import pandas as pd
import akshare as ak


# 公告分类关键词
NOTICE_CATEGORIES = {
    "业绩公告": ["年报", "季报", "半年报", "业绩预告", "业绩快报", "年度报告", "季度报告"],
    "分红送转": ["分红", "派息", "送股", "转增", "利润分配"],
    "股份回购": ["回购", "注销股份"],
    "增减持": ["减持", "增持", "权益变动"],
    "股权激励": ["股权激励", "限制性股票", "股票期权", "员工持股"],
    "投资并购": ["投资", "收购", "并购", "重组", "资产重组", "重大资产"],
    "对外合作": ["合作", "战略协议", "框架协议", "签署协议", "合资"],
    "子公司": ["子公司", "设立", "注销子公司", "对外投资"],
    "融资": ["发行", "配股", "增发", "可转债", "定增"],
    "诉讼仲裁": ["诉讼", "仲裁", "判决", "立案"],
    "处罚": ["处罚", "警示", "监管", "问询"],
    "高管变动": ["辞职", "任命", "聘任", "董事", "监事", "高管"],
    "其他": []
}


def get_stock_notices(
    stock_code: str,
    years: int = 3,
    keyword: Optional[str] = None,
    start_date: Optional[str] = None
) -> pd.DataFrame:
    """
    获取股票公告

    Args:
        stock_code: 股票代码，如 "600519"
        years: 获取最近几年的公告（当start_date未指定时使用）
        keyword: 关键词筛选 (可选)
        start_date: 起始日期，格式 "YYYYMMDD" 或 "YYYY-MM-DD"（可选，指定后忽略years参数）

    Returns:
        DataFrame包含: 公告标题、公告时间、公告类型
    """
    end_date = datetime.now().strftime("%Y%m%d")
    if start_date:
        # 支持 YYYY-MM-DD 格式转换
        start_date = start_date.replace("-", "")
    else:
        start_date = (datetime.now() - timedelta(days=years * 365)).strftime("%Y%m%d")

    try:
        df = ak.stock_zh_a_disclosure_report_cninfo(
            symbol=stock_code,
            market="沪深京",
            start_date=start_date,
            end_date=end_date,
            keyword=keyword if keyword else ""
        )

        if df is None or df.empty:
            return pd.DataFrame()

        # 标准化列名
        df = df.rename(columns={
            "公告标题": "title",
            "公告时间": "date",
            "公告链接": "url"
        })

        # 保留需要的列
        columns = ["date", "title"]
        if "url" in df.columns:
            columns.append("url")
        df = df[[col for col in columns if col in df.columns]]

        # 转换日期
        df["date"] = pd.to_datetime(df["date"])

        # 按日期降序排列
        df = df.sort_values("date", ascending=False).reset_index(drop=True)

        return df

    except KeyError as e:
        # AKShare在没有数据时可能会抛出KeyError（库内部bug）
        # 这种情况视为无新数据
        return pd.DataFrame()
    except Exception as e:
        print(f"获取公告失败: {e}")
        return pd.DataFrame()


def classify_notice(title: str) -> str:
    """
    根据公告标题分类

    Returns:
        公告类型
    """
    title_lower = title.lower()

    for category, keywords in NOTICE_CATEGORIES.items():
        if category == "其他":
            continue
        for kw in keywords:
            if kw in title_lower or kw in title:
                return category

    return "其他"


def get_all_notices_classified(
    stock_code: str,
    years: int = 3
) -> Dict[str, List[dict]]:
    """
    获取所有公告并分类

    Args:
        stock_code: 股票代码
        years: 年限

    Returns:
        按类型分类的公告字典
    """
    df = get_stock_notices(stock_code, years)

    if df.empty:
        return {}

    # 分类公告
    df["type"] = df["title"].apply(classify_notice)

    # 按类型分组
    classified = {}
    for notice_type in NOTICE_CATEGORIES.keys():
        type_df = df[df["type"] == notice_type]
        if not type_df.empty:
            classified[notice_type] = [
                {
                    "date": row["date"].strftime("%Y-%m-%d"),
                    "title": row["title"]
                }
                for _, row in type_df.iterrows()
            ]

    return classified


def get_important_notices(
    stock_code: str,
    years: int = 3,
    limit: int = 20
) -> List[dict]:
    """
    获取重要公告摘要

    Args:
        stock_code: 股票代码
        years: 年限
        limit: 返回条数限制

    Returns:
        重要公告列表
    """
    df = get_stock_notices(stock_code, years)

    if df.empty:
        return []

    # 分类公告
    df["type"] = df["title"].apply(classify_notice)

    # 优先级排序 (越重要的类型优先级越高)
    priority = {
        "业绩公告": 1,
        "投资并购": 2,
        "股份回购": 3,
        "增减持": 4,
        "对外合作": 5,
        "子公司": 6,
        "分红送转": 7,
        "股权激励": 8,
        "融资": 9,
        "高管变动": 10,
        "诉讼仲裁": 11,
        "处罚": 12,
        "其他": 99
    }
    df["priority"] = df["type"].map(lambda x: priority.get(x, 99))
    df = df.sort_values(["date", "priority"], ascending=[False, True])

    # 取前N条
    df = df.head(limit)

    # 转为字典列表
    notices = []
    for _, row in df.iterrows():
        notices.append({
            "date": row["date"].strftime("%Y-%m-%d"),
            "type": row["type"],
            "title": row["title"][:60] + "..." if len(row["title"]) > 60 else row["title"]
        })

    return notices


def get_notices_summary(stock_code: str, years: int = 3) -> dict:
    """
    获取公告统计摘要

    Returns:
        公告统计信息
    """
    df = get_stock_notices(stock_code, years)

    if df.empty:
        return {"total": 0, "by_type": {}, "by_year": {}}

    df["type"] = df["title"].apply(classify_notice)
    df["year"] = df["date"].dt.year

    summary = {
        "total": len(df),
        "by_type": df["type"].value_counts().to_dict(),
        "by_year": df["year"].value_counts().sort_index(ascending=False).to_dict(),
        "latest_date": df["date"].max().strftime("%Y-%m-%d") if len(df) > 0 else None
    }

    return summary


def analyze_notice_trends(stock_code: str, years: int = 3) -> dict:
    """
    分析公告趋势，提取公司动向

    Returns:
        公告趋势分析
    """
    classified = get_all_notices_classified(stock_code, years)

    analysis = {
        "capital_actions": [],  # 资本运作
        "business_expansion": [],  # 业务扩张
        "risk_signals": [],  # 风险信号
        "shareholder_actions": [],  # 股东动向
        "summary": ""
    }

    # 资本运作分析
    for notice_type in ["股份回购", "融资", "分红送转"]:
        if notice_type in classified:
            for n in classified[notice_type][:5]:
                analysis["capital_actions"].append(f"{n['date']}: {n['title'][:40]}")

    # 业务扩张分析
    for notice_type in ["投资并购", "对外合作", "子公司"]:
        if notice_type in classified:
            for n in classified[notice_type][:5]:
                analysis["business_expansion"].append(f"{n['date']}: {n['title'][:40]}")

    # 风险信号
    for notice_type in ["诉讼仲裁", "处罚"]:
        if notice_type in classified:
            for n in classified[notice_type][:3]:
                analysis["risk_signals"].append(f"{n['date']}: {n['title'][:40]}")

    # 股东动向
    for notice_type in ["增减持", "股权激励"]:
        if notice_type in classified:
            for n in classified[notice_type][:5]:
                analysis["shareholder_actions"].append(f"{n['date']}: {n['title'][:40]}")

    # 生成摘要
    summary_parts = []

    # 回购分析
    if "股份回购" in classified and len(classified["股份回购"]) > 0:
        summary_parts.append(f"近{years}年有{len(classified['股份回购'])}次回购动作，显示公司对股价有信心")

    # 增减持分析
    if "增减持" in classified:
        notices = classified["增减持"]
        reduce_count = sum(1 for n in notices if "减持" in n["title"])
        increase_count = sum(1 for n in notices if "增持" in n["title"])
        if reduce_count > increase_count:
            summary_parts.append(f"股东减持({reduce_count}次)多于增持({increase_count}次)，需关注")
        elif increase_count > reduce_count:
            summary_parts.append(f"股东增持({increase_count}次)多于减持({reduce_count}次)，股东看好")

    # 扩张分析
    expansion_count = len(classified.get("投资并购", [])) + len(classified.get("子公司", []))
    if expansion_count > 5:
        summary_parts.append(f"有{expansion_count}次投资/扩张动作，公司处于扩张期")

    # 风险分析
    risk_count = len(classified.get("诉讼仲裁", [])) + len(classified.get("处罚", []))
    if risk_count > 0:
        summary_parts.append(f"有{risk_count}次诉讼/处罚公告，需关注风险")

    analysis["summary"] = "；".join(summary_parts) if summary_parts else "公告面无明显异常"

    return analysis
