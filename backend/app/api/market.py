from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.data.market_service import MarketDataError, MarketDataService
from app.db.models import Instrument, User, UserWatchlist
from app.db.session import SessionFactory, get_session

router = APIRouter(tags=["market-data"])


class WatchlistWrite(BaseModel):
    symbol: str = Field(min_length=6, max_length=6, pattern=r"^\d{6}$")


def service_for(request: Request) -> MarketDataService:
    return MarketDataService(SessionFactory, getattr(request.app.state, "redis", None))


@router.get("/instruments/search")
async def search_instruments(
    query: str,
    request: Request,
    user: User = Depends(get_current_user),
) -> list[dict]:
    del user
    try:
        return await service_for(request).search_instruments(query)
    except MarketDataError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@router.get("/watchlist")
async def list_watchlist(request: Request, user: User = Depends(get_current_user)) -> list[dict]:
    return await service_for(request).list_watchlist(user.id)


@router.post("/watchlist", status_code=status.HTTP_201_CREATED)
async def add_to_watchlist(
    payload: WatchlistWrite,
    request: Request,
    user: User = Depends(get_current_user),
) -> dict:
    try:
        return await service_for(request).add_to_watchlist(user.id, payload.symbol)
    except MarketDataError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.delete("/watchlist/{code}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_from_watchlist(
    code: str,
    request: Request,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> None:
    link = await session.scalar(
        select(UserWatchlist)
        .join(Instrument)
        .where(
            UserWatchlist.owner_id == user.id,
            Instrument.code == code.upper(),
        )
    )
    if link is None:
        raise HTTPException(status_code=404, detail="关注股票不存在")
    await service_for(request).remove_from_watchlist(user.id, code)


@router.get("/market/overview")
async def market_overview(request: Request, user: User = Depends(get_current_user)) -> dict:
    del user
    try:
        return await service_for(request).get_market_overview()
    except MarketDataError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@router.get("/instruments/{symbol}/research/{dataset}")
async def company_research(
    symbol: str,
    dataset: Literal["notices", "financial", "valuation", "chip", "fund_flow", "holders"],
    request: Request,
    limit: int = Query(default=20, ge=1, le=100),
    user: User = Depends(get_current_user),
) -> dict:
    try:
        return await service_for(request).get_company_research(user.id, symbol, dataset, limit)
    except MarketDataError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
