import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from redis.asyncio import Redis
from redis.exceptions import RedisError
from sqlalchemy import text

from app.api import auth, chat, market, research
from app.config import settings
from app.db.session import engine
from app.harness.checkpointer import ResearchAsyncMySaver

logging.basicConfig(level=getattr(logging, settings.log_level.upper(), logging.INFO))
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    redis = Redis.from_url(settings.redis_url, decode_responses=True, socket_connect_timeout=2)
    try:
        await redis.ping()
        app.state.redis = redis
        logger.info("Redis cache connected")
    except RedisError as exc:
        app.state.redis = None
        await redis.aclose()
        logger.warning(
            "Redis is unavailable; short-lived data requests will use the source directly (%s)",
            type(exc).__name__,
        )

    async with ResearchAsyncMySaver.from_conn_string(
        settings.async_database_url
    ) as checkpointer:
        await checkpointer.setup()
        app.state.checkpointer = checkpointer
        async with engine.connect() as connection:
            await connection.execute(text("SELECT 1"))
        logger.info("Research service started")
        try:
            yield
        finally:
            app.state.checkpointer = None
            if app.state.redis is not None:
                await redis.aclose()
            await engine.dispose()


app = FastAPI(
    title="A 股研究助手",
    description="以可核验行情和可追溯工具调用支持持续研究。",
    version="0.2.0",
    lifespan=lifespan,
)
app.include_router(auth.router, prefix="/api")
app.include_router(research.router, prefix="/api")
app.include_router(market.router, prefix="/api")
app.include_router(chat.router, prefix="/api")


@app.get("/health", tags=["system"])
async def health() -> dict[str, str]:
    return {"status": "ok", "service": "stock-ai-analyst"}


@app.get("/ready", tags=["system"])
async def ready() -> dict[str, str]:
    async with engine.connect() as connection:
        await connection.execute(text("SELECT 1"))
    return {"status": "ready"}
