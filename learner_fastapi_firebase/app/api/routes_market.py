from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, Request

from ..dependencies import current_uid, get_repository
from ..schemas.market import MarketSelectRequest
from ..services.chat_context import build_ai_user_context


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
    advisor = request.app.state.ai_advisor
    market = repo.get_selected_market(uid)
    resolved = service.resolve_symbol(symbol, market)
    quote = service.quote(resolved, market)
    benchmark = service.benchmark_quote(market)
    chart = service.quote_history(resolved, market, period="1y", interval="1d")
    news = service.stock_news(resolved, market, limit=8)
    ai_recommendation = advisor.quote_signal(
        uid=uid,
        market=market,
        symbol=resolved,
        payload={
            "quote": quote,
            "forecast": service.forecast_lite(resolved, market),
            "risk": service.risk_lite(resolved, market),
            "market_mood": service.market_mood(market),
            "news": news,
            "close_prices": chart.get("close") or [],
            "user_context": build_ai_user_context(
                uid=uid,
                market=market,
                repo=repo,
                learning_engine=request.app.state.learning_engine,
                market_data=service,
            ),
        },
    )
    return {"market": market, "quote": quote, "benchmark": benchmark, "ai_recommendation": ai_recommendation}
