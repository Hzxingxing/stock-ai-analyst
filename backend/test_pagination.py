#!/usr/bin/env python3
"""
测试分页功能
"""
import sys
import os

# 添加项目根目录到Python路径
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from src.database.connection import get_db_session
from src.database.models import StockAnnouncement, StockNews
from sqlalchemy import desc


def test_pagination():
    """测试分页查询"""
    print("=" * 60)
    print("分页功能测试")
    print("=" * 60)

    with get_db_session() as session:
        # 1. 统计总数
        ann_total = session.query(StockAnnouncement).filter_by(stock_code='600519').count()
        news_total = session.query(StockNews).filter_by(stock_code='600519').count()

        print(f"\n【数据统计】")
        print(f"公告总数: {ann_total}")
        print(f"新闻总数: {news_total}")

        # 2. 测试公告分页
        print(f"\n【公告分页测试】")
        limit = 10

        for page_num in range(1, 4):  # 测试前3页
            offset = (page_num - 1) * limit

            announcements = session.query(StockAnnouncement).filter_by(
                stock_code='600519'
            ).order_by(desc(StockAnnouncement.announcement_date)).offset(offset).limit(limit).all()

            has_more = (offset + limit) < ann_total

            print(f"  第{page_num}页: offset={offset}, limit={limit}")
            print(f"    返回记录数: {len(announcements)}")
            print(f"    has_more: {has_more}")

            if announcements:
                print(f"    首条: {announcements[0].announcement_date} - {announcements[0].title[:30]}...")
                print(f"    末条: {announcements[-1].announcement_date} - {announcements[-1].title[:30]}...")

        # 3. 测试最后一页
        print(f"\n【最后一页测试】")
        last_page_num = (ann_total - 1) // limit + 1
        last_offset = (last_page_num - 1) * limit

        last_announcements = session.query(StockAnnouncement).filter_by(
            stock_code='600519'
        ).order_by(desc(StockAnnouncement.announcement_date)).offset(last_offset).limit(limit).all()

        has_more = (last_offset + limit) < ann_total

        print(f"  第{last_page_num}页(最后一页): offset={last_offset}, limit={limit}")
        print(f"    返回记录数: {len(last_announcements)}")
        print(f"    has_more: {has_more}")

        # 4. 模拟API响应
        print(f"\n【API响应示例】")

        # 第一页
        offset = 0
        announcements = session.query(StockAnnouncement).filter_by(
            stock_code='600519'
        ).order_by(desc(StockAnnouncement.announcement_date)).offset(offset).limit(limit).all()

        response = {
            "success": True,
            "data": [{"title": a.title[:40] + "..."} for a in announcements[:3]],
            "total": ann_total,
            "limit": limit,
            "offset": offset,
            "has_more": (offset + limit) < ann_total
        }

        print(f"  /api/stocks/600519/announcements?limit={limit}&offset={offset}")
        print(f"  {{")
        print(f"    \"success\": {response['success']},")
        print(f"    \"total\": {response['total']},")
        print(f"    \"limit\": {response['limit']},")
        print(f"    \"offset\": {response['offset']},")
        print(f"    \"has_more\": {response['has_more']},")
        print(f"    \"data\": [... {len(announcements)} 条记录 ...]")
        print(f"  }}")

        # 第二页
        offset = 10
        announcements = session.query(StockAnnouncement).filter_by(
            stock_code='600519'
        ).order_by(desc(StockAnnouncement.announcement_date)).offset(offset).limit(limit).all()

        response = {
            "success": True,
            "total": ann_total,
            "limit": limit,
            "offset": offset,
            "has_more": (offset + limit) < ann_total
        }

        print(f"\n  /api/stocks/600519/announcements?limit={limit}&offset={offset}")
        print(f"  {{")
        print(f"    \"success\": {response['success']},")
        print(f"    \"total\": {response['total']},")
        print(f"    \"limit\": {response['limit']},")
        print(f"    \"offset\": {response['offset']},")
        print(f"    \"has_more\": {response['has_more']},")
        print(f"    \"data\": [... {len(announcements)} 条记录 ...]")
        print(f"  }}")

        print(f"\n{'=' * 60}")
        print("✓ 分页功能测试完成!")
        print(f"{'=' * 60}")


if __name__ == "__main__":
    test_pagination()
