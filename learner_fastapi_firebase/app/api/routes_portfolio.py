from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request

from ..dependencies import current_uid, get_repository
from ..schemas.portfolio import CashDepositRequest, TradeJournalUpdateRequest, TradeRequest


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


@router.post("/api/portfolio/deposit")
def deposit_cash(payload: CashDepositRequest, request: Request, uid: str = Depends(current_uid), repo=Depends(get_repository)):
    market = repo.get_selected_market(uid)
    try:
        return repo.deposit_cash(uid=uid, market=market, amount=payload.amount, notes=payload.notes)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/api/trades/buy")
def buy_trade(payload: TradeRequest, request: Request, uid: str = Depends(current_uid), repo=Depends(get_repository)):
    if not _checklist_valid(payload.checklist):
        raise HTTPException(status_code=400, detail="Before-you-trade checklist is required")
    market_data = request.app.state.market_data
    learning_engine = request.app.state.learning_engine
    market = repo.get_selected_market(uid)
    symbol = market_data.resolve_symbol(payload.symbol, market)
    quote = market_data.quote(symbol, market)
    quote_price = float(quote["price"])
    if payload.stop_loss_price is not None and payload.stop_loss_price >= quote_price:
        raise HTTPException(status_code=400, detail="Stop-loss price must be below the current price")
    if payload.trailing_stop_amount is not None and payload.trailing_stop_amount >= quote_price:
        raise HTTPException(status_code=400, detail="Trailing amount must be below the current price")
    learning_engine.save_checklist(uid, payload.checklist or {})
    result = repo.apply_trade(
        uid=uid,
        market=market,
        side="buy",
        symbol=symbol,
        quantity=payload.quantity,
        price=quote_price,
        order_type=payload.order_type,
        notes=payload.notes,
    )
    protective_orders: list[dict] = []
    if payload.stop_loss_price is not None:
        protective_orders.append(
            repo.create_order(
                uid=uid,
                market=market,
                side="sell",
                symbol=symbol,
                quantity=payload.quantity,
                order_type="stop_loss",
                trigger_price=payload.stop_loss_price,
                oco_group=result["trade"]["id"],
                notes=f"Auto stop-loss for trade {result['trade']['id']}",
            )
        )
    if payload.trailing_stop_percent is not None or payload.trailing_stop_amount is not None:
        protective_orders.append(
            repo.create_order(
                uid=uid,
                market=market,
                side="sell",
                symbol=symbol,
                quantity=payload.quantity,
                order_type="trailing_stop",
                trail_percent=payload.trailing_stop_percent,
                trail_amount=payload.trailing_stop_amount,
                reference_price=quote_price,
                oco_group=result["trade"]["id"],
                notes=f"Auto trailing stop for trade {result['trade']['id']}",
            )
        )
    if protective_orders:
        result["protective_orders"] = protective_orders
    return result


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
