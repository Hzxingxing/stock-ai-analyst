"""技术指标计算模块"""

import pandas as pd
import pandas_ta as ta


def calculate_all_indicators(df: pd.DataFrame) -> pd.DataFrame:
    """
    计算所有技术指标

    Args:
        df: 包含 open, high, low, close, volume 的DataFrame

    Returns:
        添加了技术指标的DataFrame
    """
    df = df.copy()

    # 均线系统
    df = calculate_ma(df)

    # MACD
    df = calculate_macd(df)

    # RSI
    df = calculate_rsi(df)

    # KDJ
    df = calculate_kdj(df)

    # 布林带
    df = calculate_boll(df)

    # OBV
    df = calculate_obv(df)

    return df


def calculate_ma(df: pd.DataFrame) -> pd.DataFrame:
    """计算均线 MA5, MA10, MA20, MA60"""
    df["ma5"] = ta.sma(df["close"], length=5)
    df["ma10"] = ta.sma(df["close"], length=10)
    df["ma20"] = ta.sma(df["close"], length=20)
    df["ma60"] = ta.sma(df["close"], length=60)
    return df


def calculate_macd(df: pd.DataFrame) -> pd.DataFrame:
    """计算MACD指标: DIF, DEA, MACD柱"""
    macd = ta.macd(df["close"], fast=12, slow=26, signal=9)
    df["dif"] = macd["MACD_12_26_9"]
    df["dea"] = macd["MACDs_12_26_9"]
    df["macd"] = macd["MACDh_12_26_9"] * 2  # MACD柱（乘2是国内习惯）
    return df


def calculate_rsi(df: pd.DataFrame) -> pd.DataFrame:
    """计算RSI指标"""
    df["rsi"] = ta.rsi(df["close"], length=14)
    return df


def calculate_kdj(df: pd.DataFrame) -> pd.DataFrame:
    """计算KDJ指标"""
    stoch = ta.stoch(df["high"], df["low"], df["close"], k=9, d=3, smooth_k=3)
    df["k"] = stoch["STOCHk_9_3_3"]
    df["d"] = stoch["STOCHd_9_3_3"]
    df["j"] = 3 * df["k"] - 2 * df["d"]
    return df


def calculate_boll(df: pd.DataFrame) -> pd.DataFrame:
    """计算布林带"""
    bbands = ta.bbands(df["close"], length=20, std=2)
    # pandas_ta 新版本列名格式: BBU_20_2.0_2.0
    df["boll_upper"] = bbands["BBU_20_2.0_2.0"]
    df["boll_mid"] = bbands["BBM_20_2.0_2.0"]
    df["boll_lower"] = bbands["BBL_20_2.0_2.0"]
    return df


def calculate_obv(df: pd.DataFrame) -> pd.DataFrame:
    """计算OBV能量潮"""
    df["obv"] = ta.obv(df["close"], df["volume"])
    return df


def get_latest_indicators(df: pd.DataFrame) -> dict:
    """
    获取最新一天的所有指标值

    Returns:
        包含所有指标最新值的字典
    """
    latest = df.iloc[-1]
    prev = df.iloc[-2] if len(df) > 1 else latest

    return {
        # 价格信息
        "close": latest["close"],
        "open": latest["open"],
        "high": latest["high"],
        "low": latest["low"],
        "volume": latest["volume"],
        "pct_change": latest.get("pct_change", 0),

        # 均线
        "ma5": latest.get("ma5"),
        "ma10": latest.get("ma10"),
        "ma20": latest.get("ma20"),
        "ma60": latest.get("ma60"),

        # MACD
        "dif": latest.get("dif"),
        "dea": latest.get("dea"),
        "macd": latest.get("macd"),
        "prev_dif": prev.get("dif"),
        "prev_dea": prev.get("dea"),

        # RSI
        "rsi": latest.get("rsi"),

        # KDJ
        "k": latest.get("k"),
        "d": latest.get("d"),
        "j": latest.get("j"),
        "prev_k": prev.get("k"),
        "prev_d": prev.get("d"),

        # 布林带
        "boll_upper": latest.get("boll_upper"),
        "boll_mid": latest.get("boll_mid"),
        "boll_lower": latest.get("boll_lower"),

        # OBV
        "obv": latest.get("obv"),
        "prev_obv": prev.get("obv"),
    }
