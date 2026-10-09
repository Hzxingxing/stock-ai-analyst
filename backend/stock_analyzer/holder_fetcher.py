"""股东数据获取模块 - 通过AKShare获取股东变化数据"""

from datetime import datetime, date
from typing import Optional, List, Dict
import akshare as ak
import pandas as pd
import warnings

# 抑制FutureWarning
warnings.filterwarnings('ignore', category=FutureWarning)


def get_main_stock_holders(stock_code: str) -> Optional[pd.DataFrame]:
    """
    获取十大股东数据

    Args:
        stock_code: 股票代码，如 "000151"

    Returns:
        十大股东DataFrame
    """
    try:
        df = ak.stock_main_stock_holder(stock=stock_code)

        if df is None or df.empty:
            return None

        # 重命名列
        df = df.rename(columns={
            '编号': 'rank',
            '股东名称': 'holder_name',
            '持股数量': 'hold_num',
            '持股比例': 'hold_ratio',
            '股本性质': 'share_type',
            '截至日期': 'report_date',
            '公告日期': 'announce_date',
            '股东说明': 'holder_desc',
            '股东总数': 'total_holders',
            '平均持股数': 'avg_hold_num'
        })

        # 转换日期
        if 'report_date' in df.columns:
            df['report_date'] = pd.to_datetime(df['report_date'], errors='coerce').dt.date

        return df

    except Exception as e:
        print(f"获取股票 {stock_code} 十大股东数据失败: {e}")
        return None


def get_holder_count_change(stock_code: str) -> Optional[Dict]:
    """
    从十大股东数据中提取股东人数变化

    Args:
        stock_code: 股票代码

    Returns:
        股东人数变化字典
    """
    try:
        df = get_main_stock_holders(stock_code)
        if df is None or df.empty:
            return None

        # 获取不同报告期的股东总数
        holder_data = df[['report_date', 'total_holders', 'avg_hold_num']].drop_duplicates('report_date')
        holder_data = holder_data.sort_values('report_date', ascending=False)

        if len(holder_data) < 1:
            return None

        latest = holder_data.iloc[0]
        result = {
            "report_date": latest['report_date'],
            "total_holders": int(latest['total_holders']) if pd.notna(latest['total_holders']) else None,
            "avg_hold_num": float(latest['avg_hold_num']) if pd.notna(latest['avg_hold_num']) else None,
        }

        # 计算变化
        if len(holder_data) >= 2:
            prev = holder_data.iloc[1]
            if pd.notna(latest['total_holders']) and pd.notna(prev['total_holders']):
                change = int(latest['total_holders']) - int(prev['total_holders'])
                change_pct = (change / int(prev['total_holders'])) * 100 if prev['total_holders'] > 0 else 0
                result["holder_change"] = change
                result["holder_change_pct"] = round(change_pct, 2)
                result["prev_report_date"] = prev['report_date']
                result["prev_total_holders"] = int(prev['total_holders'])

                # 判断集中度变化
                if change < 0:
                    result["concentration_trend"] = "集中（股东减少）"
                elif change > 0:
                    result["concentration_trend"] = "分散（股东增加）"
                else:
                    result["concentration_trend"] = "稳定"
            else:
                result["concentration_trend"] = "数据不足"
        else:
            result["concentration_trend"] = "数据不足"

        return result

    except Exception as e:
        print(f"获取股票 {stock_code} 股东人数变化失败: {e}")
        return None


def get_top_holders_summary(stock_code: str) -> Optional[Dict]:
    """
    获取十大股东汇总信息

    Args:
        stock_code: 股票代码

    Returns:
        十大股东汇总
    """
    try:
        df = get_main_stock_holders(stock_code)
        if df is None or df.empty:
            return None

        # 获取最新一期数据
        latest_date = df['report_date'].max()
        latest_df = df[df['report_date'] == latest_date].head(10)

        if latest_df.empty:
            return None

        # 计算汇总
        total_hold_ratio = 0
        holders = []

        for _, row in latest_df.iterrows():
            hold_ratio = row.get('hold_ratio')
            if pd.notna(hold_ratio):
                # 处理百分比格式
                if isinstance(hold_ratio, str):
                    hold_ratio = float(hold_ratio.replace('%', ''))
                total_hold_ratio += float(hold_ratio)

            holders.append({
                "rank": row.get('rank'),
                "name": row.get('holder_name'),
                "hold_num": float(row.get('hold_num')) if pd.notna(row.get('hold_num')) else None,
                "hold_ratio": float(hold_ratio) if pd.notna(hold_ratio) else None,
                "share_type": row.get('share_type')
            })

        # 判断控股类型
        first_holder_ratio = holders[0]['hold_ratio'] if holders and holders[0]['hold_ratio'] else 0
        if first_holder_ratio >= 50:
            control_type = "绝对控股"
        elif first_holder_ratio >= 30:
            control_type = "相对控股"
        elif first_holder_ratio >= 20:
            control_type = "一般控股"
        else:
            control_type = "股权分散"

        result = {
            "report_date": latest_date,
            "top10_hold_ratio": round(total_hold_ratio, 2),
            "first_holder_name": holders[0]['name'] if holders else None,
            "first_holder_ratio": first_holder_ratio,
            "control_type": control_type,
            "holders": holders[:5],  # 只返回前5大股东
            "total_holders": int(latest_df['total_holders'].iloc[0]) if pd.notna(latest_df['total_holders'].iloc[0]) else None
        }

        return result

    except Exception as e:
        print(f"获取股票 {stock_code} 十大股东汇总失败: {e}")
        return None


if __name__ == "__main__":
    # 测试
    test_code = "000151"
    print(f"测试获取 {test_code} 股东数据:")

    # 股东人数变化
    holder_change = get_holder_count_change(test_code)
    if holder_change:
        print(f"  股东人数变化:")
        print(f"    报告期: {holder_change.get('report_date')}")
        print(f"    股东总数: {holder_change.get('total_holders')}")
        print(f"    变化: {holder_change.get('holder_change', 'N/A')}")
        print(f"    变化率: {holder_change.get('holder_change_pct', 'N/A')}%")
        print(f"    趋势: {holder_change.get('concentration_trend')}")

    print()

    # 十大股东汇总
    top_holders = get_top_holders_summary(test_code)
    if top_holders:
        print(f"  十大股东汇总:")
        print(f"    报告期: {top_holders.get('report_date')}")
        print(f"    十大股东合计持股: {top_holders.get('top10_hold_ratio')}%")
        print(f"    第一大股东: {top_holders.get('first_holder_name')}")
        print(f"    第一大股东持股: {top_holders.get('first_holder_ratio')}%")
        print(f"    控股类型: {top_holders.get('control_type')}")
        print(f"    股东总数: {top_holders.get('total_holders')}")
