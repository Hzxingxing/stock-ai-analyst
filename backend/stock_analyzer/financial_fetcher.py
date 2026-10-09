"""财务数据获取模块 - 获取A股财务报表数据"""

from datetime import datetime
from typing import Optional
import pandas as pd
import akshare as ak


def get_em_symbol(stock_code: str) -> str:
    """
    转换股票代码为东方财富格式

    Args:
        stock_code: 股票代码，如 "600519"

    Returns:
        东方财富格式，如 "SH600519"
    """
    if stock_code.startswith("6"):
        return f"SH{stock_code}"
    else:
        return f"SZ{stock_code}"


def get_profit_sheet(stock_code: str, periods: int = 12) -> pd.DataFrame:
    """
    获取利润表数据

    Args:
        stock_code: 股票代码
        periods: 获取多少期数据

    Returns:
        利润表DataFrame
    """
    try:
        symbol = get_em_symbol(stock_code)
        df = ak.stock_profit_sheet_by_report_em(symbol=symbol)

        if df.empty:
            return pd.DataFrame()

        # 选择关键列
        key_columns = {
            "REPORT_DATE": "report_date",
            "TOTAL_OPERATE_INCOME": "revenue",           # 营业收入
            "OPERATE_INCOME": "operating_income",        # 营业收入(主营)
            "TOTAL_OPERATE_COST": "total_cost",          # 营业总成本
            "OPERATE_COST": "operating_cost",            # 营业成本
            "OPERATE_PROFIT": "operating_profit",        # 营业利润
            "TOTAL_PROFIT": "total_profit",              # 利润总额
            "NETPROFIT": "net_profit",                   # 净利润
            "PARENT_NETPROFIT": "net_profit_parent",     # 归母净利润
            "BASIC_EPS": "eps",                          # 基本每股收益
            "TOTAL_OPERATE_INCOME_YOY": "revenue_yoy",   # 营收同比
            "NETPROFIT_YOY": "net_profit_yoy",           # 净利润同比
        }

        # 筛选存在的列
        available_cols = {k: v for k, v in key_columns.items() if k in df.columns}
        df = df[list(available_cols.keys())].rename(columns=available_cols)

        # 转换日期
        df["report_date"] = pd.to_datetime(df["report_date"])
        df = df.sort_values("report_date", ascending=False).head(periods)

        return df.reset_index(drop=True)

    except Exception as e:
        print(f"获取利润表失败: {e}")
        return pd.DataFrame()


def get_balance_sheet(stock_code: str, periods: int = 12) -> pd.DataFrame:
    """
    获取资产负债表数据

    Args:
        stock_code: 股票代码
        periods: 获取多少期数据

    Returns:
        资产负债表DataFrame
    """
    try:
        symbol = get_em_symbol(stock_code)
        df = ak.stock_balance_sheet_by_report_em(symbol=symbol)

        if df.empty:
            return pd.DataFrame()

        key_columns = {
            "REPORT_DATE": "report_date",
            "TOTAL_ASSETS": "total_assets",              # 资产总计
            "TOTAL_LIABILITIES": "total_liabilities",    # 负债合计
            "TOTAL_EQUITY": "total_equity",              # 股东权益
            "TOTAL_CURRENT_ASSETS": "current_assets",    # 流动资产
            "TOTAL_NONCURRENT_ASSETS": "non_current_assets",  # 非流动资产
            "MONETARYFUNDS": "cash",                     # 货币资金
            "INVENTORY": "inventory",                    # 存货
            "ACCOUNTS_RECE": "accounts_receivable",      # 应收账款
            "TOTAL_CURRENT_LIAB": "current_liabilities", # 流动负债
        }

        available_cols = {k: v for k, v in key_columns.items() if k in df.columns}
        df = df[list(available_cols.keys())].rename(columns=available_cols)

        df["report_date"] = pd.to_datetime(df["report_date"])
        df = df.sort_values("report_date", ascending=False).head(periods)

        return df.reset_index(drop=True)

    except Exception as e:
        print(f"获取资产负债表失败: {e}")
        return pd.DataFrame()


def get_cash_flow_sheet(stock_code: str, periods: int = 12) -> pd.DataFrame:
    """
    获取现金流量表数据

    Args:
        stock_code: 股票代码
        periods: 获取多少期数据

    Returns:
        现金流量表DataFrame
    """
    try:
        symbol = get_em_symbol(stock_code)
        df = ak.stock_cash_flow_sheet_by_report_em(symbol=symbol)

        if df.empty:
            return pd.DataFrame()

        key_columns = {
            "REPORT_DATE": "report_date",
            "NETCASH_OPERATE": "cash_from_operating",     # 经营活动现金流净额
            "NETCASH_INVEST": "cash_from_investing",      # 投资活动现金流净额
            "NETCASH_FINANCE": "cash_from_financing",     # 筹资活动现金流净额
            "CCE_ADD": "net_cash_change",                 # 现金净增加额
            "BEGIN_CCE": "cash_begin",                    # 期初现金
            "END_CCE": "cash_end",                        # 期末现金
        }

        available_cols = {k: v for k, v in key_columns.items() if k in df.columns}
        df = df[list(available_cols.keys())].rename(columns=available_cols)

        df["report_date"] = pd.to_datetime(df["report_date"])
        df = df.sort_values("report_date", ascending=False).head(periods)

        return df.reset_index(drop=True)

    except Exception as e:
        print(f"获取现金流量表失败: {e}")
        return pd.DataFrame()


def get_financial_indicators(stock_code: str, start_year: int = 2022) -> pd.DataFrame:
    """
    获取关键财务指标

    Args:
        stock_code: 股票代码
        start_year: 起始年份

    Returns:
        财务指标DataFrame
    """
    try:
        df = ak.stock_financial_analysis_indicator(
            symbol=stock_code,
            start_year=str(start_year)
        )

        if df.empty:
            return pd.DataFrame()

        # 关键指标映射 (新浪财务指标列名带百分号)
        key_columns = {
            "日期": "report_date",
            "净资产收益率(%)": "roe",                     # ROE
            "加权净资产收益率(%)": "roe_weighted",
            "总资产利润率(%)": "roa",                     # ROA
            "销售净利率(%)": "net_profit_margin",         # 净利率
            "销售毛利率(%)": "gross_margin",              # 毛利率
            "资产负债率(%)": "debt_ratio",                # 资产负债率
            "流动比率": "current_ratio",                  # 流动比率
            "速动比率": "quick_ratio",                    # 速动比率
            "存货周转率(次)": "inventory_turnover",
            "应收账款周转率(次)": "receivable_turnover",
            "总资产周转率(次)": "asset_turnover",
            "每股净资产_调整前(元)": "bps",               # 每股净资产
            "摊薄每股收益(元)": "eps",                    # 每股收益
            "每股经营性现金流(元)": "cash_per_share",
            "主营业务收入增长率(%)": "revenue_growth",    # 收入增长率
            "净利润增长率(%)": "profit_growth",           # 利润增长率
        }

        available_cols = {k: v for k, v in key_columns.items() if k in df.columns}
        df = df[list(available_cols.keys())].rename(columns=available_cols)

        # 转换日期
        df["report_date"] = pd.to_datetime(df["report_date"])
        df = df.sort_values("report_date", ascending=False)

        return df.reset_index(drop=True)

    except Exception as e:
        print(f"获取财务指标失败: {e}")
        return pd.DataFrame()


def get_all_financial_data(stock_code: str, years: int = 3) -> dict:
    """
    获取所有财务数据

    Args:
        stock_code: 股票代码
        years: 年限

    Returns:
        包含所有财务数据的字典
    """
    # 获取更多期数以确保覆盖完整年限 (每年4个季度 + 额外buffer)
    periods = (years + 1) * 4
    start_year = datetime.now().year - years - 1  # 多获取一年数据确保完整

    return {
        "profit": get_profit_sheet(stock_code, periods),
        "balance": get_balance_sheet(stock_code, periods),
        "cash_flow": get_cash_flow_sheet(stock_code, periods),
        "indicators": get_financial_indicators(stock_code, start_year)
    }


def get_annual_reports(stock_code: str, years: int = 3) -> dict:
    """
    获取年度报告数据摘要

    Args:
        stock_code: 股票代码
        years: 年限

    Returns:
        年度报告数据
    """
    profit = get_profit_sheet(stock_code, (years + 1) * 4)

    if profit.empty:
        return {}

    # 筛选年报数据 (12月31日的报告)
    profit["report_date"] = pd.to_datetime(profit["report_date"])
    annual = profit[profit["report_date"].dt.month == 12].head(years)

    annual_data = []
    for _, row in annual.iterrows():
        year_data = {
            "year": row["report_date"].year,
            "revenue": row.get("revenue"),
            "net_profit": row.get("net_profit"),
            "eps": row.get("eps"),
            "revenue_yoy": row.get("revenue_yoy"),
            "net_profit_yoy": row.get("net_profit_yoy"),
        }
        annual_data.append(year_data)

    return {"annual": annual_data}
