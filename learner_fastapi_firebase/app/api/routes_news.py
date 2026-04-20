from __future__ import annotations

from fastapi import APIRouter, Depends, Query, Request

from ..dependencies import current_uid, get_repository


router = APIRouter(tags=["news"])


@router.get("/api/news/market")
def market_news(request: Request, uid: str = Depends(current_uid), repo=Depends(get_repository)):
    market = repo.get_selected_market(uid)
    rows = request.app.state.market_data.market_news(market, limit=12)
    return {"market": market, "items": rows}


@router.get("/api/news/stock/{symbol}")
def stock_news(symbol: str, request: Request, uid: str = Depends(current_uid), repo=Depends(get_repository)):
    market = repo.get_selected_market(uid)
    rows = request.app.state.market_data.stock_news(symbol, market, limit=10)
    return {"market": market, "symbol": symbol, "items": rows}


@router.get("/api/news/sector")
def sector_news(request: Request, sector: str = Query("technology")):
    rows = request.app.state.market_data.sector_news(sector, limit=10)
    return {"sector": sector, "items": rows}


@router.get("/api/news/macro")
def macro_news(request: Request):
    rows = request.app.state.market_data.macro_news(limit=10)
    return {"items": rows}


@router.get("/api/calendar/events")
def event_calendar(request: Request, uid: str = Depends(current_uid), repo=Depends(get_repository)):
    market = repo.get_selected_market(uid)
    return {"market": market, "links": request.app.state.market_data.event_calendar_links(market)}
