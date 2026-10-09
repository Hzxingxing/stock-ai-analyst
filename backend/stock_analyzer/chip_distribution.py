"""筹码分布数据获取模块"""
from datetime import datetime
import pandas as pd
import akshare as ak


def get_chip_distribution(stock_code: str, days: int = None) -> pd.DataFrame:
    """
    获取筹码分布数据

    Args:
        stock_code: 股票代码
        days: 获取最近多少天的数据（默认None，返回所有数据）

    Returns:
        DataFrame包含: date, profit_ratio, avg_cost, cost_90_low, cost_90_high,
                      concentration_90, cost_70_low, cost_70_high, concentration_70
    """
    try:
        df = ak.stock_cyq_em(symbol=stock_code)

        if df is None or df.empty:
            return pd.DataFrame()

        # 重命名列为英文
        df = df.rename(columns={
            "日期": "date",
            "获利比例": "profit_ratio",
            "平均成本": "avg_cost",
            "90成本-低": "cost_90_low",
            "90成本-高": "cost_90_high",
            "90集中度": "concentration_90",
            "70成本-低": "cost_70_low",
            "70成本-高": "cost_70_high",
            "70集中度": "concentration_70"
        })

        # 转换日期格式
        df["date"] = pd.to_datetime(df["date"])

        # 如果指定了days参数，只取最近N天，否则返回所有数据
        if days is not None:
            df = df.tail(days).reset_index(drop=True)
        else:
            df = df.reset_index(drop=True)

        return df

    except Exception as e:
        print(f"获取筹码分布失败: {e}")
        return pd.DataFrame()
