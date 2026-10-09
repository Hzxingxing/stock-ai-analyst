#!/usr/bin/env python3
"""
重新同步新闻数据（使用增强的新闻获取功能）
"""
import sys
import os

# 添加项目根目录到Python路径
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from src.database.connection import get_db_session
from src.database.models import Stock, StockNews
from src.services.data_sync import DataSyncService
from src.utils.logger import get_logger

logger = get_logger(__name__)


def resync_all_news():
    """重新同步所有股票的新闻数据"""
    print("=" * 80)
    print("重新同步新闻数据")
    print("=" * 80)

    with get_db_session() as session:
        # 获取所有活跃股票
        stocks = session.query(Stock).filter_by(is_active=1).all()
        print(f"\n找到 {len(stocks)} 只活跃股票")

        service = DataSyncService()
        total_new_news = 0

        for stock in stocks:
            print(f"\n{'=' * 60}")
            print(f"正在同步: {stock.stock_code} {stock.stock_name}")
            print(f"{'=' * 60}")

            # 查看当前新闻数量
            current_count = session.query(StockNews).filter_by(
                stock_code=stock.stock_code
            ).count()
            print(f"  数据库现有新闻: {current_count} 条")

            # 同步新闻（limit=50）
            result = service.sync_stock_news(stock.stock_code, limit=50)

            if result['success']:
                new_count = result.get('count', 0)
                total_new_news += new_count
                print(f"  ✓ {result.get('message', '')}")

                # 查看更新后的新闻数量
                updated_count = session.query(StockNews).filter_by(
                    stock_code=stock.stock_code
                ).count()
                print(f"  更新后新闻总数: {updated_count} 条")
            else:
                print(f"  ✗ 失败: {result.get('message', '')}")

    print(f"\n{'=' * 80}")
    print(f"同步完成!")
    print(f"  共新增新闻: {total_new_news} 条")
    print(f"{'=' * 80}")


if __name__ == "__main__":
    try:
        resync_all_news()
    except Exception as e:
        logger.error(f"同步失败: {e}", exc_info=True)
        print(f"\n✗ 同步失败: {e}")
        sys.exit(1)
