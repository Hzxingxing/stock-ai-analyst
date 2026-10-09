"""估值指标获取模块 - 通过AKShare获取A股估值数据"""

from datetime import datetime, date
from typing import Optional, Dict
import akshare as ak
import pandas as pd


def _get_market_prefix(stock_code: str) -> str:
    """
    根据股票代码判断市场前缀

    Args:
        stock_code: 6位股票代码

    Returns:
        带市场前缀的代码，如 "SH600519" 或 "SZ000001"
    """
    if stock_code.startswith(('6', '9')):
        return f"SH{stock_code}"
    else:
        return f"SZ{stock_code}"


def get_stock_valuation(stock_code: str) -> Optional[Dict]:
    """
    获取单只股票的估值指标

    Args:
        stock_code: 股票代码，如 "600519" 或 "000001"

    Returns:
        估值指标字典，包含 pe_ttm, pb, ps_ttm, total_mv, circ_mv 等
    """
    try:
        # 转换为带市场前缀的代码
        symbol = _get_market_prefix(stock_code)

        # 使用雪球数据源获取实时行情（包含估值指标）
        df = ak.stock_individual_spot_xq(symbol=symbol)

        if df is None or df.empty:
            return None

        # 转换为字典便于访问
        data_dict = dict(zip(df['item'], df['value']))

        result = {
            "date": date.today(),
            "pe_ttm": float(data_dict.get("市盈率(TTM)")) if data_dict.get("市盈率(TTM)") is not None else None,
            "pe_static": float(data_dict.get("市盈率(静)")) if data_dict.get("市盈率(静)") is not None else None,
            "pb": float(data_dict.get("市净率")) if data_dict.get("市净率") is not None else None,
            "ps_ttm": None,  # 该接口不提供PS
            "total_mv": float(data_dict.get("资产净值/总市值")) if data_dict.get("资产净值/总市值") is not None else None,
            "circ_mv": float(data_dict.get("流通值")) if data_dict.get("流通值") is not None else None,
            "dividend_yield": float(data_dict.get("股息率(TTM)")) if data_dict.get("股息率(TTM)") is not None else None,
        }

        return result

    except Exception as e:
        print(f"获取股票 {stock_code} 估值数据失败: {e}")
        return None


def get_stock_industry(stock_code: str) -> Optional[str]:
    """
    获取股票所属行业

    Args:
        stock_code: 股票代码

    Returns:
        行业名称
    """
    try:
        # 获取股票所属行业
        df = ak.stock_individual_info_em(symbol=stock_code)

        if df is None or df.empty:
            return None

        # 查找行业信息
        industry_row = df[df["item"] == "行业"]
        if not industry_row.empty:
            return industry_row.iloc[0]["value"]

        return None

    except Exception as e:
        print(f"获取股票 {stock_code} 行业信息失败: {e}")
        return None


def get_industry_pe_pb(industry_name: str) -> Optional[Dict]:
    """
    获取行业平均PE和PB

    Args:
        industry_name: 行业名称

    Returns:
        包含 industry_pe, industry_pb 的字典
    """
    import time
    max_retries = 3

    for attempt in range(max_retries):
        try:
            # 获取行业成分股数据（包含PE/PB）
            df = ak.stock_board_industry_cons_em(symbol=industry_name)

            if df is None or df.empty:
                return None

            # 计算行业平均PE和PB
            pe_values = df["市盈率-动态"].dropna()
            pb_values = df["市净率"].dropna()

            # 过滤掉异常值（负数和超大值）
            pe_values = pe_values[(pe_values > 0) & (pe_values < 1000)]
            pb_values = pb_values[(pb_values > 0) & (pb_values < 100)]

            result = {
                "industry_pe": float(pe_values.median()) if not pe_values.empty else None,
                "industry_pb": float(pb_values.median()) if not pb_values.empty else None,
            }

            return result

        except Exception as e:
            print(f"获取行业 {industry_name} PE/PB失败 (尝试 {attempt + 1}/{max_retries}): {e}")
            if attempt < max_retries - 1:
                time.sleep(2)  # 等待2秒后重试

    return None


def get_full_valuation(stock_code: str) -> Optional[Dict]:
    """
    获取完整的估值数据（包含行业对比）

    Args:
        stock_code: 股票代码

    Returns:
        完整的估值数据字典
    """
    # 获取基础估值指标
    valuation = get_stock_valuation(stock_code)
    if not valuation:
        return None

    # 获取行业信息
    industry = get_stock_industry(stock_code)
    valuation["industry"] = industry

    # 获取行业平均PE/PB
    if industry:
        industry_data = get_industry_pe_pb(industry)
        if industry_data:
            valuation.update(industry_data)

    return valuation


if __name__ == "__main__":
    # 测试
    test_code = "600519"
    print(f"测试获取 {test_code} 估值数据:")

    valuation = get_full_valuation(test_code)
    if valuation:
        print(f"  日期: {valuation.get('date')}")
        print(f"  PE(TTM): {valuation.get('pe_ttm')}")
        print(f"  PE(静态): {valuation.get('pe_static')}")
        print(f"  PB: {valuation.get('pb')}")
        print(f"  PS(TTM): {valuation.get('ps_ttm')}")
        print(f"  总市值: {valuation.get('total_mv'):.2f}元" if valuation.get('total_mv') else "  总市值: N/A")
        print(f"  流通市值: {valuation.get('circ_mv'):.2f}元" if valuation.get('circ_mv') else "  流通市值: N/A")
        print(f"  股息率: {valuation.get('dividend_yield')}%")
        print(f"  行业: {valuation.get('industry')}")
        print(f"  行业PE: {valuation.get('industry_pe')}")
        print(f"  行业PB: {valuation.get('industry_pb')}")
    else:
        print("  获取失败")
