"""
清理数据库中的重复数据
"""
from src.database.connection import get_db_session
from src.database.models import StockAnnouncement, StockNews
from src.utils.logger import get_logger

logger = get_logger(__name__)


def cleanup_duplicate_news():
    """清理重复新闻"""
    with get_db_session() as session:
        # 查找所有新闻，按 (stock_code, news_date, title) 分组
        all_news = session.query(StockNews).order_by(
            StockNews.stock_code,
            StockNews.news_date,
            StockNews.title,
            StockNews.id
        ).all()

        seen = set()
        to_delete = []

        for news in all_news:
            key = (news.stock_code, news.news_date, news.title)
            if key in seen:
                to_delete.append(news)
            else:
                seen.add(key)

        if to_delete:
            logger.info(f"发现 {len(to_delete)} 条重复新闻，准备删除...")
            for news in to_delete:
                session.delete(news)
            session.commit()
            logger.success(f"成功删除 {len(to_delete)} 条重复新闻")
        else:
            logger.info("未发现重复新闻")

        return len(to_delete)


def cleanup_duplicate_announcements():
    """清理重复公告"""
    with get_db_session() as session:
        # 查找所有公告，按 (stock_code, announcement_date, title) 分组
        all_announcements = session.query(StockAnnouncement).order_by(
            StockAnnouncement.stock_code,
            StockAnnouncement.announcement_date,
            StockAnnouncement.title,
            StockAnnouncement.id
        ).all()

        seen = set()
        to_delete = []

        for announcement in all_announcements:
            key = (announcement.stock_code, announcement.announcement_date, announcement.title)
            if key in seen:
                to_delete.append(announcement)
            else:
                seen.add(key)

        if to_delete:
            logger.info(f"发现 {len(to_delete)} 条重复公告，准备删除...")
            for announcement in to_delete:
                session.delete(announcement)
            session.commit()
            logger.success(f"成功删除 {len(to_delete)} 条重复公告")
        else:
            logger.info("未发现重复公告")

        return len(to_delete)


if __name__ == "__main__":
    logger.info("开始清理重复数据...")

    news_deleted = cleanup_duplicate_news()
    announcement_deleted = cleanup_duplicate_announcements()

    logger.success(f"清理完成! 删除 {news_deleted} 条重复新闻, {announcement_deleted} 条重复公告")
