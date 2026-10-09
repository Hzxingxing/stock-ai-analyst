"""
页面路由 - 提供HTML页面
"""
from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from pathlib import Path

from src.database.connection import get_db_session
from src.database.repository import StockRepository

# 配置模板
BASE_DIR = Path(__file__).parent.parent
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))

router = APIRouter()


@router.get("/dashboard", response_class=HTMLResponse)
async def dashboard(request: Request):
    """仪表板页面"""
    with get_db_session() as session:
        stocks = StockRepository.get_all_active_stocks(session)
        stock_count = len(stocks)

    return templates.TemplateResponse(
        "dashboard.html",
        {
            "request": request,
            "title": "仪表板",
            "stock_count": stock_count
        }
    )


@router.get("/stocks", response_class=HTMLResponse)
async def stocks_page(request: Request):
    """股票管理页面"""
    return templates.TemplateResponse(
        "stocks.html",
        {
            "request": request,
            "title": "股票管理"
        }
    )


@router.get("/stocks/{stock_code}", response_class=HTMLResponse)
async def stock_detail_page(request: Request, stock_code: str):
    """股票详情页面"""
    with get_db_session() as session:
        stock = StockRepository.get_stock_by_code(session, stock_code)

        if not stock:
            return templates.TemplateResponse(
                "error.html",
                {
                    "request": request,
                    "title": "错误",
                    "message": "股票不存在"
                },
                status_code=404
            )

        # 在session内提取所有需要的数据
        stock_data = {
            "stock_code": stock.stock_code,
            "stock_name": stock.stock_name,
            "market": stock.market,
            "is_active": stock.is_active,
            "created_at": stock.created_at.isoformat() if stock.created_at else None,
            "updated_at": stock.updated_at.isoformat() if stock.updated_at else None
        }

    return templates.TemplateResponse(
        "stock_detail.html",
        {
            "request": request,
            "title": f"{stock_data['stock_name']}({stock_data['stock_code']})",
            "stock": stock_data
        }
    )


@router.get("/reports", response_class=HTMLResponse)
async def reports_page(request: Request):
    """分析报告页面"""
    return templates.TemplateResponse(
        "reports.html",
        {
            "request": request,
            "title": "分析报告"
        }
    )


@router.get("/reports/{report_id}", response_class=HTMLResponse)
async def report_detail_page(request: Request, report_id: int):
    """报告详情页面"""
    return templates.TemplateResponse(
        "report_detail.html",
        {
            "request": request,
            "title": "分析报告详情",
            "report_id": report_id
        }
    )
