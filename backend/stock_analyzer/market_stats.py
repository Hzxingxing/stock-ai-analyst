"""市场整体统计数据获取模块"""
from datetime import datetime
import pandas as pd
import akshare as ak


def get_market_statistics() -> dict:
    """
    获取A股市场整体统计数据

    Returns:
        dict包含市场统计数据
    """
    try:
        # 获取所有A股实时数据
        df = ak.stock_zh_a_spot_em()

        if df is None or df.empty:
            return {}

        # 总股票数
        total_stocks = len(df)

        # 涨跌家数统计
        up_count = len(df[df['涨跌幅'] > 0])
        down_count = len(df[df['涨跌幅'] < 0])
        flat_count = len(df[df['涨跌幅'] == 0])

        # 涨停跌停（A股一般为±10%，科创板/创业板为±20%，简化为±9.9%阈值）
        limit_up_count = len(df[df['涨跌幅'] >= 9.9])
        limit_down_count = len(df[df['涨跌幅'] <= -9.9])

        # 总成交量和成交额
        total_volume = df['成交量'].sum()  # 手
        total_amount = df['成交额'].sum()  # 元

        # 涨跌幅分布
        up_over_7 = len(df[df['涨跌幅'] > 7])
        up_5_to_7 = len(df[(df['涨跌幅'] > 5) & (df['涨跌幅'] <= 7)])
        up_3_to_5 = len(df[(df['涨跌幅'] > 3) & (df['涨跌幅'] <= 5)])
        up_0_to_3 = len(df[(df['涨跌幅'] > 0) & (df['涨跌幅'] <= 3)])

        down_0_to_3 = len(df[(df['涨跌幅'] < 0) & (df['涨跌幅'] >= -3)])
        down_3_to_5 = len(df[(df['涨跌幅'] < -3) & (df['涨跌幅'] >= -5)])
        down_5_to_7 = len(df[(df['涨跌幅'] < -5) & (df['涨跌幅'] >= -7)])
        down_over_7 = len(df[df['涨跌幅'] < -7])

        return {
            "stat_date": datetime.now().date(),
            "total_stocks": total_stocks,
            "up_count": up_count,
            "down_count": down_count,
            "flat_count": flat_count,
            "limit_up_count": limit_up_count,
            "limit_down_count": limit_down_count,
            "total_volume": float(total_volume),
            "total_amount": float(total_amount),
            "up_over_7_count": up_over_7,
            "up_5_to_7_count": up_5_to_7,
            "up_3_to_5_count": up_3_to_5,
            "up_0_to_3_count": up_0_to_3,
            "down_0_to_3_count": down_0_to_3,
            "down_3_to_5_count": down_3_to_5,
            "down_5_to_7_count": down_5_to_7,
            "down_over_7_count": down_over_7
        }

    except Exception as e:
        print(f"获取市场统计失败: {e}")
        return {}
