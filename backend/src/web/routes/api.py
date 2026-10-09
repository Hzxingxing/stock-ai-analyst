"""
API路由 - 提供RESTful API接口
"""
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from typing import List, Optional
from datetime import date, datetime
from sqlalchemy import desc
import json

from src.database.connection import get_db_session
from src.database.repository import StockRepository, AnalysisRepository, KLineRepository
from src.database.models import Stock, GeminiAnalysis, StockKLine, StockFinancial, StockAnnouncement, StockNews, StockChipDistribution, StockValuation, StockFundFlow, StockHolder
from src.services.stock_search import get_stock_search_service
from src.services.data_sync import get_data_sync_service
from pydantic import BaseModel

router = APIRouter()


# ========== Pydantic模型 ==========

class StockSearchRequest(BaseModel):
    keyword: str
    limit: int = 20


class StockCreateRequest(BaseModel):
    stock_code: str
    stock_name: str
    market: str


class StockUpdateRequest(BaseModel):
    stock_name: Optional[str] = None
    is_active: Optional[int] = None


class StockResponse(BaseModel):
    stock_code: str
    stock_name: str
    market: str
    is_active: int
    created_at: str
    updated_at: str

    class Config:
        from_attributes = True


# ========== 股票搜索API ==========

@router.post("/stocks/search")
async def search_stocks_from_market(request: StockSearchRequest):
    """
    从市场搜索股票(AKShare)

    Args:
        request: 搜索请求

    Returns:
        股票列表
    """
    try:
        service = get_stock_search_service()
        results = service.search_stocks(request.keyword, request.limit)
        return {
            "success": True,
            "data": results,
            "count": len(results)
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/stocks/info/{stock_code}")
async def get_stock_info_from_market(stock_code: str):
    """
    从市场获取股票信息(AKShare)

    Args:
        stock_code: 股票代码

    Returns:
        股票信息
    """
    try:
        service = get_stock_search_service()
        info = service.get_stock_info(stock_code)

        if not info:
            raise HTTPException(status_code=404, detail="股票不存在")

        return {
            "success": True,
            "data": info
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ========== 股票管理API ==========

@router.get("/stocks")
async def list_stocks(
    keyword: Optional[str] = None,
    market: Optional[str] = None,
    is_active: Optional[int] = None
):
    """
    获取股票列表

    Args:
        keyword: 搜索关键词
        market: 市场(SH/SZ)
        is_active: 是否启用

    Returns:
        股票列表
    """
    try:
        import json

        with get_db_session() as session:
            if keyword or market:
                stocks = StockRepository.search_stocks(session, keyword, market)
            else:
                # 返回所有股票（包括已停用的），便于管理
                stocks = session.query(Stock).order_by(desc(Stock.created_at)).all()

            # 如果明确传入is_active参数，则按参数过滤
            if is_active is not None:
                stocks = [s for s in stocks if s.is_active == is_active]

            # 构建返回数据，包含增强信息
            result_data = []
            for s in stocks:
                # 获取最新分析
                latest_analysis = session.query(GeminiAnalysis).filter_by(
                    stock_code=s.stock_code
                ).order_by(desc(GeminiAnalysis.analysis_date)).first()

                # 解析分析结果
                analysis_info = None
                if latest_analysis:
                    try:
                        analysis_result = json.loads(latest_analysis.analysis_result) if isinstance(latest_analysis.analysis_result, str) else latest_analysis.analysis_result
                        analysis_info = {
                            "technical_score": analysis_result.get("technical_score"),
                            "fundamental_score": analysis_result.get("fundamental_score"),
                            "suggestion": analysis_result.get("suggestion"),
                            "risk_level": analysis_result.get("risk_level")
                        }
                    except:
                        analysis_info = None

                # 统计数据量
                kline_count = session.query(StockKLine).filter_by(stock_code=s.stock_code).count()
                financial_count = session.query(StockFinancial).filter_by(stock_code=s.stock_code).count()

                result_data.append({
                    "stock_code": s.stock_code,
                    "stock_name": s.stock_name,
                    "market": s.market,
                    "is_active": s.is_active,
                    "created_at": s.created_at.isoformat() if s.created_at else None,
                    "updated_at": s.updated_at.isoformat() if s.updated_at else None,
                    "latest_analysis_date": latest_analysis.analysis_date.strftime('%Y-%m-%d') if latest_analysis else None,
                    "latest_analysis": analysis_info,
                    "kline_count": kline_count,
                    "financial_count": financial_count
                })

            return {
                "success": True,
                "data": result_data,
                "count": len(result_data)
            }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/stocks")
async def create_stock(request: StockCreateRequest):
    """
    添加股票到分析列表

    Args:
        request: 股票信息

    Returns:
        创建的股票
    """
    try:
        with get_db_session() as session:
            # 检查是否已存在
            existing = StockRepository.get_stock_by_code(session, request.stock_code)
            if existing:
                if existing.is_active == 0:
                    # 重新启用
                    existing.is_active = 1
                    session.commit()
                    return {
                        "success": True,
                        "message": "股票已存在,已重新启用",
                        "data": {
                            "stock_code": existing.stock_code,
                            "stock_name": existing.stock_name,
                            "market": existing.market,
                            "is_active": existing.is_active
                        }
                    }
                else:
                    raise HTTPException(status_code=400, detail="股票已存在于分析列表")

            # 创建新股票
            stock = StockRepository.create_stock(
                session,
                request.stock_code,
                request.stock_name,
                request.market
            )

            return {
                "success": True,
                "message": "股票添加成功",
                "data": {
                    "stock_code": stock.stock_code,
                    "stock_name": stock.stock_name,
                    "market": stock.market,
                    "is_active": stock.is_active
                }
            }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/stocks/{stock_code}")
async def update_stock(stock_code: str, request: StockUpdateRequest):
    """
    更新股票信息

    Args:
        stock_code: 股票代码
        request: 更新请求

    Returns:
        更新后的股票
    """
    try:
        with get_db_session() as session:
            update_data = request.model_dump(exclude_unset=True)

            if not update_data:
                raise HTTPException(status_code=400, detail="没有要更新的字段")

            stock = StockRepository.update_stock(session, stock_code, **update_data)

            if not stock:
                raise HTTPException(status_code=404, detail="股票不存在")

            return {
                "success": True,
                "message": "股票更新成功",
                "data": {
                    "stock_code": stock.stock_code,
                    "stock_name": stock.stock_name,
                    "market": stock.market,
                    "is_active": stock.is_active
                }
            }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/stocks/{stock_code}")
async def delete_stock(stock_code: str):
    """
    删除股票(软删除)

    Args:
        stock_code: 股票代码

    Returns:
        删除结果
    """
    try:
        with get_db_session() as session:
            success = StockRepository.delete_stock(session, stock_code)

            if not success:
                raise HTTPException(status_code=404, detail="股票不存在")

            return {
                "success": True,
                "message": "股票已移出分析列表"
            }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/stocks/{stock_code}")
async def get_stock_detail(stock_code: str):
    """
    获取股票详情

    Args:
        stock_code: 股票代码

    Returns:
        股票详情
    """
    try:
        with get_db_session() as session:
            stock = StockRepository.get_stock_by_code(session, stock_code)

            if not stock:
                raise HTTPException(status_code=404, detail="股票不存在")

            return {
                "success": True,
                "data": {
                    "stock_code": stock.stock_code,
                    "stock_name": stock.stock_name,
                    "market": stock.market,
                    "is_active": stock.is_active,
                    "created_at": stock.created_at.isoformat() if stock.created_at else None,
                    "updated_at": stock.updated_at.isoformat() if stock.updated_at else None
                }
            }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ========== 管理API ==========

@router.post("/admin/refresh-cache")
async def refresh_stock_cache():
    """
    刷新股票列表缓存（强制从AKShare重新获取）

    Returns:
        刷新结果
    """
    try:
        service = get_stock_search_service()
        service.refresh_cache()

        # 立即重新加载
        service.preload()

        return {
            "success": True,
            "message": "股票列表缓存已刷新，正在后台重新加载..."
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ========== K线数据API ==========

@router.get("/stocks/{stock_code}/klines")
async def get_stock_klines(
    stock_code: str,
    days: int = Query(default=60, ge=1, le=365)
):
    """
    获取股票K线数据

    Args:
        stock_code: 股票代码
        days: 获取天数（默认60天）

    Returns:
        K线数据，格式化为ECharts可用的数据结构
    """
    try:
        with get_db_session() as session:
            klines = KLineRepository.get_recent_klines(session, stock_code, days)

            if not klines:
                return {
                    "success": False,
                    "message": "暂无K线数据"
                }

            # 反转数据（从旧到新）
            klines = list(reversed(klines))

            # 格式化为ECharts需要的格式
            dates = [k.date.strftime('%Y-%m-%d') for k in klines]
            values = [[k.open, k.close, k.low, k.high] for k in klines]
            volumes = [k.volume for k in klines]

            # 移动平均线
            ma5 = [k.ma5 for k in klines]
            ma10 = [k.ma10 for k in klines]
            ma20 = [k.ma20 for k in klines]
            ma60 = [k.ma60 for k in klines]

            return {
                "success": True,
                "data": {
                    "dates": dates,
                    "values": values,
                    "volumes": volumes,
                    "ma5": ma5,
                    "ma10": ma10,
                    "ma20": ma20,
                    "ma60": ma60
                }
            }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ========== AI分析API ==========

@router.get("/stocks/{stock_code}/analysis")
async def get_stock_analysis(
    stock_code: str,
    analysis_date: Optional[str] = Query(default=None)
):
    """
    获取股票AI分析结果

    Args:
        stock_code: 股票代码
        analysis_date: 分析日期（可选，默认最新）

    Returns:
        分析结果
    """
    try:
        with get_db_session() as session:
            if analysis_date:
                # 获取指定日期的分析
                target_date = datetime.strptime(analysis_date, '%Y-%m-%d').date()
                analysis = AnalysisRepository.get_analysis_by_date(session, stock_code, target_date)
            else:
                # 获取最新分析
                analysis = session.query(GeminiAnalysis).filter(
                    GeminiAnalysis.stock_code == stock_code
                ).order_by(desc(GeminiAnalysis.analysis_date)).first()

            if not analysis:
                return {
                    "success": False,
                    "message": "暂无分析数据"
                }

            return {
                "success": True,
                "data": {
                    "stock_code": analysis.stock_code,
                    "analysis_date": analysis.analysis_date.strftime('%Y-%m-%d'),
                    "model_name": analysis.model_name,
                    "analysis_result": analysis.analysis_result,
                    "created_at": analysis.created_at.isoformat()
                }
            }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/stocks/{stock_code}/analyze")
async def analyze_stock(stock_code: str):
    """
    触发单只股票的AI分析

    Args:
        stock_code: 股票代码

    Returns:
        分析状态
    """
    try:
        with get_db_session() as session:
            # 检查股票是否存在
            stock = StockRepository.get_stock_by_code(session, stock_code)
            if not stock:
                raise HTTPException(status_code=404, detail="股票不存在")

            # 检查是否有K线数据
            klines = KLineRepository.get_recent_klines(session, stock_code, 60)
            if not klines:
                return {
                    "success": False,
                    "message": "暂无K线数据，请先更新股票数据"
                }

        # 调用Gemini分析服务
        from src.services.gemini_analyzer import get_gemini_analyzer

        analyzer = get_gemini_analyzer()
        result = analyzer.analyze_stock(stock_code)

        return result

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ========== 数据同步API ==========

@router.post("/stocks/{stock_code}/sync")
async def sync_stock_data(
    stock_code: str,
    days: int = Query(default=250, ge=1, le=365),
    years: int = Query(default=5, ge=1, le=10)
):
    """
    同步单只股票的所有数据

    Args:
        stock_code: 股票代码
        days: K线获取天数
        years: 公告/财务获取年限（默认5年）

    Returns:
        同步结果
    """
    try:
        service = get_data_sync_service()
        result = service.sync_all_data(stock_code, days, years)

        if not result["success"]:
            return result

        return result

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ========== 财务数据API ==========

@router.get("/stocks/{stock_code}/financials")
async def get_stock_financials(
    stock_code: str,
    limit: int = Query(default=8, ge=1, le=20)
):
    """
    获取股票财务数据

    Args:
        stock_code: 股票代码
        limit: 获取条数

    Returns:
        财务数据列表
    """
    try:
        from src.database.models import StockFinancial

        with get_db_session() as session:
            financials = session.query(StockFinancial).filter_by(
                stock_code=stock_code
            ).order_by(desc(StockFinancial.report_date)).limit(limit).all()

            if not financials:
                return {"success": False, "message": "暂无财务数据"}

            data = []
            for f in financials:
                data.append({
                    "report_date": f.report_date.strftime('%Y-%m-%d'),
                    "revenue": f.revenue,
                    "net_profit": f.net_profit,
                    "eps": f.eps,
                    "roe": f.roe,
                    "debt_ratio": f.debt_ratio
                })

            return {"success": True, "data": data}

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ========== 公告数据API ==========

@router.get("/stocks/{stock_code}/announcements")
async def get_stock_announcements(
    stock_code: str,
    limit: int = Query(default=10, ge=1, le=50),
    offset: int = Query(default=0, ge=0)
):
    """
    获取股票公告

    Args:
        stock_code: 股票代码
        limit: 获取条数
        offset: 偏移量（用于分页）

    Returns:
        公告列表（包含总数和分页信息）
    """
    try:
        from src.database.models import StockAnnouncement

        with get_db_session() as session:
            # 获取总数
            total = session.query(StockAnnouncement).filter_by(
                stock_code=stock_code
            ).count()

            if total == 0:
                return {"success": False, "message": "暂无公告数据", "total": 0}

            # 获取分页数据
            announcements = session.query(StockAnnouncement).filter_by(
                stock_code=stock_code
            ).order_by(desc(StockAnnouncement.announcement_date)).offset(offset).limit(limit).all()

            data = []
            for a in announcements:
                data.append({
                    "announcement_date": a.announcement_date.strftime('%Y-%m-%d'),
                    "announcement_type": a.announcement_type,
                    "title": a.title,
                    "content": a.content,
                    "url": a.url
                })

            return {
                "success": True,
                "data": data,
                "total": total,
                "limit": limit,
                "offset": offset,
                "has_more": (offset + limit) < total
            }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ========== 新闻数据API ==========

@router.get("/stocks/{stock_code}/news")
async def get_stock_news(
    stock_code: str,
    limit: int = Query(default=10, ge=1, le=50),
    offset: int = Query(default=0, ge=0)
):
    """
    获取股票新闻

    Args:
        stock_code: 股票代码
        limit: 获取条数
        offset: 偏移量（用于分页）

    Returns:
        新闻列表（包含总数和分页信息）
    """
    try:
        from src.database.models import StockNews

        with get_db_session() as session:
            # 获取总数
            total = session.query(StockNews).filter_by(
                stock_code=stock_code
            ).count()

            if total == 0:
                return {"success": False, "message": "暂无新闻数据", "total": 0}

            # 获取分页数据
            news_list = session.query(StockNews).filter_by(
                stock_code=stock_code
            ).order_by(desc(StockNews.news_date)).offset(offset).limit(limit).all()

            data = []
            for n in news_list:
                data.append({
                    "news_date": n.news_date.strftime('%Y-%m-%d'),
                    "news_type": n.news_type,
                    "title": n.title,
                    "content": n.content,
                    "source": n.source,
                    "url": n.url,
                    "sentiment": n.sentiment
                })

            return {
                "success": True,
                "data": data,
                "total": total,
                "limit": limit,
                "offset": offset,
                "has_more": (offset + limit) < total
            }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ========== 资讯合集API（公告+新闻） ==========

@router.get("/stocks/{stock_code}/info-feed")
async def get_stock_info_feed(
    stock_code: str,
    limit: int = Query(default=20, ge=1, le=50),
    offset: int = Query(default=0, ge=0)
):
    """
    获取股票资讯合集（公告+新闻混合，按时间倒序）

    Args:
        stock_code: 股票代码
        limit: 获取条数
        offset: 偏移量（用于懒加载分页）

    Returns:
        资讯列表（包含总数和分页信息）
    """
    try:
        from src.database.models import StockAnnouncement, StockNews
        from datetime import datetime

        with get_db_session() as session:
            # 获取公告数据
            announcements = session.query(StockAnnouncement).filter_by(
                stock_code=stock_code
            ).all()

            # 获取新闻数据
            news_list = session.query(StockNews).filter_by(
                stock_code=stock_code
            ).all()

            # 合并数据并添加类型标识
            combined_data = []

            for a in announcements:
                combined_data.append({
                    "type": "announcement",
                    "date": a.announcement_date,
                    "date_str": a.announcement_date.strftime('%Y-%m-%d'),
                    "category": a.announcement_type,
                    "title": a.title,
                    "content": a.content,
                    "url": a.url,
                    "sentiment": None
                })

            for n in news_list:
                combined_data.append({
                    "type": "news",
                    "date": n.news_date,
                    "date_str": n.news_date.strftime('%Y-%m-%d'),
                    "category": n.news_type,
                    "title": n.title,
                    "content": n.content,
                    "url": n.url,
                    "sentiment": n.sentiment
                })

            # 按日期倒序排序
            combined_data.sort(key=lambda x: x["date"], reverse=True)

            # 移除临时date字段（仅用于排序）
            for item in combined_data:
                del item["date"]

            # 计算总数和分页
            total = len(combined_data)
            paginated_data = combined_data[offset:offset + limit]

            return {
                "success": True,
                "data": paginated_data,
                "total": total,
                "limit": limit,
                "offset": offset,
                "has_more": (offset + limit) < total
            }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ========== 筹码分布API ==========

@router.get("/stocks/{stock_code}/chip-distribution")
async def get_chip_distribution(
    stock_code: str,
    limit: int = Query(default=30, ge=1, le=90)
):
    """
    获取股票筹码分布数据

    Args:
        stock_code: 股票代码
        limit: 获取条数（默认30条）

    Returns:
        筹码分布数据列表
    """
    try:
        with get_db_session() as session:
            # 查询筹码分布数据
            chip_data = session.query(StockChipDistribution).filter_by(
                stock_code=stock_code
            ).order_by(desc(StockChipDistribution.date)).limit(limit).all()

            if not chip_data:
                return {
                    "success": False,
                    "message": "暂无筹码分布数据"
                }

            # 反转数据（从旧到新）
            chip_data = list(reversed(chip_data))

            # 格式化数据
            data = []
            for c in chip_data:
                data.append({
                    "date": c.date.strftime('%Y-%m-%d'),
                    "profit_ratio": float(c.profit_ratio) if c.profit_ratio else None,
                    "avg_cost": float(c.avg_cost) if c.avg_cost else None,
                    "cost_90_low": float(c.cost_90_low) if c.cost_90_low else None,
                    "cost_90_high": float(c.cost_90_high) if c.cost_90_high else None,
                    "concentration_90": float(c.concentration_90) if c.concentration_90 else None,
                    "cost_70_low": float(c.cost_70_low) if c.cost_70_low else None,
                    "cost_70_high": float(c.cost_70_high) if c.cost_70_high else None,
                    "concentration_70": float(c.concentration_70) if c.concentration_70 else None
                })

            return {
                "success": True,
                "data": data,
                "count": len(data)
            }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ========== 估值指标API ==========

@router.get("/stocks/{stock_code}/valuation")
async def get_stock_valuation(
    stock_code: str,
    limit: int = Query(default=30, ge=1, le=90)
):
    """
    获取股票估值指标数据

    Args:
        stock_code: 股票代码
        limit: 获取条数（默认30条）

    Returns:
        估值指标数据列表
    """
    try:
        with get_db_session() as session:
            # 查询估值指标数据
            valuation_data = session.query(StockValuation).filter_by(
                stock_code=stock_code
            ).order_by(desc(StockValuation.date)).limit(limit).all()

            if not valuation_data:
                return {
                    "success": False,
                    "message": "暂无估值指标数据"
                }

            # 最新一条数据作为当前估值
            latest = valuation_data[0]

            # 反转数据（从旧到新）用于趋势图
            valuation_data = list(reversed(valuation_data))

            # 格式化历史数据
            history = []
            for v in valuation_data:
                history.append({
                    "date": v.date.strftime('%Y-%m-%d'),
                    "pe_ttm": float(v.pe_ttm) if v.pe_ttm else None,
                    "pe_static": float(v.pe_static) if v.pe_static else None,
                    "pb": float(v.pb) if v.pb else None,
                    "ps_ttm": float(v.ps_ttm) if v.ps_ttm else None,
                    "dividend_yield": float(v.dividend_yield) if v.dividend_yield else None,
                    "total_mv": float(v.total_mv) if v.total_mv else None,
                    "circ_mv": float(v.circ_mv) if v.circ_mv else None
                })

            # 当前估值数据（含行业对比）
            current = {
                "date": latest.date.strftime('%Y-%m-%d'),
                "pe_ttm": float(latest.pe_ttm) if latest.pe_ttm else None,
                "pe_static": float(latest.pe_static) if latest.pe_static else None,
                "pb": float(latest.pb) if latest.pb else None,
                "ps_ttm": float(latest.ps_ttm) if latest.ps_ttm else None,
                "dividend_yield": float(latest.dividend_yield) if latest.dividend_yield else None,
                "total_mv": float(latest.total_mv) if latest.total_mv else None,
                "circ_mv": float(latest.circ_mv) if latest.circ_mv else None,
                "industry": latest.industry,
                "industry_pe": float(latest.industry_pe) if latest.industry_pe else None,
                "industry_pb": float(latest.industry_pb) if latest.industry_pb else None
            }

            return {
                "success": True,
                "data": {
                    "current": current,
                    "history": history
                },
                "count": len(history)
            }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))



# ========== 资金流向API ==========

@router.get("/stocks/{stock_code}/fund-flow")
async def get_stock_fund_flow(
    stock_code: str,
    limit: int = Query(default=30, ge=1, le=90)
):
    """
    获取股票资金流向数据

    Args:
        stock_code: 股票代码
        limit: 获取条数（默认30条）

    Returns:
        资金流向数据列表和汇总
    """
    try:
        with get_db_session() as session:
            # 查询资金流向数据
            fund_flow_data = session.query(StockFundFlow).filter_by(
                stock_code=stock_code
            ).order_by(desc(StockFundFlow.date)).limit(limit).all()

            if not fund_flow_data:
                return {
                    "success": False,
                    "message": "暂无资金流向数据"
                }

            # 反转数据（从旧到新）用于图表
            fund_flow_data = list(reversed(fund_flow_data))

            # 格式化历史数据
            history = []
            for f in fund_flow_data:
                history.append({
                    "date": f.date.strftime('%Y-%m-%d'),
                    "close_price": float(f.close_price) if f.close_price else None,
                    "change_pct": float(f.change_pct) if f.change_pct else None,
                    "main_net_inflow": float(f.main_net_inflow) if f.main_net_inflow else None,
                    "main_net_inflow_pct": float(f.main_net_inflow_pct) if f.main_net_inflow_pct else None,
                    "super_large_net_inflow": float(f.super_large_net_inflow) if f.super_large_net_inflow else None,
                    "large_net_inflow": float(f.large_net_inflow) if f.large_net_inflow else None,
                    "medium_net_inflow": float(f.medium_net_inflow) if f.medium_net_inflow else None,
                    "small_net_inflow": float(f.small_net_inflow) if f.small_net_inflow else None,
                })

            # 计算汇总（最近5天）
            recent_5 = fund_flow_data[-5:] if len(fund_flow_data) >= 5 else fund_flow_data
            main_total = sum(f.main_net_inflow or 0 for f in recent_5)
            small_total = sum(f.small_net_inflow or 0 for f in recent_5)

            summary = {
                "days": len(recent_5),
                "main_net_inflow_total": main_total,
                "small_net_inflow_total": small_total,
                "main_flow_trend": "流入" if main_total > 0 else "流出",
                "retail_flow_trend": "流入" if small_total > 0 else "流出",
            }

            # 判断背离
            if main_total > 0 and small_total < 0:
                summary["divergence"] = "主力吸筹"
            elif main_total < 0 and small_total > 0:
                summary["divergence"] = "主力出货"
            elif main_total > 0 and small_total > 0:
                summary["divergence"] = "共同流入"
            else:
                summary["divergence"] = "共同流出"

            return {
                "success": True,
                "data": {
                    "summary": summary,
                    "history": history
                },
                "count": len(history)
            }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ========== 股东数据API ==========

@router.get("/stocks/{stock_code}/holder")
async def get_stock_holder(stock_code: str):
    """
    获取股票股东数据

    Args:
        stock_code: 股票代码

    Returns:
        股东数据
    """
    try:
        with get_db_session() as session:
            # 查询最新股东数据
            holder_data = session.query(StockHolder).filter_by(
                stock_code=stock_code
            ).order_by(desc(StockHolder.report_date)).first()

            if not holder_data:
                return {
                    "success": False,
                    "message": "暂无股东数据"
                }

            return {
                "success": True,
                "data": {
                    "report_date": holder_data.report_date.strftime('%Y-%m-%d'),
                    "total_holders": holder_data.total_holders,
                    "avg_hold_num": float(holder_data.avg_hold_num) if holder_data.avg_hold_num else None,
                    "holder_change": holder_data.holder_change,
                    "holder_change_pct": float(holder_data.holder_change_pct) if holder_data.holder_change_pct else None,
                    "concentration_trend": holder_data.concentration_trend,
                    "top10_hold_ratio": float(holder_data.top10_hold_ratio) if holder_data.top10_hold_ratio else None,
                    "first_holder_name": holder_data.first_holder_name,
                    "first_holder_ratio": float(holder_data.first_holder_ratio) if holder_data.first_holder_ratio else None,
                    "control_type": holder_data.control_type,
                    "top_holders": holder_data.top_holders_detail
                }
            }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ========== 行业对比API ==========

@router.get("/stocks/{stock_code}/industry-rank")
async def get_stock_industry_rank_api(stock_code: str):
    """
    获取股票在行业内的排名

    Args:
        stock_code: 股票代码

    Returns:
        行业排名数据
    """
    try:
        # 先获取股票所属行业
        from stock_analyzer.valuation_fetcher import get_stock_industry
        from stock_analyzer.industry_compare import get_stock_industry_rank, get_industry_top_stocks

        industry = get_stock_industry(stock_code)
        if not industry:
            return {
                "success": False,
                "message": "无法获取股票所属行业"
            }

        # 获取行业排名
        rank_info = get_stock_industry_rank(stock_code, industry)
        if not rank_info:
            return {
                "success": False,
                "message": "无法获取行业排名数据"
            }

        # 获取行业Top5
        top_stocks = get_industry_top_stocks(industry, top_n=5)

        return {
            "success": True,
            "data": {
                "industry": industry,
                "total_stocks": rank_info.get("total_stocks"),
                "stock_code": stock_code,
                "stock_name": rank_info.get("stock_name"),
                "price": rank_info.get("price"),
                "change_pct": rank_info.get("change_pct"),
                "change_rank": rank_info.get("change_rank"),
                "change_percentile": rank_info.get("change_percentile"),
                "pe_ttm": rank_info.get("pe_ttm"),
                "pe_rank": rank_info.get("pe_rank"),
                "pe_percentile": rank_info.get("pe_percentile"),
                "pe_vs_industry": rank_info.get("pe_vs_industry"),
                "pb": rank_info.get("pb"),
                "pb_rank": rank_info.get("pb_rank"),
                "pb_percentile": rank_info.get("pb_percentile"),
                "pb_vs_industry": rank_info.get("pb_vs_industry"),
                "industry_avg_pe": rank_info.get("industry_avg_pe"),
                "industry_avg_pb": rank_info.get("industry_avg_pb"),
                "industry_avg_change": rank_info.get("industry_avg_change"),
                "top_stocks": top_stocks
            }
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ========== 获取所有股票的最新分析报告 ==========

@router.get("/analysis/latest")
async def get_latest_analysis_all():
    """
    获取所有股票的最新AI分析报告

    Returns:
        所有股票的最新分析列表
    """
    try:
        with get_db_session() as session:
            # 子查询：获取每个股票的最新分析日期
            from sqlalchemy import func
            latest_dates = session.query(
                GeminiAnalysis.stock_code,
                func.max(GeminiAnalysis.analysis_date).label("latest_date")
            ).group_by(GeminiAnalysis.stock_code).subquery()

            # 连接查询获取完整的分析记录
            results = session.query(
                Stock,
                GeminiAnalysis
            ).join(
                latest_dates,
                Stock.stock_code == latest_dates.c.stock_code
            ).join(
                GeminiAnalysis,
                (GeminiAnalysis.stock_code == Stock.stock_code) &
                (GeminiAnalysis.analysis_date == latest_dates.c.latest_date)
            ).all()

            if not results:
                return {
                    "success": True,
                    "data": [],
                    "message": "暂无分析数据"
                }

            data = []
            for stock, analysis in results:
                # Parse JSON if it's a string
                analysis_json = analysis.analysis_result
                if isinstance(analysis_json, str):
                    analysis_json = json.loads(analysis_json)

                data.append({
                    "stock_code": stock.stock_code,
                    "stock_name": stock.stock_name,
                    "analysis_date": analysis.analysis_date.strftime("%Y-%m-%d"),
                    "model_name": analysis.model_name,
                    "technical_score": analysis_json.get("technical_score", 0),
                    "fundamental_score": analysis_json.get("fundamental_score", 0),
                    "risk_level": analysis_json.get("risk_level", "-"),
                    "suggestion": analysis_json.get("suggestion", "-"),
                    "key_points": analysis_json.get("key_points", []),
                    "technical_analysis": analysis_json.get("technical_analysis", ""),
                    "fundamental_analysis": analysis_json.get("fundamental_analysis", ""),
                    "risk_analysis": analysis_json.get("risk_analysis", ""),
                    "summary": analysis_json.get("summary", ""),
                    "created_at": analysis.created_at.isoformat()
                })

            # 按综合评分排序（技术面 + 基本面）
            data.sort(
                key=lambda x: float(x["technical_score"]) + float(x["fundamental_score"]),
                reverse=True
            )

            return {
                "success": True,
                "data": data,
                "count": len(data)
            }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
