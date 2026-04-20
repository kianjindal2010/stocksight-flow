from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Callable


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _f(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _safe_call(fn: Callable[..., Any], *args: Any, default: Any = None, **kwargs: Any) -> Any:
    try:
        return fn(*args, **kwargs)
    except Exception:
        return default


def _with_change_pct(position: dict[str, Any]) -> dict[str, Any]:
    row = dict(position)
    avg = _f(row.get("avg_price"), 0.0)
    last = _f(row.get("last_price"), avg)
    row["change_pct"] = round(((last - avg) / avg * 100), 2) if avg > 0 else 0.0
    return row


def _collect_symbols_from_watchlists(watchlists: list[dict[str, Any]]) -> list[str]:
    symbols: list[str] = []
    seen: set[str] = set()
    for watchlist in watchlists:
        for raw in watchlist.get("symbols") or []:
            symbol = str(raw or "").strip().upper()
            if not symbol or symbol in seen:
                continue
            seen.add(symbol)
            symbols.append(symbol)
    return symbols


def build_ai_chat_context(
    uid: str,
    market: str,
    repo: Any,
    learning_engine: Any,
    market_data: Any,
) -> dict[str, Any]:
    portfolio = repo.get_portfolio(uid, market)
    positions = [_with_change_pct(row) for row in (portfolio.get("positions") or []) if isinstance(row, dict)]
    watchlists = repo.list_watchlists(uid)
    watchlist_symbols = _collect_symbols_from_watchlists(watchlists)
    holding_symbols = [str(row.get("symbol") or "").strip().upper() for row in positions if row.get("symbol")]

    holdings_intel: list[dict[str, Any]] = []
    for symbol in holding_symbols[:25]:
        holdings_intel.append(
            {
                "symbol": symbol,
                "quote": _safe_call(market_data.quote, symbol, market, default={}) or {},
                "risk": _safe_call(market_data.risk_lite, symbol, market, default={}) or {},
                "forecast": _safe_call(market_data.forecast_lite, symbol, market, default={}) or {},
                "news": _safe_call(market_data.stock_news, symbol, market, limit=8, default=[]) or [],
            }
        )

    watchlist_intel: list[dict[str, Any]] = []
    for symbol in [s for s in watchlist_symbols if s not in set(holding_symbols)][:25]:
        watchlist_intel.append(
            {
                "symbol": symbol,
                "quote": _safe_call(market_data.quote, symbol, market, default={}) or {},
                "forecast": _safe_call(market_data.forecast_lite, symbol, market, default={}) or {},
                "news": _safe_call(market_data.stock_news, symbol, market, limit=4, default=[]) or [],
            }
        )

    trades = repo.list_trades(uid, market=market)
    journal_rows: list[dict[str, Any]] = []
    for trade in trades[:80]:
        trade_id = str(trade.get("id") or "")
        if not trade_id:
            continue
        journal = repo.get_trade_journal(uid, trade_id)
        if journal:
            journal_rows.append({"trade_id": trade_id, "journal": journal})

    learning_docs = {
        "goals": repo.get_learning_doc(uid, "goals", default={}),
        "quizzes": repo.get_learning_doc(uid, "quizzes", default={}),
        "challenges": repo.get_learning_doc(uid, "challenges", default={}),
        "streaks": repo.get_learning_doc(uid, "streaks", default={}),
        "portfolio_goal": repo.get_learning_doc(uid, "portfolio_goal", default={}),
        "before_trade_checklist": repo.get_learning_doc(uid, "before_trade_checklist", default={}),
    }

    context = {
        "access_mode": "full",
        "generated_at": _now_iso(),
        "market": market,
        "user_profile": repo.get_profile(uid),
        "user_preferences": repo.get_preferences(uid),
        "saved_filters": repo.get_saved_filters(uid),
        "watchlists": watchlists,
        "alerts": repo.list_alerts(uid),
        "notifications": repo.list_notifications(uid)[:100],
        "orders": repo.list_orders(uid, market=market),
        "portfolio": {**portfolio, "positions": positions},
        "portfolio_performance": repo.get_portfolio_performance(uid, market),
        "trades": trades[:200],
        "journal_entries": journal_rows,
        "learning": {
            "dashboard": learning_engine.dashboard(uid, market),
            "health": learning_engine.health_score(uid, market),
            "mistakes": learning_engine.mistake_detection(uid, market),
            "weekly_summary": learning_engine.weekly_summary(uid, market),
            "docs": learning_docs,
        },
        "market_intel": {
            "benchmark": _safe_call(market_data.benchmark_quote, market, default={}) or {},
            "market_mood": _safe_call(market_data.market_mood, market, default={}) or {},
            "market_news": _safe_call(market_data.market_news, market, limit=24, default=[]) or [],
            "macro_news": _safe_call(market_data.macro_news, limit=24, default=[]) or [],
            "event_calendar_links": _safe_call(market_data.event_calendar_links, market, default=[]) or [],
        },
        "holdings_intel": holdings_intel,
        "watchlist_intel": watchlist_intel,
        "data_scope": {
            "position_count": len(positions),
            "holding_symbols": holding_symbols,
            "watchlist_symbol_count": len(watchlist_symbols),
            "trade_count": len(trades),
            "news_items": len((_safe_call(market_data.market_news, market, limit=24, default=[]) or [])),
        },
    }
    return context
