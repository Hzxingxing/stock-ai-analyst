"""分析引擎模块 - 生成技术分析结论"""

from typing import Optional
import pandas as pd


def analyze_ma_trend(indicators: dict) -> dict:
    """
    分析均线趋势

    Returns:
        {"trend": "多头/空头/震荡", "description": "分析描述"}
    """
    ma5 = indicators.get("ma5")
    ma10 = indicators.get("ma10")
    ma20 = indicators.get("ma20")
    ma60 = indicators.get("ma60")
    close = indicators.get("close")

    if None in [ma5, ma10, ma20]:
        return {"trend": "数据不足", "description": "均线数据不足，无法判断"}

    # 判断多头排列: MA5 > MA10 > MA20 > MA60
    if ma60 and ma5 > ma10 > ma20 > ma60:
        trend = "强势多头"
        desc = "均线多头排列，趋势向上"
    elif ma5 > ma10 > ma20:
        trend = "多头"
        desc = "短期均线多头排列，短期趋势向上"
    # 判断空头排列: MA5 < MA10 < MA20 < MA60
    elif ma60 and ma5 < ma10 < ma20 < ma60:
        trend = "强势空头"
        desc = "均线空头排列，趋势向下"
    elif ma5 < ma10 < ma20:
        trend = "空头"
        desc = "短期均线空头排列，短期趋势向下"
    else:
        trend = "震荡"
        desc = "均线交织，趋势不明确"

    # 判断价格与均线的关系
    if close > ma5:
        desc += "，价格站上5日均线"
    elif close < ma5:
        desc += "，价格跌破5日均线"

    return {"trend": trend, "description": desc}


def analyze_macd(indicators: dict) -> dict:
    """
    分析MACD指标

    Returns:
        {"signal": "金叉/死叉/...", "description": "分析描述"}
    """
    dif = indicators.get("dif")
    dea = indicators.get("dea")
    macd = indicators.get("macd")
    prev_dif = indicators.get("prev_dif")
    prev_dea = indicators.get("prev_dea")

    if None in [dif, dea, prev_dif, prev_dea]:
        return {"signal": "数据不足", "description": "MACD数据不足"}

    # 判断金叉/死叉
    if prev_dif <= prev_dea and dif > dea:
        if dif > 0:
            signal = "零轴上金叉"
            desc = "MACD在零轴上方金叉，强势买入信号"
        else:
            signal = "零轴下金叉"
            desc = "MACD在零轴下方金叉，反弹信号"
    elif prev_dif >= prev_dea and dif < dea:
        if dif < 0:
            signal = "零轴下死叉"
            desc = "MACD在零轴下方死叉，强势卖出信号"
        else:
            signal = "零轴上死叉"
            desc = "MACD在零轴上方死叉，回调信号"
    elif dif > dea:
        signal = "多头"
        desc = "DIF在DEA上方，多头动能"
        if macd > 0:
            desc += "，红柱放大"
    else:
        signal = "空头"
        desc = "DIF在DEA下方，空头动能"
        if macd < 0:
            desc += "，绿柱放大"

    return {"signal": signal, "description": desc}


def analyze_kdj(indicators: dict) -> dict:
    """
    分析KDJ指标

    Returns:
        {"signal": "超买/超卖/...", "description": "分析描述"}
    """
    k = indicators.get("k")
    d = indicators.get("d")
    j = indicators.get("j")
    prev_k = indicators.get("prev_k")
    prev_d = indicators.get("prev_d")

    if None in [k, d, j]:
        return {"signal": "数据不足", "description": "KDJ数据不足"}

    # 判断超买超卖
    if j > 100:
        signal = "严重超买"
        desc = "J值超过100，极度超买，注意回调风险"
    elif k > 80 and d > 80:
        signal = "超买"
        desc = "KD均在超买区(>80)，短期可能回调"
    elif j < 0:
        signal = "严重超卖"
        desc = "J值小于0，极度超卖，关注反弹机会"
    elif k < 20 and d < 20:
        signal = "超卖"
        desc = "KD均在超卖区(<20)，短期可能反弹"
    else:
        signal = "中性"
        desc = "KDJ处于中性区域"

    # 判断金叉/死叉
    if prev_k and prev_d:
        if prev_k <= prev_d and k > d:
            desc += "，KDJ金叉形成"
        elif prev_k >= prev_d and k < d:
            desc += "，KDJ死叉形成"

    return {"signal": signal, "description": desc}


def analyze_rsi(indicators: dict) -> dict:
    """
    分析RSI指标

    Returns:
        {"signal": "超买/超卖/...", "description": "分析描述"}
    """
    rsi = indicators.get("rsi")

    if rsi is None:
        return {"signal": "数据不足", "description": "RSI数据不足"}

    if rsi > 80:
        signal = "严重超买"
        desc = "RSI超过80，严重超买，回调概率大"
    elif rsi > 70:
        signal = "超买"
        desc = "RSI在70-80之间，超买区域"
    elif rsi < 20:
        signal = "严重超卖"
        desc = "RSI低于20，严重超卖，反弹概率大"
    elif rsi < 30:
        signal = "超卖"
        desc = "RSI在20-30之间，超卖区域"
    elif rsi > 50:
        signal = "偏强"
        desc = "RSI在50上方，多头占优"
    else:
        signal = "偏弱"
        desc = "RSI在50下方，空头占优"

    return {"signal": signal, "description": desc}


def analyze_boll(indicators: dict) -> dict:
    """
    分析布林带

    Returns:
        {"position": "上轨/中轨/下轨", "description": "分析描述"}
    """
    close = indicators.get("close")
    upper = indicators.get("boll_upper")
    mid = indicators.get("boll_mid")
    lower = indicators.get("boll_lower")

    if None in [close, upper, mid, lower]:
        return {"position": "数据不足", "description": "布林带数据不足"}

    # 计算价格在布林带中的位置
    band_width = upper - lower
    position_pct = (close - lower) / band_width * 100 if band_width > 0 else 50

    if close >= upper:
        position = "触及上轨"
        desc = "价格触及布林带上轨，短期可能承压"
    elif close <= lower:
        position = "触及下轨"
        desc = "价格触及布林带下轨，短期可能有支撑"
    elif close > mid:
        position = "中轨上方"
        desc = f"价格在中轨上方(位置{position_pct:.0f}%)，偏强运行"
    else:
        position = "中轨下方"
        desc = f"价格在中轨下方(位置{position_pct:.0f}%)，偏弱运行"

    return {"position": position, "description": desc}


def analyze_obv(indicators: dict, df: pd.DataFrame) -> dict:
    """
    分析OBV能量潮

    Returns:
        {"trend": "上升/下降", "description": "分析描述"}
    """
    obv = indicators.get("obv")
    prev_obv = indicators.get("prev_obv")
    close = indicators.get("close")

    if None in [obv, prev_obv]:
        return {"trend": "数据不足", "description": "OBV数据不足"}

    # 计算OBV趋势
    if len(df) >= 5:
        obv_5d_ago = df.iloc[-5].get("obv")
        close_5d_ago = df.iloc[-5].get("close")

        if obv_5d_ago and close_5d_ago:
            obv_change = obv - obv_5d_ago
            price_change = close - close_5d_ago

            if obv_change > 0 and price_change > 0:
                trend = "量价齐升"
                desc = "OBV与价格同步上涨，量价配合良好"
            elif obv_change < 0 and price_change < 0:
                trend = "量价齐跌"
                desc = "OBV与价格同步下跌，下跌趋势确认"
            elif obv_change > 0 and price_change < 0:
                trend = "底背离"
                desc = "价格下跌但OBV上升，可能见底信号"
            elif obv_change < 0 and price_change > 0:
                trend = "顶背离"
                desc = "价格上涨但OBV下降，可能见顶信号"
            else:
                trend = "持平"
                desc = "OBV变化不大"
        else:
            trend = "上升" if obv > prev_obv else "下降"
            desc = f"OBV{'上升' if obv > prev_obv else '下降'}"
    else:
        trend = "上升" if obv > prev_obv else "下降"
        desc = f"OBV{'上升' if obv > prev_obv else '下降'}"

    return {"trend": trend, "description": desc}


def generate_summary(
    ma_analysis: dict,
    macd_analysis: dict,
    kdj_analysis: dict,
    rsi_analysis: dict,
    boll_analysis: dict,
    obv_analysis: dict
) -> str:
    """
    生成综合研判

    Returns:
        综合分析结论字符串
    """
    bullish_signals = 0
    bearish_signals = 0

    # 均线趋势
    if ma_analysis["trend"] in ["强势多头", "多头"]:
        bullish_signals += 2 if "强势" in ma_analysis["trend"] else 1
    elif ma_analysis["trend"] in ["强势空头", "空头"]:
        bearish_signals += 2 if "强势" in ma_analysis["trend"] else 1

    # MACD信号
    if "金叉" in macd_analysis["signal"]:
        bullish_signals += 1
    elif "死叉" in macd_analysis["signal"]:
        bearish_signals += 1
    elif macd_analysis["signal"] == "多头":
        bullish_signals += 0.5
    elif macd_analysis["signal"] == "空头":
        bearish_signals += 0.5

    # KDJ信号
    if kdj_analysis["signal"] in ["超买", "严重超买"]:
        bearish_signals += 1
    elif kdj_analysis["signal"] in ["超卖", "严重超卖"]:
        bullish_signals += 1

    # RSI信号
    if rsi_analysis["signal"] in ["超买", "严重超买"]:
        bearish_signals += 0.5
    elif rsi_analysis["signal"] in ["超卖", "严重超卖"]:
        bullish_signals += 0.5

    # 布林带位置
    if boll_analysis["position"] == "触及上轨":
        bearish_signals += 0.5
    elif boll_analysis["position"] == "触及下轨":
        bullish_signals += 0.5

    # OBV背离
    if obv_analysis["trend"] == "底背离":
        bullish_signals += 1
    elif obv_analysis["trend"] == "顶背离":
        bearish_signals += 1

    # 生成结论
    summary_parts = []

    # 趋势判断
    if bullish_signals > bearish_signals + 1:
        summary_parts.append("综合指标偏多")
    elif bearish_signals > bullish_signals + 1:
        summary_parts.append("综合指标偏空")
    else:
        summary_parts.append("多空分歧，方向不明")

    # 关键信号提示
    if "金叉" in macd_analysis["signal"]:
        summary_parts.append("MACD金叉形成")
    elif "死叉" in macd_analysis["signal"]:
        summary_parts.append("MACD死叉形成")

    if kdj_analysis["signal"] in ["严重超买", "超买"]:
        summary_parts.append("KDJ超买注意回调")
    elif kdj_analysis["signal"] in ["严重超卖", "超卖"]:
        summary_parts.append("KDJ超卖关注反弹")

    if obv_analysis["trend"] == "顶背离":
        summary_parts.append("量价顶背离需警惕")
    elif obv_analysis["trend"] == "底背离":
        summary_parts.append("量价底背离可关注")

    # 操作建议
    if bullish_signals > bearish_signals + 2:
        summary_parts.append("建议：可适当关注")
    elif bearish_signals > bullish_signals + 2:
        summary_parts.append("建议：谨慎观望")
    else:
        summary_parts.append("建议：观望为主")

    return "。".join(summary_parts) + "。"


def run_full_analysis(indicators: dict, df: pd.DataFrame) -> dict:
    """
    运行完整的技术分析

    Returns:
        包含所有分析结果的字典
    """
    ma_analysis = analyze_ma_trend(indicators)
    macd_analysis = analyze_macd(indicators)
    kdj_analysis = analyze_kdj(indicators)
    rsi_analysis = analyze_rsi(indicators)
    boll_analysis = analyze_boll(indicators)
    obv_analysis = analyze_obv(indicators, df)

    summary = generate_summary(
        ma_analysis, macd_analysis, kdj_analysis,
        rsi_analysis, boll_analysis, obv_analysis
    )

    return {
        "ma": ma_analysis,
        "macd": macd_analysis,
        "kdj": kdj_analysis,
        "rsi": rsi_analysis,
        "boll": boll_analysis,
        "obv": obv_analysis,
        "summary": summary
    }
