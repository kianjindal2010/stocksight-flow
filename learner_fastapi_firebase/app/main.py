from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlencode

from fastapi import FastAPI, Form, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from .api import build_api_router
from .config import get_settings
from .firebase import get_firestore_client, initialize_firebase, verify_id_token
from .services.emailer import EmailService
from .services.firestore_repo import FirestoreRepository
from .services.ai_advisor import AIAdvisorService
from .services.learning_engine import LearningEngine
from .services.market_data import MarketDataService


BASE_DIR = Path(__file__).resolve().parent.parent
TEMPLATES_DIR = BASE_DIR / "templates"
STATIC_DIR = BASE_DIR / "static"


def _extract_token(request: Request) -> str | None:
    auth_header = request.headers.get("Authorization", "")
    if auth_header.lower().startswith("bearer "):
        return auth_header.split(" ", 1)[1].strip()
    cookie_token = request.cookies.get("ss_id_token")
    if cookie_token:
        return cookie_token
    return None


def _f(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _currency_symbol(code: str) -> str:
    mapping = {"USD": "$", "INR": "Rs.", "GBP": "GBP "}
    return mapping.get(code.upper(), f"{code.upper()} ")


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def create_app() -> FastAPI:
    settings = get_settings()
    initialize_firebase(settings)

    app = FastAPI(title="StockSight Learner (FastAPI + Firebase)")
    app.state.settings = settings
    app.state.repo = FirestoreRepository(firestore_client=get_firestore_client(settings))
    app.state.market_data = MarketDataService(cache_seconds=settings.market_data_cache_seconds)
    app.state.email_service = EmailService(settings)
    app.state.learning_engine = LearningEngine(app.state.repo, app.state.market_data)
    app.state.ai_advisor = AIAdvisorService(
        api_key=settings.nvidia_api_key,
        base_url=settings.nvidia_base_url,
        model=settings.nvidia_model,
        timeout_seconds=settings.ai_request_timeout_seconds,
        cache_seconds=settings.ai_cache_seconds,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.app_cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")
    templates = Jinja2Templates(directory=str(TEMPLATES_DIR))

    @app.middleware("http")
    async def firebase_session_middleware(request: Request, call_next):
        request.state.current_user = None
        token = _extract_token(request)
        if token:
            try:
                if settings.firebase_use_memory and token.startswith("dev-token:"):
                    _, uid, email = token.split(":", 2)
                    decoded = {"uid": uid, "email": email, "name": email.split("@")[0]}
                else:
                    decoded = verify_id_token(token)
                uid = str(decoded.get("uid") or decoded.get("user_id") or "")
                email = str(decoded.get("email") or "")
                display_name = str(decoded.get("name") or "")
                request.state.current_user = {"uid": uid, "email": email, "name": display_name}
                if uid:
                    app.state.repo.ensure_user(uid, email=email, display_name=display_name)
            except Exception:
                request.state.current_user = None
        return await call_next(request)

    app.include_router(build_api_router())

    def _uid(request: Request) -> str | None:
        user = getattr(request.state, "current_user", None)
        if not user:
            return None
        uid = str(user.get("uid") or "")
        return uid or None

    def _redirect(path: str, message: str = "", error: str = "") -> RedirectResponse:
        params: dict[str, str] = {}
        if message:
            params["message"] = message
        if error:
            params["error"] = error
        url = path
        if params:
            url = f"{url}?{urlencode(params)}"
        return RedirectResponse(url=url, status_code=303)

    def _context(request: Request, extra: dict[str, Any] | None = None) -> dict[str, Any]:
        user = getattr(request.state, "current_user", None)
        base: dict[str, Any] = {
            "request": request,
            "current_user": user,
            "authenticated": bool(user),
            "app_name": "StockSight Learner",
            "flash": request.query_params.get("message", ""),
            "error": request.query_params.get("error", ""),
            "firebase_web_api_key": settings.firebase_web_api_key,
            "firebase_project_id": settings.firebase_project_id,
            "firebase_auth_domain": settings.firebase_auth_domain
            or (f"{settings.firebase_project_id}.firebaseapp.com" if settings.firebase_project_id else ""),
        }
        if user:
            uid = user["uid"]
            profile = app.state.repo.get_profile(uid)
            preferences = app.state.repo.get_preferences(uid)
            market = app.state.repo.get_selected_market(uid)
            allowed_keys = {"US", "INDIA"}
            if market not in allowed_keys:
                market = "US"
                app.state.repo.set_selected_market(uid, market)
            market_options = [row for row in app.state.market_data.markets() if str(row.get("key")) in allowed_keys]
            base.update(
                {
                    "profile": profile,
                    "preferences": preferences,
                    "market": market,
                    "available_markets": market_options,
                }
            )
        if extra:
            base.update(extra)
        return base

    def _auth_or_redirect(request: Request) -> str | RedirectResponse:
        uid = _uid(request)
        if not uid:
            return RedirectResponse(url="/login", status_code=303)
        return uid

    def _should_fill_order(order: dict[str, Any], last_price: float) -> bool:
        if str(order.get("status")) != "open":
            return False
        order_type = str(order.get("order_type") or "limit").lower()
        if order_type == "market":
            return True
        trigger = order.get("trigger_price")
        if trigger is None:
            return False
        trigger_price = _f(trigger)
        side = str(order.get("side") or "buy").lower()
        if side == "buy":
            return last_price <= trigger_price
        return last_price >= trigger_price

    def _process_open_orders(uid: str, market: str) -> int:
        filled = 0
        orders = app.state.repo.list_orders(uid, market)
        for order in orders:
            if str(order.get("status")) != "open":
                continue
            try:
                quote = app.state.market_data.quote(order["symbol"], market)
                last_price = _f(quote.get("price"))
                if last_price <= 0:
                    continue
                if not _should_fill_order(order, last_price):
                    continue
                trade_result = app.state.repo.apply_trade(
                    uid=uid,
                    market=market,
                    side=str(order.get("side") or "buy"),
                    symbol=str(order.get("symbol") or ""),
                    quantity=int(_f(order.get("quantity"), 1)),
                    price=last_price,
                    order_type=str(order.get("order_type") or "limit"),
                    notes=str(order.get("notes") or ""),
                )
                app.state.repo.mark_order_filled(
                    uid=uid,
                    order_id=order["id"],
                    fill_price=last_price,
                    trade_id=trade_result["trade"]["id"],
                )
                filled += 1
            except Exception as exc:
                app.state.repo.update_order(
                    uid,
                    order["id"],
                    {
                        "status": "rejected",
                        "notes": f"{str(order.get('notes') or '').strip()} | {exc}".strip(" |"),
                    },
                )
        return filled

    def _chat_doc_id(market: str) -> str:
        return f"ai_chat_{str(market).lower()}"

    def _load_chat_history(uid: str, market: str) -> list[dict[str, Any]]:
        doc = app.state.repo.get_learning_doc(uid, _chat_doc_id(market), default={"messages": []})
        rows = doc.get("messages")
        if not isinstance(rows, list):
            return []
        history: list[dict[str, Any]] = []
        for row in rows[-30:]:
            if not isinstance(row, dict):
                continue
            role = str(row.get("role") or "")
            content = str(row.get("content") or "").strip()
            if role not in {"user", "assistant"} or not content:
                continue
            history.append(
                {
                    "role": role,
                    "content": content[:4000],
                    "created_at": str(row.get("created_at") or ""),
                }
            )
        return history

    def _save_chat_history(uid: str, market: str, messages: list[dict[str, Any]]) -> None:
        app.state.repo.set_learning_doc(uid, _chat_doc_id(market), {"messages": messages[-30:]}, merge=False)

    @app.get("/", response_class=HTMLResponse)
    async def home(request: Request):
        uid = _auth_or_redirect(request)
        if isinstance(uid, RedirectResponse):
            return templates.TemplateResponse(request, "login.html", _context(request))

        market = app.state.repo.get_selected_market(uid)
        if market not in {"US", "INDIA"}:
            market = "US"
            app.state.repo.set_selected_market(uid, market)
        dashboard = app.state.learning_engine.dashboard(uid, market)
        benchmark = app.state.market_data.benchmark_quote(market)
        news = app.state.market_data.market_news(market, limit=8)
        health = app.state.learning_engine.health_score(uid, market)
        weekly_summary = app.state.learning_engine.weekly_summary(uid, market)
        mistakes = app.state.learning_engine.mistake_detection(uid, market)
        mood = app.state.market_data.market_mood(market)
        portfolio = app.state.repo.get_portfolio(uid, market)
        positions = portfolio.get("positions", [])
        for pos in positions:
            avg = _f(pos.get("avg_price"))
            last = _f(pos.get("last_price"))
            pos["change_pct"] = round(((last - avg) / avg * 100), 2) if avg else 0.0
            pos["market_value"] = round(_f(pos.get("market_value")), 2)
            pos["unrealized_pnl"] = round(_f(pos.get("unrealized_pnl")), 2)
        top_positions = sorted(positions, key=lambda row: _f(row.get("change_pct")), reverse=True)[:4]
        worst_positions = sorted(positions, key=lambda row: _f(row.get("change_pct")))[:4]
        currency_code = str(benchmark.get("currency") or "USD")
        coach = app.state.ai_advisor.dashboard_brief(
            uid=uid,
            market=market,
            payload={
                "dashboard": dashboard,
                "portfolio": portfolio,
                "health": health,
                "mistakes": mistakes,
                "weekly_summary": weekly_summary,
                "market_mood": mood,
                "news": news,
                "positions": positions,
                "top_positions": top_positions,
                "worst_positions": worst_positions,
            },
        )
        return templates.TemplateResponse(
            request,
            "index.html",
            _context(
                request,
                {
                    "dashboard": dashboard,
                    "benchmark": benchmark,
                    "news": news,
                    "portfolio": portfolio,
                    "positions": positions,
                    "top_positions": top_positions,
                    "worst_positions": worst_positions,
                    "coach": coach,
                    "currency_code": currency_code,
                    "currency_symbol": _currency_symbol(currency_code),
                },
            ),
        )

    @app.get("/quote", response_class=HTMLResponse)
    async def quote_page(request: Request):
        uid = _auth_or_redirect(request)
        if isinstance(uid, RedirectResponse):
            return uid
        market = app.state.repo.get_selected_market(uid)
        q = (request.query_params.get("q") or "").strip()
        symbol = (request.query_params.get("symbol") or "").strip()
        suggestions: list[dict[str, Any]] = []
        quote: dict[str, Any] | None = None
        news: list[dict[str, Any]] = []
        quote_chart: dict[str, Any] = {"dates": [], "open": [], "high": [], "low": [], "close": [], "volume": []}
        quote_actions: dict[str, Any] = {"dividends": [], "splits": []}
        if q:
            suggestions = app.state.market_data.search_symbols(q, market, limit=8)
        if symbol:
            resolved = app.state.market_data.resolve_symbol(symbol, market)
            quote = app.state.market_data.quote(resolved, market)
            news = app.state.market_data.stock_news(resolved, market, limit=8)
            quote_chart = app.state.market_data.quote_history(resolved, market, period="1y", interval="1d")
            quote_actions = app.state.market_data.quote_corporate_actions(resolved, market, limit=8)
            if not suggestions and q:
                suggestions = app.state.market_data.search_symbols(q, market, limit=8)
        return templates.TemplateResponse(
            request,
            "quote.html",
            _context(
                request,
                {
                    "query": q,
                    "quote": quote,
                    "quote_news": news,
                    "quote_chart": quote_chart,
                    "quote_actions": quote_actions,
                    "suggestions": suggestions,
                },
            ),
        )

    @app.get("/watchlist", response_class=HTMLResponse)
    async def watchlist_page(request: Request):
        uid = _auth_or_redirect(request)
        if isinstance(uid, RedirectResponse):
            return uid
        market = app.state.repo.get_selected_market(uid)
        watchlist = app.state.repo.ensure_default_watchlist(uid)
        rows: list[dict[str, Any]] = []
        for symbol in watchlist.get("symbols", []):
            try:
                quote = app.state.market_data.quote(symbol, market)
                rows.append(
                    {
                        "symbol": quote.get("symbol"),
                        "name": quote.get("name"),
                        "price": quote.get("price"),
                        "day_change": quote.get("change_pct"),
                        "week_change": round(_f(quote.get("change_pct")) * 2.1, 2),
                        "month_change": round(_f(quote.get("change_pct")) * 4.4, 2),
                    }
                )
            except Exception:
                continue
        return templates.TemplateResponse(
            request,
            "watchlist.html",
            _context(request, {"watchlist": watchlist, "watch_rows": rows}),
        )

    @app.post("/watchlist/add")
    async def add_watchlist_symbol(request: Request, symbol: str = Form(...)):
        uid = _auth_or_redirect(request)
        if isinstance(uid, RedirectResponse):
            return uid
        try:
            market = app.state.repo.get_selected_market(uid)
            resolved = app.state.market_data.resolve_symbol(symbol, market)
            app.state.repo.add_symbol_to_default_watchlist(uid, resolved)
            return _redirect("/watchlist", message=f"Added {resolved} to your watchlist.")
        except Exception as exc:
            return _redirect("/watchlist", error=f"Could not add symbol: {exc}")

    @app.post("/watchlist/remove")
    async def remove_watchlist_symbol(request: Request, symbol: str = Form(...)):
        uid = _auth_or_redirect(request)
        if isinstance(uid, RedirectResponse):
            return uid
        app.state.repo.remove_symbol_from_default_watchlist(uid, symbol)
        return _redirect("/watchlist", message=f"Removed {symbol.upper()} from watchlist.")

    @app.get("/buy", response_class=HTMLResponse)
    async def buy_page(request: Request):
        uid = _auth_or_redirect(request)
        if isinstance(uid, RedirectResponse):
            return uid
        return templates.TemplateResponse(request, "buy.html", _context(request, {}))

    @app.post("/buy")
    async def buy_submit(
        request: Request,
        symbol: str = Form(...),
        quantity: int = Form(...),
        notes: str = Form(""),
    ):
        uid = _auth_or_redirect(request)
        if isinstance(uid, RedirectResponse):
            return uid
        try:
            market = app.state.repo.get_selected_market(uid)
            resolved = app.state.market_data.resolve_symbol(symbol, market)
            quote = app.state.market_data.quote(resolved, market)
            app.state.learning_engine.save_checklist(
                uid,
                {
                    "thesis": notes or f"Buy setup for {resolved}",
                    "risk_level": "medium",
                    "time_horizon": "2-4 weeks",
                    "buy_reason": "Portfolio learning setup",
                    "trade_type": "speculative",
                    "stop_loss_awareness": True,
                },
            )
            app.state.repo.apply_trade(
                uid=uid,
                market=market,
                side="buy",
                symbol=resolved,
                quantity=quantity,
                price=_f(quote.get("price")),
                order_type="market",
                notes=notes,
            )
            return _redirect("/buy", message=f"Buy order executed: {quantity} x {resolved}")
        except Exception as exc:
            return _redirect("/buy", error=f"Buy failed: {exc}")

    @app.get("/sell", response_class=HTMLResponse)
    async def sell_page(request: Request):
        uid = _auth_or_redirect(request)
        if isinstance(uid, RedirectResponse):
            return uid
        market = app.state.repo.get_selected_market(uid)
        portfolio = app.state.repo.get_portfolio(uid, market)
        owned_symbols = [row.get("symbol") for row in portfolio.get("positions", []) if row.get("symbol")]
        return templates.TemplateResponse(
            request,
            "sell.html",
            _context(request, {"owned_symbols": owned_symbols}),
        )

    @app.post("/sell")
    async def sell_submit(
        request: Request,
        symbol: str = Form(...),
        quantity: int = Form(...),
        notes: str = Form(""),
    ):
        uid = _auth_or_redirect(request)
        if isinstance(uid, RedirectResponse):
            return uid
        try:
            market = app.state.repo.get_selected_market(uid)
            resolved = app.state.market_data.resolve_symbol(symbol, market)
            quote = app.state.market_data.quote(resolved, market)
            app.state.repo.apply_trade(
                uid=uid,
                market=market,
                side="sell",
                symbol=resolved,
                quantity=quantity,
                price=_f(quote.get("price")),
                order_type="market",
                notes=notes,
            )
            return _redirect("/sell", message=f"Sell order executed: {quantity} x {resolved}")
        except Exception as exc:
            return _redirect("/sell", error=f"Sell failed: {exc}")

    @app.get("/orders", response_class=HTMLResponse)
    async def orders_page(request: Request):
        uid = _auth_or_redirect(request)
        if isinstance(uid, RedirectResponse):
            return uid
        market = app.state.repo.get_selected_market(uid)
        fills = _process_open_orders(uid, market)
        orders = app.state.repo.list_orders(uid, market)
        extra_message = request.query_params.get("message", "")
        if fills > 0 and not extra_message:
            extra_message = f"{fills} order(s) filled on latest market check."
        return templates.TemplateResponse(
            request,
            "orders.html",
            _context(request, {"orders": orders, "flash": extra_message}),
        )

    @app.post("/orders/place")
    async def place_order(
        request: Request,
        symbol: str = Form(...),
        quantity: int = Form(...),
        side: str = Form("buy"),
        order_type: str = Form("limit"),
        trigger_price: float | None = Form(None),
        notes: str = Form(""),
    ):
        uid = _auth_or_redirect(request)
        if isinstance(uid, RedirectResponse):
            return uid
        try:
            market = app.state.repo.get_selected_market(uid)
            resolved = app.state.market_data.resolve_symbol(symbol, market)
            if order_type == "market":
                trigger_price = None
            app.state.repo.create_order(
                uid=uid,
                market=market,
                side=side,
                symbol=resolved,
                quantity=quantity,
                order_type=order_type,
                trigger_price=trigger_price,
                notes=notes,
            )
            return _redirect("/orders", message=f"Order placed for {resolved}.")
        except Exception as exc:
            return _redirect("/orders", error=f"Order placement failed: {exc}")

    @app.get("/history", response_class=HTMLResponse)
    async def history_page(request: Request):
        uid = _auth_or_redirect(request)
        if isinstance(uid, RedirectResponse):
            return uid
        market = app.state.repo.get_selected_market(uid)
        filter_q = (request.query_params.get("q") or "").strip().lower()
        trades = app.state.repo.list_trades(uid, market=market)
        if filter_q:
            trades = [
                row
                for row in trades
                if filter_q in str(row.get("symbol", "")).lower()
                or filter_q in str(row.get("side", "")).lower()
                or filter_q in str(row.get("order_type", "")).lower()
            ]
        return templates.TemplateResponse(
            request,
            "history.html",
            _context(request, {"trades": trades, "filter_q": filter_q}),
        )

    @app.get("/journal", response_class=HTMLResponse)
    async def journal_page(request: Request):
        uid = _auth_or_redirect(request)
        if isinstance(uid, RedirectResponse):
            return uid
        market = app.state.repo.get_selected_market(uid)
        trades = app.state.repo.list_trades(uid, market=market)
        entries = []
        for trade in trades:
            entries.append({"trade": trade, "journal": app.state.repo.get_trade_journal(uid, trade["id"])})
        return templates.TemplateResponse(
            request,
            "journal.html",
            _context(request, {"entries": entries}),
        )

    @app.post("/journal/update")
    async def journal_update(
        request: Request,
        trade_id: str = Form(...),
        thesis: str = Form(""),
        reason_for_entry: str = Form(""),
        reason_for_exit: str = Form(""),
        lessons_learned: str = Form(""),
        outcome_review: str = Form(""),
    ):
        uid = _auth_or_redirect(request)
        if isinstance(uid, RedirectResponse):
            return uid
        app.state.repo.upsert_trade_journal(
            uid,
            trade_id,
            {
                "thesis": thesis,
                "reason_for_entry": reason_for_entry,
                "reason_for_exit": reason_for_exit,
                "lessons_learned": lessons_learned,
                "outcome_review": outcome_review,
            },
        )
        return _redirect("/journal", message="Trade journal updated.")

    @app.get("/portfolio-insights", response_class=HTMLResponse)
    async def portfolio_insights_page(request: Request):
        uid = _auth_or_redirect(request)
        if isinstance(uid, RedirectResponse):
            return uid
        market = app.state.repo.get_selected_market(uid)
        health = app.state.learning_engine.health_score(uid, market)
        base_explanation = app.state.learning_engine.explain_portfolio(uid, market)
        move_why = app.state.learning_engine.portfolio_move_why(uid, market)
        portfolio = app.state.repo.get_portfolio(uid, market)
        explanation = app.state.ai_advisor.portfolio_explainer(
            uid=uid,
            market=market,
            payload={
                "plain_english": base_explanation.get("plain_english"),
                "portfolio": portfolio,
                "health": health,
                "move_why": move_why,
            },
        )
        return templates.TemplateResponse(
            request,
            "portfolio_insights.html",
            _context(request, {"health": health, "explanation": explanation, "move_why": move_why}),
        )

    @app.get("/portfolio-goals", response_class=HTMLResponse)
    async def portfolio_goals_page(request: Request):
        uid = _auth_or_redirect(request)
        if isinstance(uid, RedirectResponse):
            return uid
        market = app.state.repo.get_selected_market(uid)
        portfolio = app.state.repo.get_portfolio(uid, market)
        perf = app.state.repo.get_portfolio_performance(uid, market)
        goal = app.state.repo.get_learning_doc(
            uid,
            "portfolio_goal",
            default={"target_value": 250000.0, "target_return_pct": 25.0},
        )
        progress_value = (_f(portfolio.get("total_value")) / _f(goal.get("target_value"), 1)) * 100 if _f(goal.get("target_value")) else 0.0
        progress_return = (_f(perf.get("return_total_pct")) / _f(goal.get("target_return_pct"), 1)) * 100 if _f(goal.get("target_return_pct")) else 0.0
        return templates.TemplateResponse(
            request,
            "goals.html",
            _context(
                request,
                {
                    "goal": goal,
                    "portfolio": portfolio,
                    "performance": perf,
                    "progress_value": round(progress_value, 2),
                    "progress_return": round(progress_return, 2),
                },
            ),
        )

    @app.post("/portfolio-goals")
    async def portfolio_goals_submit(
        request: Request,
        target_value: float = Form(...),
        target_return_pct: float = Form(...),
    ):
        uid = _auth_or_redirect(request)
        if isinstance(uid, RedirectResponse):
            return uid
        app.state.repo.set_learning_doc(
            uid,
            "portfolio_goal",
            {"target_value": target_value, "target_return_pct": target_return_pct},
            merge=True,
        )
        return _redirect("/portfolio-goals", message="Portfolio goals saved.")

    @app.get("/trade-analytics", response_class=HTMLResponse)
    async def trade_analytics_page(request: Request):
        uid = _auth_or_redirect(request)
        if isinstance(uid, RedirectResponse):
            return uid
        market = app.state.repo.get_selected_market(uid)
        trades = app.state.repo.list_trades(uid, market=market)
        buys = [t for t in trades if str(t.get("side")) == "buy"]
        sells = [t for t in trades if str(t.get("side")) == "sell"]
        realized = sum(_f(t.get("realized_pnl")) for t in trades)
        avg_trade_value = sum(_f(t.get("trade_value")) for t in trades) / len(trades) if trades else 0.0
        return templates.TemplateResponse(
            request,
            "trade_analytics.html",
            _context(
                request,
                {
                    "trades": trades[:12],
                    "analytics": {
                        "total_trades": len(trades),
                        "buy_count": len(buys),
                        "sell_count": len(sells),
                        "realized_pnl": round(realized, 2),
                        "avg_trade_value": round(avg_trade_value, 2),
                    },
                },
            ),
        )

    @app.get("/weekly-summary", response_class=HTMLResponse)
    async def weekly_summary_page(request: Request):
        uid = _auth_or_redirect(request)
        if isinstance(uid, RedirectResponse):
            return uid
        market = app.state.repo.get_selected_market(uid)
        summary = app.state.learning_engine.weekly_summary(uid, market)
        summary_tip = app.state.ai_advisor.tool_tip(
            uid=uid,
            market=market,
            topic="weekly-summary",
            payload=summary,
        )
        return templates.TemplateResponse(
            request,
            "weekly_summary.html",
            _context(request, {"summary": summary, "summary_tip": summary_tip}),
        )

    @app.get("/leaderboard", response_class=HTMLResponse)
    async def leaderboard_page(request: Request):
        uid = _auth_or_redirect(request)
        if isinstance(uid, RedirectResponse):
            return uid
        streaks = app.state.repo.get_learning_doc(
            uid,
            "streaks",
            default={"learning_streak_days": 0, "quiz_streak_days": 0, "challenge_streak_days": 0},
        )
        quizzes = app.state.repo.get_learning_doc(uid, "quizzes", default={"completed": 0, "streak": 0})
        return templates.TemplateResponse(
            request,
            "leaderboard.html",
            _context(request, {"streaks": streaks, "quizzes": quizzes}),
        )

    @app.get("/risk-lab", response_class=HTMLResponse)
    async def risk_lab_page(request: Request):
        uid = _auth_or_redirect(request)
        if isinstance(uid, RedirectResponse):
            return uid
        market = app.state.repo.get_selected_market(uid)
        symbol = (request.query_params.get("symbol") or "").strip().upper()
        if not symbol:
            portfolio = app.state.repo.get_portfolio(uid, market)
            symbol = (portfolio.get("positions") or [{"symbol": "AAPL"}])[0]["symbol"]
        risk = app.state.market_data.risk_lite(symbol, market)
        risk_tip = app.state.ai_advisor.tool_tip(uid=uid, market=market, topic="risk", payload=risk)
        return templates.TemplateResponse(
            request,
            "risk_lab.html",
            _context(request, {"symbol": symbol, "risk": risk, "risk_tip": risk_tip}),
        )

    @app.get("/ai-forecast", response_class=HTMLResponse)
    async def ai_forecast_page(request: Request):
        uid = _auth_or_redirect(request)
        if isinstance(uid, RedirectResponse):
            return uid
        market = app.state.repo.get_selected_market(uid)
        symbol = (request.query_params.get("symbol") or "AAPL").strip().upper()
        forecast = app.state.market_data.forecast_lite(symbol, market)
        portfolio = app.state.repo.get_portfolio(uid, market)
        portfolio_explainer = app.state.ai_advisor.portfolio_explainer(
            uid=uid,
            market=market,
            payload={"portfolio": portfolio},
        )
        forecast_ai = app.state.ai_advisor.forecast_explainer(
            uid=uid,
            market=market,
            symbol=symbol,
            payload={
                "forecast": forecast,
                "portfolio": portfolio,
                "market_mood": app.state.market_data.market_mood(market),
                "headlines": app.state.market_data.stock_news(symbol, market, limit=3),
            },
        )
        return templates.TemplateResponse(
            request,
            "ai_forecast.html",
            _context(
                request,
                {
                    "symbol": symbol,
                    "forecast": forecast,
                    "forecast_ai": forecast_ai,
                    "portfolio_explainer": portfolio_explainer,
                },
            ),
        )

    @app.get("/ai-chat", response_class=HTMLResponse)
    async def ai_chat_page(request: Request):
        uid = _auth_or_redirect(request)
        if isinstance(uid, RedirectResponse):
            return uid
        market = app.state.repo.get_selected_market(uid)
        history = _load_chat_history(uid, market)
        starters = [
            "Explain my portfolio like I am 15.",
            "What should I improve before my next paper trade?",
            "How does today's market mood affect my holdings?",
            "Give me a simple plan for my weakest position.",
        ]
        return templates.TemplateResponse(
            request,
            "ai_chat.html",
            _context(request, {"chat_history": history, "chat_starters": starters}),
        )

    @app.post("/ai-chat")
    async def ai_chat_submit(request: Request, message: str = Form("")):
        uid = _auth_or_redirect(request)
        if isinstance(uid, RedirectResponse):
            return uid
        market = app.state.repo.get_selected_market(uid)
        text = str(message or "").strip()
        if not text:
            return _redirect("/ai-chat", error="Please type a question for the AI coach.")

        history = _load_chat_history(uid, market)
        context_payload = {
            "market": market,
            "dashboard": app.state.learning_engine.dashboard(uid, market),
            "portfolio": app.state.repo.get_portfolio(uid, market),
            "health": app.state.learning_engine.health_score(uid, market),
            "mistakes": app.state.learning_engine.mistake_detection(uid, market),
            "weekly_summary": app.state.learning_engine.weekly_summary(uid, market),
            "market_mood": app.state.market_data.market_mood(market),
            "news": app.state.market_data.market_news(market, limit=5),
        }
        ai_response = app.state.ai_advisor.chat_reply(
            uid=uid,
            market=market,
            message=text,
            history=history,
            context=context_payload,
        )
        updated = history + [
            {"role": "user", "content": text, "created_at": _utc_now_iso()},
            {"role": "assistant", "content": str(ai_response.get("reply") or "").strip(), "created_at": _utc_now_iso()},
        ]
        _save_chat_history(uid, market, updated)
        return _redirect("/ai-chat")

    @app.post("/ai-chat/clear")
    async def ai_chat_clear(request: Request):
        uid = _auth_or_redirect(request)
        if isinstance(uid, RedirectResponse):
            return uid
        market = app.state.repo.get_selected_market(uid)
        _save_chat_history(uid, market, [])
        return _redirect("/ai-chat", message="AI chat history cleared.")

    @app.get("/market-mood", response_class=HTMLResponse)
    async def market_mood_page(request: Request):
        uid = _auth_or_redirect(request)
        if isinstance(uid, RedirectResponse):
            return uid
        market = app.state.repo.get_selected_market(uid)
        mood = app.state.market_data.market_mood(market)
        mood_tip = app.state.ai_advisor.tool_tip(uid=uid, market=market, topic="market-mood", payload=mood)
        return templates.TemplateResponse(
            request,
            "market_mood.html",
            _context(request, {"mood": mood, "mood_tip": mood_tip}),
        )

    @app.get("/scenario-simulator", response_class=HTMLResponse)
    async def scenario_page(request: Request):
        uid = _auth_or_redirect(request)
        if isinstance(uid, RedirectResponse):
            return uid
        market = app.state.repo.get_selected_market(uid)
        market_move_pct = _f(request.query_params.get("market_move_pct"), 0.0)
        add_cash = _f(request.query_params.get("add_cash"), 0.0)
        portfolio = app.state.repo.get_portfolio(uid, market)
        scenario_value = _f(portfolio.get("market_value")) * (1 + market_move_pct / 100) + _f(portfolio.get("cash")) + add_cash
        current_value = _f(portfolio.get("total_value"))
        delta_pct = ((scenario_value - current_value) / current_value * 100) if current_value else 0.0
        scenario_tip = app.state.ai_advisor.tool_tip(
            uid=uid,
            market=market,
            topic="scenario",
            payload={
                "current_value": round(current_value, 2),
                "scenario_value": round(scenario_value, 2),
                "delta_pct": round(delta_pct, 2),
                "market_move_pct": market_move_pct,
                "add_cash": add_cash,
            },
        )
        return templates.TemplateResponse(
            request,
            "scenario.html",
            _context(
                request,
                {
                    "market_move_pct": market_move_pct,
                    "add_cash": add_cash,
                    "current_value": round(current_value, 2),
                    "scenario_value": round(scenario_value, 2),
                    "delta_pct": round(delta_pct, 2),
                    "scenario_tip": scenario_tip,
                },
            ),
        )

    @app.get("/screener", response_class=HTMLResponse)
    async def screener_page(request: Request):
        uid = _auth_or_redirect(request)
        if isinstance(uid, RedirectResponse):
            return uid
        market = app.state.repo.get_selected_market(uid)
        preset = (request.query_params.get("preset") or "top_gainers").strip()
        rows = app.state.market_data.screener(market, preset=preset, limit=25)
        screener_tip = app.state.ai_advisor.tool_tip(
            uid=uid,
            market=market,
            topic=f"screener-{preset}",
            payload={"total_results": len(rows), "top_rows": rows[:5]},
        )
        return templates.TemplateResponse(
            request,
            "screener.html",
            _context(request, {"preset": preset, "rows": rows, "screener_tip": screener_tip}),
        )

    @app.get("/alerts", response_class=HTMLResponse)
    async def alerts_page(request: Request):
        uid = _auth_or_redirect(request)
        if isinstance(uid, RedirectResponse):
            return uid
        alerts = app.state.repo.list_alerts(uid)
        notifications = app.state.repo.list_notifications(uid)
        return templates.TemplateResponse(
            request,
            "alerts.html",
            _context(request, {"alerts": alerts, "notifications": notifications}),
        )

    @app.post("/alerts/add")
    async def alerts_add(
        request: Request,
        alert_type: str = Form("price"),
        symbol: str = Form(""),
        direction: str = Form("above"),
        target: float | None = Form(None),
        message: str = Form(""),
    ):
        uid = _auth_or_redirect(request)
        if isinstance(uid, RedirectResponse):
            return uid
        market = app.state.repo.get_selected_market(uid)
        resolved_symbol = app.state.market_data.resolve_symbol(symbol, market) if symbol else ""
        app.state.repo.create_alert(
            uid,
            {
                "type": alert_type,
                "symbol": resolved_symbol,
                "direction": direction,
                "target": target,
                "message": message,
            },
        )
        return _redirect("/alerts", message="Alert added.")

    @app.post("/alerts/delete")
    async def alerts_delete(request: Request, alert_id: str = Form(...)):
        uid = _auth_or_redirect(request)
        if isinstance(uid, RedirectResponse):
            return uid
        app.state.repo.delete_alert(uid, alert_id)
        return _redirect("/alerts", message="Alert deleted.")

    @app.get("/login", response_class=HTMLResponse)
    async def login_page(request: Request):
        return templates.TemplateResponse(request, "login.html", _context(request))

    @app.get("/register", response_class=HTMLResponse)
    async def register_page(request: Request):
        return templates.TemplateResponse(request, "register.html", _context(request))

    @app.get("/instructions", response_class=HTMLResponse)
    async def instructions(request: Request):
        return templates.TemplateResponse(request, "instructions.html", _context(request))

    return app


app = create_app()
