"""数据获取模块 - 通过AKShare获取A股数据"""

from datetime import datetime, timedelta
from typing import Optional

import akshare as ak
import pandas as pd


def get_stock_data(
    stock_code: str,
    days: int = 60,
    end_date: Optional[str] = None
) -> pd.DataFrame:
    """
    获取A股日K线数据

    Args:
        stock_code: 股票代码，如 "600519" 或 "000001"
        days: 获取最近多少个交易日的数据
        end_date: 结束日期，格式 "YYYYMMDD"，默认为今天

    Returns:
        DataFrame包含: date, open, high, low, close, volume
    """
    if end_date is None:
        end_date = datetime.now().strftime("%Y%m%d")

    # 计算开始日期（多取一些天数以确保有足够的交易日数据）
    start_date = (datetime.now() - timedelta(days=days * 2)).strftime("%Y%m%d")

    # 根据股票代码判断市场
    # 6开头为上海，0和3开头为深圳
    if stock_code.startswith("6"):
        symbol = f"sh{stock_code}"
    else:
        symbol = f"sz{stock_code}"

    # 获取日K线数据
    df = ak.stock_zh_a_hist(
        symbol=stock_code,
        period="daily",
        start_date=start_date,
        end_date=end_date,
        adjust="qfq"  # 前复权
    )

    # 重命名列
    df = df.rename(columns={
        "日期": "date",
        "开盘": "open",
        "最高": "high",
        "最低": "low",
        "收盘": "close",
        "成交量": "volume",
        "成交额": "amount",
        "涨跌幅": "pct_change",
        "涨跌额": "change",
        "换手率": "turnover"
    })

    # 只保留需要的列
    columns_to_keep = ["date", "open", "high", "low", "close", "volume", "pct_change"]
    df = df[[col for col in columns_to_keep if col in df.columns]]

    # 转换日期格式
    df["date"] = pd.to_datetime(df["date"])

    # 只取最近N个交易日
    df = df.tail(days).reset_index(drop=True)

    return df


def get_stock_name(stock_code: str) -> str:
    """
    获取股票名称

    Args:
        stock_code: 股票代码

    Returns:
        股票名称
    """
    try:
        # 获取股票列表
        stock_info = ak.stock_info_a_code_name()
        name = stock_info[stock_info["code"] == stock_code]["name"].values
        if len(name) > 0:
            return name[0]
    except Exception:
        pass
    return stock_code
