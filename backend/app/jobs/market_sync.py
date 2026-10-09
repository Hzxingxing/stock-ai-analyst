import asyncio
import logging

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

from app.config import settings
from app.data.market_service import MarketDataService
from app.db.session import SessionFactory, engine

logging.basicConfig(level=getattr(logging, settings.log_level.upper(), logging.INFO))
logger = logging.getLogger(__name__)


async def refresh_market_data() -> None:
    service = MarketDataService(SessionFactory, None)
    bars = await service.refresh_core_indexes()
    try:
        overview = await service.get_market_overview()
    except Exception:
        logger.exception("Market breadth refresh failed")
    else:
        logger.info(
            "Stored %s core index bars and breadth for %s",
            bars,
            overview.get("trade_date"),
        )


async def main() -> None:
    scheduler = AsyncIOScheduler(timezone="Asia/Shanghai")
    scheduler.add_job(
        refresh_market_data,
        CronTrigger(day_of_week="mon-fri", hour=18, minute=20, timezone="Asia/Shanghai"),
        id="daily-core-market-data",
        coalesce=True,
        max_instances=1,
        misfire_grace_time=3600,
    )
    scheduler.start()
    try:
        await refresh_market_data()
        logger.info("Core market sync is scheduled for weekdays at 18:20 Asia/Shanghai")
        while True:
            await asyncio.sleep(3600)
    finally:
        scheduler.shutdown(wait=False)
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
