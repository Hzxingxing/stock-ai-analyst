"""资金流向数据获取模块 - 通过AKShare获取个股资金流向数据"""

from datetime import datetime, date
from typing import Optional, List, Dict
import akshare as ak
import pandas as pd


def _get_market_code(stock_code: str) -> str:
    """
    根据股票代码判断市场代码

    Args:
        stock_code: 6位股票代码

    Returns:
        市场代码 'sh' 或 'sz'
    """
    if stock_code.startswith(('6', '9')):
        return 'sh'
    else:
        return 'sz'


def get_stock_fund_flow(stock_code: str, days: int = 30) -> Optional[pd.DataFrame]:
    """
    获取个股资金流向数据

    Args:
        stock_code: 股票代码，如 "000151"
        days: 获取天数

    Returns:
        资金流向DataFrame，包含日期、主力净流入、超大单、大单、中单、小单等
    """
    try:
        market = _get_market_code(stock_code)
        df = ak.stock_individual_fund_flow(stock=stock_code, market=market)

        if df is None or df.empty:
            return None

        # 重命名列，统一格式
        df = df.rename(columns={
            '日期': 'date',
            '收盘价': 'close_price',
            '涨跌幅': 'change_pct',
            '主力净流入-净额': 'main_net_inflow',
            '主力净流入-净占比': 'main_net_inflow_pct',
            '超大单净流入-净额': 'super_large_net_inflow',
            '超大单净流入-净占比': 'super_large_net_inflow_pct',
            '大单净流入-净额': 'large_net_inflow',
            '大单净流入-净占比': 'large_net_inflow_pct',
            '中单净流入-净额': 'medium_net_inflow',
            '中单净流入-净占比': 'medium_net_inflow_pct',
            '小单净流入-净额': 'small_net_inflow',
            '小单净流入-净占比': 'small_net_inflow_pct'
        })

        # 转换日期格式
        df['date'] = pd.to_datetime(df['date']).dt.date

        # 按日期降序排序，取最近N天
        df = df.sort_values('date', ascending=False).head(days)

        return df

    except Exception as e:
        print(f"获取股票 {stock_code} 资金流向数据失败: {e}")
        return None


def get_stock_fund_flow_summary(stock_code: str, days: int = 5) -> Optional[Dict]:
    """
    获取个股资金流向汇总数据

    Args:
        stock_code: 股票代码
        days: 汇总天数（默认5天）

    Returns:
        资金流向汇总字典
    """
    try:
        df = get_stock_fund_flow(stock_code, days=days)
        if df is None or df.empty:
            return None

        # 计算汇总数据
        summary = {
            "date": df['date'].max(),
            "days": len(df),
            # 主力资金
            "main_net_inflow_total": float(df['main_net_inflow'].sum()),
            "main_net_inflow_avg": float(df['main_net_inflow'].mean()),
            "main_net_inflow_pct_avg": float(df['main_net_inflow_pct'].mean()),
            # 超大单
            "super_large_net_inflow_total": float(df['super_large_net_inflow'].sum()),
            # 大单
            "large_net_inflow_total": float(df['large_net_inflow'].sum()),
            # 中单
            "medium_net_inflow_total": float(df['medium_net_inflow'].sum()),
            # 小单
            "small_net_inflow_total": float(df['small_net_inflow'].sum()),
            # 判断资金趋势
            "main_flow_trend": "流入" if df['main_net_inflow'].sum() > 0 else "流出",
            "retail_flow_trend": "流入" if df['small_net_inflow'].sum() > 0 else "流出",
        }

        # 判断主力与散户的背离情况
        main_direction = df['main_net_inflow'].sum() > 0
        retail_direction = df['small_net_inflow'].sum() > 0

        if main_direction and not retail_direction:
            summary["divergence"] = "主力吸筹（主力流入，散户流出）"
        elif not main_direction and retail_direction:
            summary["divergence"] = "主力出货（主力流出，散户流入）"
        elif main_direction and retail_direction:
            summary["divergence"] = "资金共同流入"
        else:
            summary["divergence"] = "资金共同流出"

        return summary

    except Exception as e:
        print(f"获取股票 {stock_code} 资金流向汇总失败: {e}")
        return None


def get_industry_fund_flow() -> Optional[pd.DataFrame]:
    """
    获取行业资金流向排名

    Returns:
        行业资金流向DataFrame
    """
    try:
        df = ak.stock_fund_flow_industry(symbol='即时')

        if df is None or df.empty:
            return None

        # 重命名列
        df = df.rename(columns={
            '序号': 'rank',
            '行业': 'industry',
            '行业指数': 'industry_index',
            '行业-涨跌幅': 'change_pct',
            '流入资金': 'inflow',
            '流出资金': 'outflow',
            '净额': 'net_inflow',
            '公司家数': 'company_count',
            '领涨股': 'leading_stock',
            '领涨股-涨跌幅': 'leading_stock_change_pct',
            '当前价': 'leading_stock_price'
        })

        return df

    except Exception as e:
        print(f"获取行业资金流向失败: {e}")
        return None


if __name__ == "__main__":
    # 测试
    test_code = "000151"
    print(f"测试获取 {test_code} 资金流向数据:")

    # 获取资金流向详情
    df = get_stock_fund_flow(test_code, days=5)
    if df is not None:
        print(f"  获取到 {len(df)} 条记录")
        print(df.head())

    print()

    # 获取汇总
    summary = get_stock_fund_flow_summary(test_code, days=5)
    if summary:
        print(f"  5日汇总:")
        print(f"    主力净流入: {summary['main_net_inflow_total']/10000:.2f}万")
        print(f"    资金趋势: {summary['main_flow_trend']}")
        print(f"    背离情况: {summary['divergence']}")
