from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, Request

from ..dependencies import current_uid, get_repository
from ..schemas.market import MarketSelectRequest


router = APIRouter(tags=["market"])


@router.get("/api/markets")
def get_markets(request: Request):
    service = request.app.state.market_data
    allowed = {"US", "INDIA"}
    markets = [row for row in service.markets() if str(row.get("key")) in allowed]
    return {"markets": markets}


@router.post("/api/market/select")
def select_market(payload: MarketSelectRequest, uid: str = Depends(current_uid), repo=Depends(get_repository)):
    market = payload.market.upper().strip()
    if market not in {"US", "INDIA"}:
        raise HTTPException(status_code=400, detail="Only US and INDIA paper trading markets are supported")
    return repo.set_selected_market(uid, market)


@router.get("/api/search")
def search_symbols(request: Request, q: str = Query(..., min_length=1), limit: int = 12, uid: str = Depends(current_uid), repo=Depends(get_repository)):
    service = request.app.state.market_data
    market = repo.get_selected_market(uid)
    rows = service.search_symbols(q, market=market, limit=limit)
    return {"query": q, "market": market, "results": rows}


@router.get("/api/quote/{symbol}")
def quick_quote(symbol: str, request: Request, uid: str = Depends(current_uid), repo=Depends(get_repository)):
    service = request.app.state.market_data
    market = repo.get_selected_market(uid)
    resolved = service.resolve_symbol(symbol, market)
    quote = service.quote(resolved, market)
    benchmark = service.benchmark_quote(market)
    return {"market": market, "quote": quote, "benchmark": benchmark}
