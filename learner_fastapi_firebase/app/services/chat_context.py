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


def _tradebook_stats(trades: list[dict[str, Any]]) -> dict[str, Any]:
    realized_rows = [row for row in trades if str(row.get("side") or "").lower() == "sell"]
    realized_pnls = [_f(row.get("realized_pnl"), 0.0) for row in realized_rows]
    wins = [pnl for pnl in realized_pnls if pnl > 0]
    losses = [pnl for pnl in realized_pnls if pnl < 0]
    symbols: list[str] = []
    seen: set[str] = set()
    for trade in trades:
        symbol = str(trade.get("symbol") or "").strip().upper()
        if symbol and symbol not in seen:
            seen.add(symbol)
            symbols.append(symbol)
    return {
        "trade_count": len(trades),
        "buy_count": sum(1 for row in trades if str(row.get("side") or "").lower() == "buy"),
        "sell_count": len(realized_rows),
        "realized_trade_count": len(realized_rows),
        "winning_sells": len(wins),
        "losing_sells": len(losses),
        "win_rate_pct": round((len(wins) / len(realized_rows) * 100), 2) if realized_rows else 0.0,
        "realized_pnl": round(sum(realized_pnls), 2),
        "symbols_traded": symbols[:30],
    }


def _journal_rows(repo: Any, uid: str, trades: list[dict[str, Any]], limit: int) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for trade in trades[:limit]:
        trade_id = str(trade.get("id") or "")
        if not trade_id:
            continue
        journal = _safe_call(repo.get_trade_journal, uid, trade_id, default={}) or {}
        if journal:
            rows.append(
                {
                    "trade_id": trade_id,
                    "symbol": trade.get("symbol"),
                    "side": trade.get("side"),
                    "created_at": trade.get("created_at"),
                    "realized_pnl": trade.get("realized_pnl"),
                    "journal": journal,
                }
            )
    return rows


def build_ai_user_context(
    uid: str,
    market: str,
    repo: Any,
    learning_engine: Any | None = None,
    market_data: Any | None = None,
    trade_limit: int = 80,
    journal_limit: int = 40,
) -> dict[str, Any]:
    portfolio = repo.get_portfolio(uid, market)
    positions = [_with_change_pct(row) for row in (portfolio.get("positions") or []) if isinstance(row, dict)]
    watchlists = repo.list_watchlists(uid)
    watchlist_symbols = _collect_symbols_from_watchlists(watchlists)
    holding_symbols = [str(row.get("symbol") or "").strip().upper() for row in positions if row.get("symbol")]
    trades = repo.list_trades(uid, market=market)
    journal_rows = _journal_rows(repo, uid, trades, journal_limit)
    learning_docs = {
        "goals": repo.get_learning_doc(uid, "goals", default={}),
        "quizzes": repo.get_learning_doc(uid, "quizzes", default={}),
        "challenges": repo.get_learning_doc(uid, "challenges", default={}),
        "streaks": repo.get_learning_doc(uid, "streaks", default={}),
        "portfolio_goal": repo.get_learning_doc(uid, "portfolio_goal", default={}),
        "before_trade_checklist": repo.get_learning_doc(uid, "before_trade_checklist", default={}),
    }
    learning: dict[str, Any] = {"docs": learning_docs}
    if learning_engine is not None:
        learning.update(
            {
                "dashboard": _safe_call(learning_engine.dashboard, uid, market, default={}) or {},
                "health": _safe_call(learning_engine.health_score, uid, market, default={}) or {},
                "mistakes": _safe_call(learning_engine.mistake_detection, uid, market, default={}) or {},
                "weekly_summary": _safe_call(learning_engine.weekly_summary, uid, market, default={}) or {},
            }
        )

    context = {
        "access_mode": "advisor_compact",
        "data_origin": "firestore_repository",
        "generated_at": _now_iso(),
        "market": market,
        "user_profile": _safe_call(repo.get_profile, uid, default={}) or {},
        "user_preferences": _safe_call(repo.get_preferences, uid, default={}) or {},
        "saved_filters": _safe_call(repo.get_saved_filters, uid, default=[]) or [],
        "watchlists": watchlists,
        "alerts": _safe_call(repo.list_alerts, uid, default=[]) or [],
        "notifications": (_safe_call(repo.list_notifications, uid, default=[]) or [])[:50],
        "orders": _safe_call(repo.list_orders, uid, market=market, default=[]) or [],
        "portfolio": {**portfolio, "positions": positions},
        "portfolio_performance": _safe_call(repo.get_portfolio_performance, uid, market, default={}) or {},
        "tradebook": {
            "stats": _tradebook_stats(trades),
            "recent_trades": trades[:trade_limit],
            "journal_entries": journal_rows,
        },
        "trades": trades[:trade_limit],
        "journal_entries": journal_rows,
        "learning": learning,
        "data_scope": {
            "position_count": len(positions),
            "holding_symbols": holding_symbols,
            "watchlist_symbol_count": len(watchlist_symbols),
            "trade_count": len(trades),
            "journal_entry_count": len(journal_rows),
        },
    }
    if market_data is not None:
        context["market_snapshot"] = {
            "benchmark": _safe_call(market_data.benchmark_quote, market, default={}) or {},
            "market_mood": _safe_call(market_data.market_mood, market, default={}) or {},
        }
    return context


def build_ai_chat_context(
    uid: str,
    market: str,
    repo: Any,
    learning_engine: Any,
    market_data: Any,
) -> dict[str, Any]:
    context = build_ai_user_context(
        uid=uid,
        market=market,
        repo=repo,
        learning_engine=learning_engine,
        market_data=market_data,
        trade_limit=200,
        journal_limit=80,
    )
    positions = context.get("portfolio", {}).get("positions") or []
    watchlists = context.get("watchlists") or []
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

    market_news = _safe_call(market_data.market_news, market, limit=24, default=[]) or []
    context["access_mode"] = "full"
    context["market_intel"] = {
        "benchmark": _safe_call(market_data.benchmark_quote, market, default={}) or {},
        "market_mood": _safe_call(market_data.market_mood, market, default={}) or {},
        "market_news": market_news,
        "macro_news": _safe_call(market_data.macro_news, limit=24, default=[]) or [],
        "event_calendar_links": _safe_call(market_data.event_calendar_links, market, default=[]) or [],
    }
    context["holdings_intel"] = holdings_intel
    context["watchlist_intel"] = watchlist_intel
    context["data_scope"] = {
        **(context.get("data_scope") or {}),
        "news_items": len(market_news),
    }
    return context
