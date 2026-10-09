#!/usr/bin/env python3
"""
测试增强的新闻获取功能
"""
import sys
import os

# 添加项目根目录到Python路径
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from stock_analyzer.market_news import get_stock_news
from stock_analyzer.stock_info import get_stock_name


def test_enhanced_news():
    """测试增强的新闻获取"""
    stock_code = '600519'
    stock_name = get_stock_name(stock_code)

    print("=" * 80)
    print(f"测试增强的新闻获取功能")
    print(f"股票: {stock_code} {stock_name}")
    print("=" * 80)

    # 获取新闻（limit=50）
    print("\n正在获取新闻（limit=50）...")
    news_list = get_stock_news(stock_code, stock_name, limit=50)

    print(f"\n【结果统计】")
    print(f"  获取到新闻总数: {len(news_list)} 条")

    # 按来源统计
    sources = {}
    for news in news_list:
        source = news.get('source', '未知')
        sources[source] = sources.get(source, 0) + 1

    print(f"\n【按来源统计】")
    for source, count in sorted(sources.items(), key=lambda x: x[1], reverse=True):
        print(f"  {source}: {count} 条")

    # 显示前10条新闻
    print(f"\n【前10条新闻预览】")
    for i, news in enumerate(news_list[:10], 1):
        print(f"\n  {i}. [{news.get('source', 'N/A')}] {news.get('title', 'N/A')}")
        print(f"     日期: {news.get('date', 'N/A')}")
        content = news.get('content', '')
        if content:
            print(f"     内容: {content[:80]}...")

    # 日期范围
    if news_list:
        dates = [n.get('date', '') for n in news_list if n.get('date')]
        if dates:
            print(f"\n【日期范围】")
            print(f"  最新: {max(dates)}")
            print(f"  最旧: {min(dates)}")

    print("\n" + "=" * 80)
    print("✓ 测试完成!")
    print("=" * 80)


if __name__ == "__main__":
    test_enhanced_news()
