"""
FastAPI Web应用主入口
"""
import asyncio
from pathlib import Path

# 加载环境变量（必须在其他导入之前）
from dotenv import load_dotenv
env_path = Path(__file__).parent.parent.parent / '.env'
load_dotenv(env_path)

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from src.web.routes import pages, api
from src.web.routes import reports_api
from src.services.stock_search import get_stock_search_service
from src.utils.logger import get_logger

logger = get_logger(__name__)

# 创建FastAPI应用
app = FastAPI(
    title="股票AI分析系统",
    description="集成AKShare数据、Gemini分析、Claude汇总的自动化投资分析平台",
    version="1.0.0"
)

# 获取项目路径
BASE_DIR = Path(__file__).parent

# 挂载静态文件
app.mount("/static", StaticFiles(directory=str(BASE_DIR / "static")), name="static")

# 配置模板
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))

# 注册路由
app.include_router(pages.router, tags=["Pages"])
app.include_router(api.router, prefix="/api", tags=["API"])
app.include_router(reports_api.router, prefix="/api", tags=["Reports"])


@app.on_event("startup")
async def startup_event():
    """应用启动事件 - 预加载股票列表"""
    logger.info("应用启动中...")

    # 在后台线程预加载股票列表
    def preload_stocks():
        try:
            service = get_stock_search_service()
            service.preload()
        except Exception as e:
            logger.error(f"预加载股票列表失败: {e}")

    # 异步执行预加载
    asyncio.create_task(asyncio.to_thread(preload_stocks))
    logger.info("股票列表正在后台加载...")


@app.get("/")
async def root():
    """根路径重定向到仪表板"""
    from fastapi.responses import RedirectResponse
    return RedirectResponse(url="/dashboard")


@app.get("/health")
async def health_check():
    """健康检查"""
    return {"status": "ok", "service": "stock-ai-analyst"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000, reload=True)
