from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request

from ..dependencies import current_uid, get_repository
from ..schemas.portfolio import TradeJournalUpdateRequest, TradeRequest


router = APIRouter(tags=["portfolio"])


def _checklist_valid(checklist: dict | None) -> bool:
    if not checklist:
        return False
    required = ["thesis", "risk_level", "time_horizon", "buy_reason", "trade_type"]
    return all(bool(str(checklist.get(key, "")).strip()) for key in required)


@router.get("/api/portfolio")
def get_portfolio(request: Request, uid: str = Depends(current_uid), repo=Depends(get_repository)):
    market = repo.get_selected_market(uid)
    return repo.get_portfolio(uid, market)


@router.get("/api/portfolio/performance")
def get_portfolio_performance(request: Request, uid: str = Depends(current_uid), repo=Depends(get_repository)):
    market = repo.get_selected_market(uid)
    return repo.get_portfolio_performance(uid, market)


@router.post("/api/trades/buy")
def buy_trade(payload: TradeRequest, request: Request, uid: str = Depends(current_uid), repo=Depends(get_repository)):
    if not _checklist_valid(payload.checklist):
        raise HTTPException(status_code=400, detail="Before-you-trade checklist is required")
    market_data = request.app.state.market_data
    learning_engine = request.app.state.learning_engine
    market = repo.get_selected_market(uid)
    symbol = market_data.resolve_symbol(payload.symbol, market)
    quote = market_data.quote(symbol, market)
    learning_engine.save_checklist(uid, payload.checklist or {})
    return repo.apply_trade(
        uid=uid,
        market=market,
        side="buy",
        symbol=symbol,
        quantity=payload.quantity,
        price=float(quote["price"]),
        order_type=payload.order_type,
        notes=payload.notes,
    )


@router.post("/api/trades/sell")
def sell_trade(payload: TradeRequest, request: Request, uid: str = Depends(current_uid), repo=Depends(get_repository)):
    if not _checklist_valid(payload.checklist):
        raise HTTPException(status_code=400, detail="Before-you-trade checklist is required")
    market_data = request.app.state.market_data
    learning_engine = request.app.state.learning_engine
    market = repo.get_selected_market(uid)
    symbol = market_data.resolve_symbol(payload.symbol, market)
    quote = market_data.quote(symbol, market)
    learning_engine.save_checklist(uid, payload.checklist or {})
    return repo.apply_trade(
        uid=uid,
        market=market,
        side="sell",
        symbol=symbol,
        quantity=payload.quantity,
        price=float(quote["price"]),
        order_type=payload.order_type,
        notes=payload.notes,
    )


@router.get("/api/trades/history")
def trade_history(uid: str = Depends(current_uid), repo=Depends(get_repository)):
    market = repo.get_selected_market(uid)
    trades = repo.list_trades(uid, market=market)
    for row in trades:
        row["journal"] = repo.get_trade_journal(uid, row["id"])
    return {"market": market, "trades": trades}


@router.put("/api/trades/journal/{trade_id}")
def update_trade_journal(trade_id: str, payload: TradeJournalUpdateRequest, uid: str = Depends(current_uid), repo=Depends(get_repository)):
    return repo.upsert_trade_journal(uid, trade_id, payload.model_dump(exclude_none=True))
