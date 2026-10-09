"""报告生成模块 - 生成格式化的文本分析报告"""

from datetime import datetime
from typing import Optional


def format_number(value, decimals: int = 2) -> str:
    """格式化数字，处理None值"""
    if value is None:
        return "N/A"
    if isinstance(value, (int, float)):
        if abs(value) >= 1e8:
            return f"{value/1e8:.2f}亿"
        elif abs(value) >= 1e4:
            return f"{value/1e4:.2f}万"
        return f"{value:.{decimals}f}"
    return str(value)


def generate_report(
    stock_code: str,
    stock_name: str,
    indicators: dict,
    analysis: dict,
    days: int
) -> str:
    """
    生成完整的技术分析报告

    Args:
        stock_code: 股票代码
        stock_name: 股票名称
        indicators: 技术指标数据
        analysis: 分析结果
        days: 分析周期天数

    Returns:
        格式化的文本报告
    """
    sep = "=" * 50
    sub_sep = "-" * 50

    # 标题
    title = f"A股技术分析报告 - {stock_name}({stock_code})"
    header = f"""
{sep}
{title:^50}
{sep}
分析日期: {datetime.now().strftime('%Y-%m-%d %H:%M')}
数据周期: 最近{days}个交易日
"""

    # 价格信息
    pct_change = indicators.get("pct_change", 0)
    pct_str = f"+{pct_change:.2f}%" if pct_change >= 0 else f"{pct_change:.2f}%"

    price_section = f"""
{sub_sep}
【价格信息】
当前价格: {format_number(indicators['close'])}
涨跌幅: {pct_str}
今开: {format_number(indicators['open'])}  最高: {format_number(indicators['high'])}
最低: {format_number(indicators['low'])}  成交量: {format_number(indicators['volume'], 0)}
"""

    # 均线系统
    ma_section = f"""
{sub_sep}
【均线系统】
MA5:  {format_number(indicators.get('ma5'))}    MA10: {format_number(indicators.get('ma10'))}
MA20: {format_number(indicators.get('ma20'))}    MA60: {format_number(indicators.get('ma60'))}
趋势判断: {analysis['ma']['trend']}
分析: {analysis['ma']['description']}
"""

    # MACD
    macd_section = f"""
{sub_sep}
【MACD指标】
DIF: {format_number(indicators.get('dif'))}  DEA: {format_number(indicators.get('dea'))}  MACD柱: {format_number(indicators.get('macd'))}
信号: {analysis['macd']['signal']}
分析: {analysis['macd']['description']}
"""

    # KDJ
    kdj_section = f"""
{sub_sep}
【KDJ指标】
K: {format_number(indicators.get('k'))}  D: {format_number(indicators.get('d'))}  J: {format_number(indicators.get('j'))}
信号: {analysis['kdj']['signal']}
分析: {analysis['kdj']['description']}
"""

    # RSI
    rsi_section = f"""
{sub_sep}
【RSI指标】
RSI(14): {format_number(indicators.get('rsi'))}
信号: {analysis['rsi']['signal']}
分析: {analysis['rsi']['description']}
"""

    # 布林带
    boll_section = f"""
{sub_sep}
【布林带】
上轨: {format_number(indicators.get('boll_upper'))}
中轨: {format_number(indicators.get('boll_mid'))}
下轨: {format_number(indicators.get('boll_lower'))}
位置: {analysis['boll']['position']}
分析: {analysis['boll']['description']}
"""

    # OBV
    obv_section = f"""
{sub_sep}
【OBV能量潮】
当前OBV: {format_number(indicators.get('obv'), 0)}
趋势: {analysis['obv']['trend']}
分析: {analysis['obv']['description']}
"""

    # 综合研判
    summary_section = f"""
{sub_sep}
【综合研判】
{analysis['summary']}
{sep}
"""

    # 免责声明
    disclaimer = """
※ 以上分析仅供参考，不构成投资建议。
※ 股市有风险，投资需谨慎。
"""

    return (
        header +
        price_section +
        ma_section +
        macd_section +
        kdj_section +
        rsi_section +
        boll_section +
        obv_section +
        summary_section +
        disclaimer
    )


def print_report(report: str) -> None:
    """打印报告到控制台"""
    print(report)
