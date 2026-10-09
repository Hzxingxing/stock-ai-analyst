"""行业对比数据获取模块 - 通过AKShare获取行业内股票排名对比"""

from datetime import datetime, date
from typing import Optional, List, Dict
import akshare as ak
import pandas as pd


def get_industry_stocks(industry_name: str) -> Optional[pd.DataFrame]:
    """
    获取行业成分股列表（含排名）

    Args:
        industry_name: 行业名称，如 "贸易行业"、"游戏"、"通信设备"

    Returns:
        行业成分股DataFrame，按涨跌幅排名
    """
    try:
        df = ak.stock_board_industry_cons_em(symbol=industry_name)

        if df is None or df.empty:
            return None

        # 重命名列
        df = df.rename(columns={
            '序号': 'rank',
            '代码': 'stock_code',
            '名称': 'stock_name',
            '最新价': 'price',
            '涨跌幅': 'change_pct',
            '涨跌额': 'change_amount',
            '成交量': 'volume',
            '成交额': 'turnover',
            '振幅': 'amplitude',
            '最高': 'high',
            '最低': 'low',
            '今开': 'open',
            '昨收': 'pre_close',
            '换手率': 'turnover_rate',
            '市盈率-动态': 'pe_ttm',
            '市净率': 'pb'
        })

        return df

    except Exception as e:
        print(f"获取行业 {industry_name} 成分股失败: {e}")
        return None


def get_stock_industry_rank(stock_code: str, industry_name: str) -> Optional[Dict]:
    """
    获取股票在行业内的排名

    Args:
        stock_code: 股票代码
        industry_name: 行业名称

    Returns:
        行业排名信息
    """
    try:
        df = get_industry_stocks(industry_name)
        if df is None or df.empty:
            return None

        total_stocks = len(df)

        # 找到该股票在行业中的位置
        stock_row = df[df['stock_code'] == stock_code]

        if stock_row.empty:
            return None

        stock_data = stock_row.iloc[0]

        # 计算各指标排名
        # 涨跌幅排名（已经按涨跌幅排序）
        change_rank = int(stock_data['rank'])

        # PE排名（从低到高）
        df_pe = df[df['pe_ttm'] > 0].sort_values('pe_ttm')
        pe_rank = None
        pe_percentile = None
        if stock_data['pe_ttm'] and stock_data['pe_ttm'] > 0:
            pe_rank_list = df_pe['stock_code'].tolist()
            if stock_code in pe_rank_list:
                pe_rank = pe_rank_list.index(stock_code) + 1
                pe_percentile = round((pe_rank / len(pe_rank_list)) * 100, 1)

        # PB排名（从低到高）
        df_pb = df[df['pb'] > 0].sort_values('pb')
        pb_rank = None
        pb_percentile = None
        if stock_data['pb'] and stock_data['pb'] > 0:
            pb_rank_list = df_pb['stock_code'].tolist()
            if stock_code in pb_rank_list:
                pb_rank = pb_rank_list.index(stock_code) + 1
                pb_percentile = round((pb_rank / len(pb_rank_list)) * 100, 1)

        # 换手率排名（从高到低）
        df_turnover = df.sort_values('turnover_rate', ascending=False)
        turnover_rank_list = df_turnover['stock_code'].tolist()
        turnover_rank = turnover_rank_list.index(stock_code) + 1 if stock_code in turnover_rank_list else None

        # 行业统计
        industry_avg_pe = float(df[df['pe_ttm'] > 0]['pe_ttm'].median()) if not df[df['pe_ttm'] > 0].empty else None
        industry_avg_pb = float(df[df['pb'] > 0]['pb'].median()) if not df[df['pb'] > 0].empty else None
        industry_avg_change = float(df['change_pct'].mean())

        result = {
            "industry": industry_name,
            "total_stocks": total_stocks,
            "stock_code": stock_code,
            "stock_name": stock_data['stock_name'],
            # 个股数据
            "price": float(stock_data['price']) if pd.notna(stock_data['price']) else None,
            "change_pct": float(stock_data['change_pct']) if pd.notna(stock_data['change_pct']) else None,
            "pe_ttm": float(stock_data['pe_ttm']) if pd.notna(stock_data['pe_ttm']) else None,
            "pb": float(stock_data['pb']) if pd.notna(stock_data['pb']) else None,
            "turnover_rate": float(stock_data['turnover_rate']) if pd.notna(stock_data['turnover_rate']) else None,
            # 排名信息
            "change_rank": change_rank,
            "change_percentile": round((change_rank / total_stocks) * 100, 1),
            "pe_rank": pe_rank,
            "pe_percentile": pe_percentile,
            "pb_rank": pb_rank,
            "pb_percentile": pb_percentile,
            "turnover_rank": turnover_rank,
            # 行业平均
            "industry_avg_pe": industry_avg_pe,
            "industry_avg_pb": industry_avg_pb,
            "industry_avg_change": industry_avg_change,
            # PE/PB对比
            "pe_vs_industry": "低估" if stock_data['pe_ttm'] and industry_avg_pe and stock_data['pe_ttm'] < industry_avg_pe else "高估" if stock_data['pe_ttm'] and industry_avg_pe else "N/A",
            "pb_vs_industry": "低估" if stock_data['pb'] and industry_avg_pb and stock_data['pb'] < industry_avg_pb else "高估" if stock_data['pb'] and industry_avg_pb else "N/A",
        }

        return result

    except Exception as e:
        print(f"获取股票 {stock_code} 行业排名失败: {e}")
        return None


def get_industry_top_stocks(industry_name: str, top_n: int = 5) -> Optional[List[Dict]]:
    """
    获取行业内排名前N的股票

    Args:
        industry_name: 行业名称
        top_n: 获取数量

    Returns:
        前N名股票列表
    """
    try:
        df = get_industry_stocks(industry_name)
        if df is None or df.empty:
            return None

        top_stocks = []
        for _, row in df.head(top_n).iterrows():
            top_stocks.append({
                "rank": int(row['rank']),
                "stock_code": row['stock_code'],
                "stock_name": row['stock_name'],
                "price": float(row['price']) if pd.notna(row['price']) else None,
                "change_pct": float(row['change_pct']) if pd.notna(row['change_pct']) else None,
                "pe_ttm": float(row['pe_ttm']) if pd.notna(row['pe_ttm']) else None,
                "pb": float(row['pb']) if pd.notna(row['pb']) else None,
            })

        return top_stocks

    except Exception as e:
        print(f"获取行业 {industry_name} Top股票失败: {e}")
        return None


def get_full_industry_comparison(stock_code: str, industry_name: str) -> Optional[Dict]:
    """
    获取完整的行业对比数据

    Args:
        stock_code: 股票代码
        industry_name: 行业名称

    Returns:
        完整行业对比数据
    """
    try:
        # 获取行业排名
        rank_info = get_stock_industry_rank(stock_code, industry_name)
        if not rank_info:
            return None

        # 获取行业Top5
        top_stocks = get_industry_top_stocks(industry_name, top_n=5)

        result = {
            **rank_info,
            "top_stocks": top_stocks,
            "analysis_date": date.today()
        }

        return result

    except Exception as e:
        print(f"获取完整行业对比失败: {e}")
        return None


if __name__ == "__main__":
    # 测试
    test_code = "000151"
    test_industry = "贸易行业"

    print(f"测试获取 {test_code} 在 {test_industry} 的排名:")

    rank_info = get_stock_industry_rank(test_code, test_industry)
    if rank_info:
        print(f"  行业: {rank_info.get('industry')}")
        print(f"  行业股票数: {rank_info.get('total_stocks')}")
        print(f"  涨跌幅排名: {rank_info.get('change_rank')}/{rank_info.get('total_stocks')} (前{rank_info.get('change_percentile')}%)")
        print(f"  PE排名: {rank_info.get('pe_rank')} (前{rank_info.get('pe_percentile')}%)")
        print(f"  PB排名: {rank_info.get('pb_rank')} (前{rank_info.get('pb_percentile')}%)")
        print(f"  PE对比行业: {rank_info.get('pe_vs_industry')}")
        print(f"  PB对比行业: {rank_info.get('pb_vs_industry')}")

    print()

    # 获取Top5
    top_stocks = get_industry_top_stocks(test_industry, top_n=5)
    if top_stocks:
        print(f"  {test_industry} Top 5:")
        for s in top_stocks:
            print(f"    {s['rank']}. {s['stock_name']}({s['stock_code']}) 涨跌{s['change_pct']}%")
