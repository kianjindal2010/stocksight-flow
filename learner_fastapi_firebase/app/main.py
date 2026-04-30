from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from pathlib import Path
from time import perf_counter
from typing import Any
from urllib.parse import urlencode

from fastapi import FastAPI, Form, HTTPException, Request
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
from .services.chat_context import build_ai_chat_context, build_ai_user_context
from .services.learning_engine import LearningEngine
from .services.market_data import MarketDataService
from .services import quiz_bank

logger = logging.getLogger(__name__)


BASE_DIR = Path(__file__).resolve().parent.parent
TEMPLATES_DIR = BASE_DIR / "templates"
STATIC_DIR = BASE_DIR / "static"
PREVIEW_UID = "public_preview_user"
PREVIEW_EMAIL = "preview@stocksight.local"


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


def _i(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _currency_symbol(code: str) -> str:
    mapping = {"USD": "$", "INR": "Rs.", "GBP": "GBP "}
    return mapping.get(code.upper(), f"{code.upper()} ")


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _parse_goal_deadline(value: Any) -> datetime | None:
    raw = str(value or "").strip()
    if not raw:
        return None
    try:
        return datetime.strptime(raw, "%Y-%m-%d").replace(tzinfo=timezone.utc)
    except ValueError:
        return None


def _goal_deadline_status(goal: dict[str, Any]) -> dict[str, Any]:
    deadline_dt = _parse_goal_deadline(goal.get("target_deadline"))
    if not deadline_dt:
        return {
            "has_deadline": False,
            "target_deadline": "",
            "days_left": None,
            "is_due_today": False,
            "is_overdue": False,
            "label": "No deadline set",
        }
    today = datetime.now(timezone.utc).date()
    deadline_date = deadline_dt.date()
    days_left = (deadline_date - today).days
    if days_left > 0:
        label = f"{days_left} day{'s' if days_left != 1 else ''} left"
    elif days_left == 0:
        label = "Due today"
    else:
        overdue_days = abs(days_left)
        label = f"Overdue by {overdue_days} day{'s' if overdue_days != 1 else ''}"
    return {
        "has_deadline": True,
        "target_deadline": deadline_date.isoformat(),
        "days_left": days_left,
        "is_due_today": days_left == 0,
        "is_overdue": days_left < 0,
        "label": label,
    }


def _quiz_default_doc() -> dict[str, Any]:
    return quiz_bank.quiz_default_doc()


def _quiz_question_bank(
    curriculum: list[dict[str, Any]] | None = None,
    module_id: str | None = None,
) -> list[dict[str, Any]]:
    generated = quiz_bank.quiz_question_bank(curriculum or [], module_id=module_id)
    if generated:
        return generated
    return [
        {
            "id": "q1",
            "module": "Market Basics",
            "prompt": "What does owning one share of a company represent?",
            "choices": [
                "A fixed loan to the company",
                "A small ownership stake in the company",
                "A guarantee of yearly profit",
                "A short-term insurance contract",
            ],
            "answer_index": 1,
            "explanation": "A stock share is equity ownership, not a loan or guaranteed return.",
        },
        {
            "id": "q2",
            "module": "Risk and Return",
            "prompt": "Higher expected return usually comes with:",
            "choices": [
                "Lower risk",
                "No risk at all",
                "Higher risk",
                "Fixed and predictable outcomes",
            ],
            "answer_index": 2,
            "explanation": "Risk and return are generally linked. Higher expected upside typically means higher uncertainty.",
        },
        {
            "id": "q3",
            "module": "Diversification",
            "prompt": "Diversification helps mainly by:",
            "choices": [
                "Eliminating all market risk",
                "Spreading risk across different assets",
                "Guaranteeing profit every month",
                "Replacing research with random picks",
            ],
            "answer_index": 1,
            "explanation": "Diversification lowers concentration risk, but cannot remove all market risk.",
        },
        {
            "id": "q4",
            "module": "Order Types",
            "prompt": "A limit buy order executes when price is:",
            "choices": [
                "At or below your limit price",
                "At any price immediately",
                "Only above your limit price",
                "Only at market close",
            ],
            "answer_index": 0,
            "explanation": "A limit buy sets a maximum purchase price.",
        },
        {
            "id": "q5",
            "module": "Order Types",
            "prompt": "A stop-loss order is mainly used to:",
            "choices": [
                "Increase leverage quickly",
                "Lock in a fixed profit",
                "Limit downside on a position",
                "Predict future earnings",
            ],
            "answer_index": 2,
            "explanation": "Stop-loss orders are a risk-control tool that can cap downside when price moves against you.",
        },
        {
            "id": "q6",
            "module": "Long-Term Investing",
            "prompt": "Compounding works best when you:",
            "choices": [
                "Invest consistently for long periods",
                "Trade all-in on one stock",
                "Withdraw gains every week",
                "Ignore position sizing",
            ],
            "answer_index": 0,
            "explanation": "Compounding benefits from time and consistency.",
        },
        {
            "id": "q7",
            "module": "Behavioral Finance",
            "prompt": "Which is a common behavioral mistake?",
            "choices": [
                "Writing a trade thesis before entry",
                "Panic selling after short-term volatility",
                "Using position size limits",
                "Reviewing losing trades for lessons",
            ],
            "answer_index": 1,
            "explanation": "Emotion-driven panic selling is a classic behavioral bias.",
        },
        {
            "id": "q8",
            "module": "ETFs and Mutual Funds",
            "prompt": "An ETF is typically:",
            "choices": [
                "A single-company stock",
                "A fund holding a basket of assets",
                "A guaranteed-return bond",
                "A bank savings account",
            ],
            "answer_index": 1,
            "explanation": "ETFs usually hold diversified baskets and trade like stocks.",
        },
        {
            "id": "q9",
            "module": "Portfolio Discipline",
            "prompt": "Position sizing is important because it:",
            "choices": [
                "Makes every trade a winner",
                "Controls how much one mistake can hurt",
                "Eliminates market volatility",
                "Removes the need for stop-losses",
            ],
            "answer_index": 1,
            "explanation": "Sizing limits damage from any single bad trade.",
        },
        {
            "id": "q10",
            "module": "Market Awareness",
            "prompt": "A strong negative market mood should usually make you:",
            "choices": [
                "Increase risk aggressively",
                "Ignore your risk plan",
                "Review risk controls and stay selective",
                "Double every losing position",
            ],
            "answer_index": 2,
            "explanation": "Weak sentiment is a signal to tighten discipline and risk checks.",
        },
    ]


def _quiz_report(questions: list[dict[str, Any]], selected_answers: dict[str, str]) -> dict[str, Any]:
    details: list[dict[str, Any]] = []
    correct = 0
    unanswered = 0
    for question in questions:
        question_id = str(question.get("id") or "")
        choices = question.get("choices") if isinstance(question.get("choices"), list) else []
        selected_raw = str(selected_answers.get(question_id, "")).strip()
        selected_idx = _i(selected_raw, -1)
        in_range = 0 <= selected_idx < len(choices)
        selected_text = str(choices[selected_idx]) if in_range else ""
        answer_idx = _i(question.get("answer_index"), -1)
        answer_in_range = 0 <= answer_idx < len(choices)
        correct_text = str(choices[answer_idx]) if answer_in_range else ""
        is_correct = in_range and answer_in_range and selected_idx == answer_idx
        if not in_range:
            unanswered += 1
        if is_correct:
            correct += 1
        details.append(
            {
                "id": question_id,
                "prompt": str(question.get("prompt") or ""),
                "selected_text": selected_text,
                "correct_text": correct_text,
                "is_correct": is_correct,
                "explanation": str(question.get("explanation") or ""),
            }
        )
    total = len(questions)
    safe_total = max(1, total)
    score_pct = int(round((correct / safe_total) * 100))
    return {
        "total": total,
        "correct": correct,
        "incorrect": max(0, total - correct),
        "unanswered": unanswered,
        "score_pct": score_pct,
        "passed": score_pct >= 70,
        "details": details,
    }


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
        started = perf_counter()
        status_code = 500
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
        response = await call_next(request)
        status_code = int(getattr(response, "status_code", 500))
        elapsed_ms = (perf_counter() - started) * 1000
        logger.info(
            "request_timing method=%s path=%s status=%s duration_ms=%.2f",
            request.method,
            request.url.path,
            status_code,
            elapsed_ms,
        )
        return response

    app.include_router(build_api_router())

    def _uid(request: Request) -> str | None:
        user = getattr(request.state, "current_user", None)
        if not user:
            return None
        uid = str(user.get("uid") or "")
        return uid or None

    def _ensure_preview_user() -> str:
        app.state.repo.ensure_user(PREVIEW_UID, email=PREVIEW_EMAIL, display_name="Preview Guest")
        app.state.repo.set_selected_market(PREVIEW_UID, "US")
        portfolio = app.state.repo.get_portfolio(PREVIEW_UID, "US")
        if not portfolio.get("positions"):
            demo_trades = [
                ("AAPL", 8, 178.0, "AI platform leader demo holding"),
                ("MSFT", 4, 410.0, "Quality software cash-flow demo holding"),
                ("NVDA", 3, 830.0, "High-volatility semiconductor demo holding"),
            ]
            for symbol, quantity, price, thesis in demo_trades:
                result = app.state.repo.apply_trade(
                    uid=PREVIEW_UID,
                    market="US",
                    side="buy",
                    symbol=symbol,
                    quantity=quantity,
                    price=price,
                    order_type="market",
                    notes=thesis,
                )
                trade_id = str((result.get("trade") or {}).get("id") or "")
                if trade_id:
                    app.state.repo.upsert_trade_journal(
                        PREVIEW_UID,
                        trade_id,
                        {
                            "thesis": thesis,
                            "reason_for_entry": "Demo preview trade showing how the journal informs AI coaching.",
                            "lessons_learned": "Keep position size controlled and write the risk plan before buying.",
                            "outcome_review": "Preview data only.",
                        },
                    )
            app.state.repo.deposit_cash(PREVIEW_UID, "US", 5000.0, notes="Demo preview top-up")
            app.state.repo.set_learning_doc(
                PREVIEW_UID,
                "portfolio_goal",
                {"target_value": 30000.0, "target_return_pct": 12.0, "target_deadline": "2026-12-31"},
                merge=True,
            )
        return PREVIEW_UID

    def _preview_uid(request: Request) -> str | None:
        if _uid(request):
            return None
        if request.method not in {"GET", "HEAD"}:
            return None
        uid = _ensure_preview_user()
        request.state.preview_mode = True
        request.state.current_user = {"uid": uid, "email": PREVIEW_EMAIL, "name": "Preview Guest", "preview": True}
        return uid

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
            "preview_mode": bool(getattr(request.state, "preview_mode", False)),
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
            preview_uid = _preview_uid(request)
            if preview_uid:
                return preview_uid
            return RedirectResponse(url="/login", status_code=303)
        return uid

    def _run_parallel(
        tasks: dict[str, Any],
        max_workers: int = 8,
    ) -> dict[str, Any]:
        if not tasks:
            return {}
        workers = max(1, min(max_workers, len(tasks)))
        results: dict[str, Any] = {}
        with ThreadPoolExecutor(max_workers=workers) as pool:
            futures = {name: pool.submit(fn) for name, fn in tasks.items()}
            for name, fut in futures.items():
                try:
                    results[name] = fut.result()
                except Exception as exc:
                    logger.exception("parallel_task_failed task=%s error=%s", name, exc)
        return results

    def _dashboard_position_rows(
        positions: list[dict[str, Any]],
    ) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
        for pos in positions:
            avg = _f(pos.get("avg_price"))
            last = _f(pos.get("last_price"))
            total_change_pct = round(((last - avg) / avg * 100) if avg else 0.0, 2)
            day_change_pct = round(_f(pos.get("day_change_pct"), total_change_pct), 2)
            pos["total_change_pct"] = total_change_pct
            pos["day_change_pct"] = day_change_pct
            pos["change_pct"] = day_change_pct
            pos["market_value"] = round(_f(pos.get("market_value")), 2)
            pos["unrealized_pnl"] = round(_f(pos.get("unrealized_pnl")), 2)
        top_positions = sorted(
            [row for row in positions if _f(row.get("day_change_pct")) > 0],
            key=lambda row: _f(row.get("day_change_pct")),
            reverse=True,
        )[:4]
        worst_positions = sorted(
            [row for row in positions if _f(row.get("day_change_pct")) < 0],
            key=lambda row: _f(row.get("day_change_pct")),
        )[:4]
        return positions, top_positions, worst_positions

    def _advisor_user_context(uid: str, market: str) -> dict[str, Any]:
        return build_ai_user_context(
            uid=uid,
            market=market,
            repo=app.state.repo,
            learning_engine=app.state.learning_engine,
            market_data=app.state.market_data,
        )

    def _coach_loading_placeholder() -> dict[str, Any]:
        return {
            "headline": "AI Coach",
            "summary": "Loading personalized coaching insight...",
            "risk_level": "Medium",
            "actions": [
                "Loading your next steps...",
                "Loading your risk guidance...",
                "Loading your headline watchlist...",
            ],
            "news_watch": ["Loading market context..."],
            "disclaimer": "For education and paper trading only, not financial advice.",
            "source": "loading",
            "generated_at": _utc_now_iso(),
            "model": "loading",
        }

    def _quote_ai_loading_placeholder() -> dict[str, Any]:
        return {
            "action": "Hold",
            "buy_score": 50,
            "confidence": 50,
            "news_bias": "Neutral",
            "summary": "Loading AI quote verdict...",
            "factors": [
                "Loading trend signal...",
                "Loading risk profile...",
                "Loading news sentiment...",
            ],
            "disclaimer": "Educational signal for paper trading only, not financial advice.",
            "source": "loading",
            "generated_at": _utc_now_iso(),
            "model": "loading",
        }

    def _evaluate_order_trigger(order: dict[str, Any], last_price: float) -> tuple[bool, dict[str, Any]]:
        if str(order.get("status")) != "open":
            return False, {}
        order_type = str(order.get("order_type") or "limit").lower()
        side = str(order.get("side") or "buy").lower()
        if order_type == "market":
            return True, {}
        trigger = order.get("trigger_price")
        if order_type == "limit":
            if trigger is None:
                return False, {}
            trigger_price = _f(trigger)
            if trigger_price <= 0:
                return False, {}
            if side == "buy":
                return last_price <= trigger_price, {}
            return last_price >= trigger_price, {}
        if order_type == "stop_loss":
            if trigger is None:
                return False, {}
            trigger_price = _f(trigger)
            if trigger_price <= 0:
                return False, {}
            if side == "buy":
                return last_price >= trigger_price, {}
            return last_price <= trigger_price, {}
        if order_type == "trailing_stop":
            trail_percent_raw = order.get("trail_percent")
            trail_amount_raw = order.get("trail_amount")
            trail_percent = _f(trail_percent_raw) if trail_percent_raw is not None else None
            trail_amount = _f(trail_amount_raw) if trail_amount_raw is not None else None
            previous_anchor = _f(order.get("trail_anchor_price"))
            anchor = previous_anchor if previous_anchor > 0 else last_price
            if side == "buy":
                anchor = min(anchor, last_price)
                if trail_percent is not None and trail_percent > 0:
                    trigger_price = anchor * (1 + trail_percent / 100)
                elif trail_amount is not None and trail_amount > 0:
                    trigger_price = anchor + trail_amount
                else:
                    return False, {}
                updates = {"trail_anchor_price": round(anchor, 4), "trigger_price": round(trigger_price, 4)}
                return last_price >= trigger_price, updates
            anchor = max(anchor, last_price)
            if trail_percent is not None and trail_percent > 0:
                trigger_price = anchor * (1 - trail_percent / 100)
            elif trail_amount is not None and trail_amount > 0:
                trigger_price = anchor - trail_amount
            else:
                return False, {}
            trigger_price = max(0.01, trigger_price)
            updates = {"trail_anchor_price": round(anchor, 4), "trigger_price": round(trigger_price, 4)}
            return last_price <= trigger_price, updates
        return False, {}

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
                should_fill, order_updates = _evaluate_order_trigger(order, last_price)
                if order_updates:
                    app.state.repo.update_order(uid, order["id"], order_updates)
                if not should_fill:
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

    def _quizzes_page_payload(
        uid: str,
        *,
        selected_module_id: str | None = None,
        result: dict[str, Any] | None = None,
        selected_answers: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        quiz_doc = {**_quiz_default_doc(), **app.state.repo.get_learning_doc(uid, "quizzes", default=_quiz_default_doc())}
        streaks = app.state.repo.get_learning_doc(
            uid,
            "streaks",
            default={"learning_streak_days": 0, "quiz_streak_days": 0, "challenge_streak_days": 0},
        )
        progress_state = _module_progress_state(uid)
        curriculum = progress_state["curriculum"]
        selected_id = quiz_bank.select_module_id(
            curriculum,
            selected_module_id,
            progress_state["completed_ids"],
        )
        catalog = quiz_bank.quiz_catalog(
            curriculum,
            quiz_doc,
            progress_state["completed_ids"],
            selected_id,
        )
        selected_quiz = next((row for row in catalog if row["id"] == selected_id), catalog[0] if catalog else {})
        history_raw = quiz_doc.get("history") if isinstance(quiz_doc.get("history"), list) else []
        history = [row for row in history_raw if isinstance(row, dict)]
        total_modules = max(1, progress_state["total_modules"])
        completed_modules = progress_state["completed_count"]
        return {
            "questions": _quiz_question_bank(curriculum, selected_id),
            "quiz_catalog": catalog,
            "selected_quiz": selected_quiz,
            "selected_module_id": selected_id,
            "module_progress": {
                "completed_modules": completed_modules,
                "total_modules": total_modules,
                "progress_pct": int(round((completed_modules / total_modules) * 100)),
            },
            "quiz_state": quiz_doc,
            "streaks": streaks,
            "quiz_history": list(reversed(history[-5:])),
            "result": result,
            "selected_answers": selected_answers or {},
        }

    def _module_progress_state(uid: str) -> dict[str, Any]:
        curriculum = app.state.learning_engine.curriculum()
        module_ids = [str(row.get("id") or "") for row in curriculum if str(row.get("id") or "").strip()]
        default_next = f"Start module 1: {curriculum[0]['title']}." if curriculum else "Complete your next concept check."
        progress_doc = app.state.repo.get_learning_doc(
            uid,
            "progress",
            default={
                "completed_modules": 0,
                "total_modules": len(module_ids) or 20,
                "completed_module_ids": [],
                "next_step": default_next,
            },
        )
        completed_raw = progress_doc.get("completed_module_ids") if isinstance(progress_doc.get("completed_module_ids"), list) else []
        completed_ids: list[str] = []
        seen: set[str] = set()
        for raw_id in completed_raw:
            module_id = str(raw_id or "").strip()
            if not module_id or module_id not in module_ids or module_id in seen:
                continue
            completed_ids.append(module_id)
            seen.add(module_id)

        if not completed_ids:
            fallback_completed = max(0, min(_i(progress_doc.get("completed_modules"), 0), len(module_ids)))
            completed_ids = module_ids[:fallback_completed]

        completed_set = set(completed_ids)
        total_modules = len(module_ids) if module_ids else max(1, _i(progress_doc.get("total_modules"), 20))
        return {
            "curriculum": curriculum,
            "module_ids": module_ids,
            "progress_doc": progress_doc,
            "completed_ids": completed_ids,
            "completed_set": completed_set,
            "completed_count": len(completed_set),
            "total_modules": total_modules,
        }

    def _next_module_step(curriculum: list[dict[str, Any]], completed_set: set[str]) -> str:
        for idx, module in enumerate(curriculum, start=1):
            module_id = str(module.get("id") or "")
            if module_id and module_id not in completed_set:
                return f"Complete module {idx}: {module.get('title') or 'Next Module'}."
        return "Great momentum. Keep reinforcing with concept checks and trade journaling."

    def _save_module_progress(uid: str, module_id: str, *, complete: bool, source: str) -> dict[str, Any] | None:
        state = _module_progress_state(uid)
        curriculum = state["curriculum"]
        module_ids = state["module_ids"]
        if module_id not in set(module_ids):
            return None

        completed_set = set(state["completed_ids"])
        if complete:
            completed_set.add(module_id)
        else:
            completed_set.discard(module_id)

        ordered_completed = [row_id for row_id in module_ids if row_id in completed_set]
        payload: dict[str, Any] = {
            "completed_module_ids": ordered_completed,
            "completed_modules": len(ordered_completed),
            "total_modules": len(module_ids) or 20,
            "next_step": _next_module_step(curriculum, completed_set),
            "last_progress_source": source,
            "updated_at": _utc_now_iso(),
        }
        if complete:
            payload["last_completed_module_id"] = module_id
            payload["last_completed_at"] = _utc_now_iso()
        return app.state.repo.set_learning_doc(uid, "progress", payload, merge=True)

    def _modules_page_payload(uid: str) -> dict[str, Any]:
        state = _module_progress_state(uid)
        curriculum = state["curriculum"]
        completed_set = state["completed_set"]
        rows: list[dict[str, Any]] = []
        for idx, module in enumerate(curriculum, start=1):
            module_id = str(module.get("id") or "")
            rows.append(
                {
                    **module,
                    "index": idx,
                    "is_completed": module_id in completed_set,
                }
            )
        total_modules = max(1, state["total_modules"])
        completed_count = state["completed_count"]
        progress_pct = int(round((completed_count / total_modules) * 100))
        next_step = _next_module_step(curriculum, completed_set)
        return {
            "modules": rows,
            "progress": {
                "completed_modules": completed_count,
                "total_modules": total_modules,
                "progress_pct": progress_pct,
                "next_step": next_step,
            },
            "progress_doc": state["progress_doc"],
        }

    @app.get("/", response_class=HTMLResponse)
    async def home(request: Request):
        uid = _auth_or_redirect(request)
        if isinstance(uid, RedirectResponse):
            return templates.TemplateResponse(request, "login.html", _context(request))

        market = app.state.repo.get_selected_market(uid)
        if market not in {"US", "INDIA"}:
            market = "US"
            app.state.repo.set_selected_market(uid, market)
        parallel_rows = _run_parallel(
            {
                "dashboard": lambda: app.state.learning_engine.dashboard(uid, market),
                "benchmark": lambda: app.state.market_data.benchmark_quote(market),
                "market_session": lambda: app.state.market_data.market_session(market),
                "news": lambda: app.state.market_data.market_news(market, limit=8),
                "health": lambda: app.state.learning_engine.health_score(uid, market),
                "weekly_summary": lambda: app.state.learning_engine.weekly_summary(uid, market),
                "mistakes": lambda: app.state.learning_engine.mistake_detection(uid, market),
                "mood": lambda: app.state.market_data.market_mood(market),
            },
            max_workers=8,
        )
        dashboard = parallel_rows.get("dashboard") or app.state.learning_engine.dashboard(uid, market)
        benchmark = parallel_rows.get("benchmark") or app.state.market_data.benchmark_quote(market)
        market_session = parallel_rows.get("market_session") or app.state.market_data.market_session(market)
        news = parallel_rows.get("news") or []
        health = parallel_rows.get("health") or app.state.learning_engine.health_score(uid, market)
        weekly_summary = parallel_rows.get("weekly_summary") or app.state.learning_engine.weekly_summary(uid, market)
        mistakes = parallel_rows.get("mistakes") or app.state.learning_engine.mistake_detection(uid, market)
        mood = parallel_rows.get("mood") or app.state.market_data.market_mood(market)
        portfolio = app.state.repo.get_portfolio(uid, market)
        positions = portfolio.get("positions", [])
        positions, top_positions, worst_positions = _dashboard_position_rows(positions)
        currency_code = str(benchmark.get("currency") or "USD")
        goal = app.state.repo.get_learning_doc(uid, "portfolio_goal", default={})
        goal_deadline = _goal_deadline_status(goal)
        coach = _coach_loading_placeholder()
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
                    "coach_loading": True,
                    "market_session": market_session,
                    "currency_code": currency_code,
                    "currency_symbol": _currency_symbol(currency_code),
                    "goal_deadline": goal_deadline,
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
        quote_ai: dict[str, Any] | None = None
        if q:
            suggestions = app.state.market_data.search_symbols(q, market, limit=8)
        if symbol:
            resolved = app.state.market_data.resolve_symbol(symbol, market)
            parallel_rows = _run_parallel(
                {
                    "quote": lambda: app.state.market_data.quote(resolved, market),
                    "news": lambda: app.state.market_data.stock_news(resolved, market, limit=8),
                    "quote_chart": lambda: app.state.market_data.quote_history(resolved, market, period="1y", interval="1d"),
                    "quote_actions": lambda: app.state.market_data.quote_corporate_actions(resolved, market, limit=8),
                    "forecast": lambda: app.state.market_data.forecast_lite(resolved, market),
                    "risk": lambda: app.state.market_data.risk_lite(resolved, market),
                    "market_mood": lambda: app.state.market_data.market_mood(market),
                },
                max_workers=7,
            )
            quote = parallel_rows.get("quote") or app.state.market_data.quote(resolved, market)
            news = parallel_rows.get("news") or []
            quote_chart = parallel_rows.get("quote_chart") or quote_chart
            quote_actions = parallel_rows.get("quote_actions") or quote_actions
            quote_ai = _quote_ai_loading_placeholder()
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
                    "quote_ai": quote_ai,
                    "quote_ai_loading": bool(symbol),
                    "suggestions": suggestions,
                },
            ),
        )

    @app.get("/api/ai/dashboard-brief")
    async def api_ai_dashboard_brief(request: Request):
        uid = _uid(request) or _preview_uid(request)
        if not uid:
            raise HTTPException(status_code=401, detail="Not authenticated")
        market = app.state.repo.get_selected_market(uid)
        parallel_rows = _run_parallel(
            {
                "dashboard": lambda: app.state.learning_engine.dashboard(uid, market),
                "news": lambda: app.state.market_data.market_news(market, limit=8),
                "health": lambda: app.state.learning_engine.health_score(uid, market),
                "weekly_summary": lambda: app.state.learning_engine.weekly_summary(uid, market),
                "mistakes": lambda: app.state.learning_engine.mistake_detection(uid, market),
                "mood": lambda: app.state.market_data.market_mood(market),
            },
            max_workers=6,
        )
        dashboard = parallel_rows.get("dashboard") or app.state.learning_engine.dashboard(uid, market)
        news = parallel_rows.get("news") or []
        health = parallel_rows.get("health") or app.state.learning_engine.health_score(uid, market)
        weekly_summary = parallel_rows.get("weekly_summary") or app.state.learning_engine.weekly_summary(uid, market)
        mistakes = parallel_rows.get("mistakes") or app.state.learning_engine.mistake_detection(uid, market)
        mood = parallel_rows.get("mood") or app.state.market_data.market_mood(market)
        portfolio = app.state.repo.get_portfolio(uid, market)
        positions = portfolio.get("positions", [])
        positions, top_positions, worst_positions = _dashboard_position_rows(positions)
        return app.state.ai_advisor.dashboard_brief(
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
                "user_context": _advisor_user_context(uid, market),
            },
        )

    @app.get("/api/ai/quote-signal")
    async def api_ai_quote_signal(request: Request):
        uid = _uid(request) or _preview_uid(request)
        if not uid:
            raise HTTPException(status_code=401, detail="Not authenticated")
        raw_symbol = str(request.query_params.get("symbol") or "").strip()
        if not raw_symbol:
            raise HTTPException(status_code=400, detail="symbol is required")
        market = app.state.repo.get_selected_market(uid)
        symbol = app.state.market_data.resolve_symbol(raw_symbol, market)
        parallel_rows = _run_parallel(
            {
                "quote": lambda: app.state.market_data.quote(symbol, market),
                "forecast": lambda: app.state.market_data.forecast_lite(symbol, market),
                "risk": lambda: app.state.market_data.risk_lite(symbol, market),
                "market_mood": lambda: app.state.market_data.market_mood(market),
                "news": lambda: app.state.market_data.stock_news(symbol, market, limit=8),
                "quote_chart": lambda: app.state.market_data.quote_history(symbol, market, period="1y", interval="1d"),
            },
            max_workers=6,
        )
        quote = parallel_rows.get("quote") or app.state.market_data.quote(symbol, market)
        forecast = parallel_rows.get("forecast") or app.state.market_data.forecast_lite(symbol, market)
        risk = parallel_rows.get("risk") or app.state.market_data.risk_lite(symbol, market)
        market_mood = parallel_rows.get("market_mood") or app.state.market_data.market_mood(market)
        news = parallel_rows.get("news") or []
        quote_chart = parallel_rows.get("quote_chart") or {"close": []}
        return app.state.ai_advisor.quote_signal(
            uid=uid,
            market=market,
            symbol=symbol,
            payload={
                "quote": quote,
                "forecast": forecast,
                "risk": risk,
                "market_mood": market_mood,
                "news": news,
                "close_prices": quote_chart.get("close") or [],
                "user_context": _advisor_user_context(uid, market),
            },
        )

    @app.get("/api/dashboard/summary")
    async def api_dashboard_summary(request: Request):
        uid = _uid(request) or _preview_uid(request)
        if not uid:
            raise HTTPException(status_code=401, detail="Not authenticated")
        market = app.state.repo.get_selected_market(uid)
        parallel_rows = _run_parallel(
            {
                "dashboard": lambda: app.state.learning_engine.dashboard(uid, market),
                "benchmark": lambda: app.state.market_data.benchmark_quote(market),
                "market_session": lambda: app.state.market_data.market_session(market),
                "news": lambda: app.state.market_data.market_news(market, limit=8),
            },
            max_workers=4,
        )
        dashboard = parallel_rows.get("dashboard") or app.state.learning_engine.dashboard(uid, market)
        benchmark = parallel_rows.get("benchmark") or app.state.market_data.benchmark_quote(market)
        market_session = parallel_rows.get("market_session") or app.state.market_data.market_session(market)
        news = parallel_rows.get("news") or []
        portfolio = app.state.repo.get_portfolio(uid, market)
        positions = portfolio.get("positions", [])
        positions, top_positions, worst_positions = _dashboard_position_rows(positions)
        currency_code = str(benchmark.get("currency") or "USD")
        goal = app.state.repo.get_learning_doc(uid, "portfolio_goal", default={})
        goal_deadline = _goal_deadline_status(goal)
        return {
            "market": market,
            "dashboard": dashboard,
            "benchmark": benchmark,
            "market_session": market_session,
            "news": news,
            "portfolio": portfolio,
            "positions": positions,
            "top_positions": top_positions,
            "worst_positions": worst_positions,
            "currency_code": currency_code,
            "currency_symbol": _currency_symbol(currency_code),
            "goal_deadline": goal_deadline,
        }

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
        stop_loss_price: float | None = Form(None),
        trailing_stop_percent: float | None = Form(None),
        trailing_stop_amount: float | None = Form(None),
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
            trade_result = app.state.repo.apply_trade(
                uid=uid,
                market=market,
                side="buy",
                symbol=resolved,
                quantity=quantity,
                price=_f(quote.get("price")),
                order_type="market",
                notes=notes,
            )
            if stop_loss_price is not None and _f(stop_loss_price) > 0:
                app.state.repo.create_order(
                    uid=uid,
                    market=market,
                    side="sell",
                    symbol=resolved,
                    quantity=quantity,
                    order_type="stop_loss",
                    trigger_price=_f(stop_loss_price),
                    notes=f"Auto stop-loss for trade {trade_result['trade']['id']}",
                )
            has_trailing_percent = trailing_stop_percent is not None and _f(trailing_stop_percent) > 0
            has_trailing_amount = trailing_stop_amount is not None and _f(trailing_stop_amount) > 0
            if has_trailing_percent and has_trailing_amount:
                raise ValueError("Use either trailing stop percent or trailing stop amount, not both")
            if has_trailing_percent or has_trailing_amount:
                app.state.repo.create_order(
                    uid=uid,
                    market=market,
                    side="sell",
                    symbol=resolved,
                    quantity=quantity,
                    order_type="trailing_stop",
                    trail_percent=_f(trailing_stop_percent) if has_trailing_percent else None,
                    trail_amount=_f(trailing_stop_amount) if has_trailing_amount else None,
                    notes=f"Auto trailing stop for trade {trade_result['trade']['id']}",
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
        trail_percent: float | None = Form(None),
        trail_amount: float | None = Form(None),
        notes: str = Form(""),
    ):
        uid = _auth_or_redirect(request)
        if isinstance(uid, RedirectResponse):
            return uid
        try:
            market = app.state.repo.get_selected_market(uid)
            resolved = app.state.market_data.resolve_symbol(symbol, market)
            normalized_type = str(order_type or "limit").lower().strip()
            if normalized_type == "market":
                trigger_price = None
                trail_percent = None
                trail_amount = None
            app.state.repo.create_order(
                uid=uid,
                market=market,
                side=side,
                symbol=resolved,
                quantity=quantity,
                order_type=normalized_type,
                trigger_price=trigger_price,
                trail_percent=trail_percent,
                trail_amount=trail_amount,
                notes=notes,
            )
            return _redirect("/orders", message=f"{normalized_type.replace('_', ' ').title()} order placed for {resolved}.")
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
        user_context = _advisor_user_context(uid, market)
        explanation = app.state.ai_advisor.portfolio_explainer(
            uid=uid,
            market=market,
            payload={
                "plain_english": base_explanation.get("plain_english"),
                "portfolio": portfolio,
                "health": health,
                "move_why": move_why,
                "user_context": user_context,
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
            default={"target_value": 250000.0, "target_return_pct": 25.0, "target_deadline": ""},
        )
        goal_deadline = _goal_deadline_status(goal)
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
                    "goal_deadline": goal_deadline,
                },
            ),
        )

    @app.post("/portfolio-goals")
    async def portfolio_goals_submit(
        request: Request,
        target_value: float = Form(...),
        target_return_pct: float = Form(...),
        target_deadline: str = Form(""),
    ):
        uid = _auth_or_redirect(request)
        if isinstance(uid, RedirectResponse):
            return uid
        parsed_deadline = _parse_goal_deadline(target_deadline)
        if str(target_deadline or "").strip() and not parsed_deadline:
            return _redirect("/portfolio-goals", error="Please choose a valid goal deadline.")
        app.state.repo.set_learning_doc(
            uid,
            "portfolio_goal",
            {
                "target_value": target_value,
                "target_return_pct": target_return_pct,
                "target_deadline": parsed_deadline.date().isoformat() if parsed_deadline else None,
            },
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
            payload={**summary, "user_context": _advisor_user_context(uid, market)},
        )
        return templates.TemplateResponse(
            request,
            "weekly_summary.html",
            _context(request, {"summary": summary, "summary_tip": summary_tip}),
        )

    @app.get("/learning-progress", response_class=HTMLResponse)
    async def learning_progress_page(request: Request):
        uid = _auth_or_redirect(request)
        if isinstance(uid, RedirectResponse):
            return uid
        market = app.state.repo.get_selected_market(uid)
        dashboard = app.state.learning_engine.dashboard(uid, market)
        health = app.state.learning_engine.health_score(uid, market)
        weekly = app.state.learning_engine.weekly_summary(uid, market)
        mistakes = app.state.learning_engine.mistake_detection(uid, market)
        curriculum = app.state.learning_engine.curriculum()
        progress_doc = app.state.repo.get_learning_doc(
            uid,
            "progress",
            default={
                "completed_modules": 0,
                "total_modules": len(curriculum) or 20,
                "completed_module_ids": [],
                "next_step": dashboard.get("next_step", ""),
            },
        )
        quizzes = app.state.repo.get_learning_doc(uid, "quizzes", default={"completed": 0, "streak": 0})
        streaks = app.state.repo.get_learning_doc(
            uid,
            "streaks",
            default={"learning_streak_days": 0, "quiz_streak_days": 0, "challenge_streak_days": 0},
        )
        components = health.get("components") if isinstance(health.get("components"), dict) else {}
        actions: list[str] = []
        progress_pct = _f(dashboard.get("learning_progress_pct"), 0.0)
        if progress_pct < 30:
            actions.append("Complete at least one curriculum module this week and finish its concept check.")
        if _f(components.get("discipline"), 0.0) < 70:
            actions.append("Trade less frequently and write a one-line thesis before every paper trade.")
        if _f(components.get("diversification"), 0.0) < 70:
            actions.append("Reduce concentration risk by limiting single-position size and adding sector diversity.")
        detected = [str(item).strip() for item in mistakes.get("mistakes", []) if str(item).strip()]
        if detected and "no major behavioral red flags detected." not in detected[0].lower():
            actions.append(f"Fix this first: {detected[0]}")
        next_concept = str(weekly.get("next_concept") or "").strip()
        if next_concept:
            actions.append(f"Study next concept: {next_concept}.")
        if not actions:
            actions = [
                "Keep a consistent daily review habit and document one lesson from each trade.",
                "Maintain position sizing discipline and protect downside with stop-loss rules.",
                "Use weekly summary insights to set one concrete goal for the next week.",
            ]
        return templates.TemplateResponse(
            request,
            "learning_progress.html",
            _context(
                request,
                {
                    "dashboard": dashboard,
                    "health": health,
                    "weekly_summary": weekly,
                    "mistakes": mistakes,
                    "curriculum": curriculum,
                    "progress_doc": progress_doc,
                    "quizzes": quizzes,
                    "streaks": streaks,
                    "learning_actions": actions[:6],
                },
            ),
        )

    @app.get("/modules", response_class=HTMLResponse)
    async def modules_page(request: Request):
        uid = _auth_or_redirect(request)
        if isinstance(uid, RedirectResponse):
            return uid
        return templates.TemplateResponse(
            request,
            "modules.html",
            _context(request, _modules_page_payload(uid)),
        )

    @app.post("/modules/complete")
    async def modules_complete(request: Request):
        uid = _auth_or_redirect(request)
        if isinstance(uid, RedirectResponse):
            return uid

        form = await request.form()
        module_id = str(form.get("module_id") or "").strip()
        action = str(form.get("action") or "complete").strip().lower()

        state = _module_progress_state(uid)
        if module_id not in set(state["module_ids"]):
            return _redirect("/modules", error="Module not found.")

        if action == "undo":
            _save_module_progress(uid, module_id, complete=False, source="manual")
            action_message = "Module marked as not completed."
        else:
            _save_module_progress(uid, module_id, complete=True, source="manual")
            action_message = "Module marked as completed."
        return _redirect("/modules", message=action_message)

    @app.get("/quizzes", response_class=HTMLResponse)
    async def quizzes_page(request: Request):
        uid = _auth_or_redirect(request)
        if isinstance(uid, RedirectResponse):
            return uid
        selected_module_id = str(request.query_params.get("module_id") or "").strip()
        return templates.TemplateResponse(
            request,
            "quizzes.html",
            _context(request, _quizzes_page_payload(uid, selected_module_id=selected_module_id)),
        )

    @app.post("/quizzes/submit", response_class=HTMLResponse)
    async def quizzes_submit(request: Request):
        uid = _auth_or_redirect(request)
        if isinstance(uid, RedirectResponse):
            return uid

        form = await request.form()
        requested_module_id = str(form.get("module_id") or "").strip()
        progress_state = _module_progress_state(uid)
        curriculum = progress_state["curriculum"]
        selected_module_id = quiz_bank.select_module_id(
            curriculum,
            requested_module_id,
            progress_state["completed_ids"],
        )
        if not selected_module_id:
            return _redirect("/quizzes", error="No quiz module is available.")

        questions = _quiz_question_bank(curriculum, selected_module_id)
        selected_module = next(
            (row for row in curriculum if str(row.get("id") or "") == selected_module_id),
            {},
        )
        selected_module_title = str(selected_module.get("title") or "Module Quiz")
        selected_answers: dict[str, str] = {}
        for question in questions:
            qid = str(question.get("id") or "")
            selected_answers[qid] = str(form.get(f"answer_{qid}", "")).strip()

        result = _quiz_report(questions, selected_answers)
        result["module_id"] = selected_module_id
        result["module_title"] = selected_module_title
        result["progress_updated"] = False
        now = datetime.now(timezone.utc)
        today_iso = now.date().isoformat()
        yesterday_iso = (now.date() - timedelta(days=1)).isoformat()

        current = {**_quiz_default_doc(), **app.state.repo.get_learning_doc(uid, "quizzes", default=_quiz_default_doc())}
        previous_streak = _i(current.get("streak"), 0)
        previous_completed = _i(current.get("completed"), 0)
        last_completed_on = str(current.get("last_completed_on") or "").strip()

        if last_completed_on == today_iso:
            next_streak = max(1, previous_streak)
        elif last_completed_on == yesterday_iso:
            next_streak = max(1, previous_streak + 1)
        else:
            next_streak = 1

        history_raw = current.get("history") if isinstance(current.get("history"), list) else []
        history = [row for row in history_raw if isinstance(row, dict)][-19:]
        history.append(
            {
                "submitted_at": now.isoformat(),
                "module_id": selected_module_id,
                "module_title": selected_module_title,
                "score_pct": result["score_pct"],
                "correct": result["correct"],
                "total": result["total"],
                "passed": result["passed"],
            }
        )
        milestones = current.get("milestones")
        if not isinstance(milestones, list) or "Finish 20 trade-based questions" in milestones:
            milestones = _quiz_default_doc()["milestones"]

        module_scores = current.get("module_scores") if isinstance(current.get("module_scores"), dict) else {}
        existing_score = module_scores.get(selected_module_id) if isinstance(module_scores.get(selected_module_id), dict) else {}
        best_score = max(_i(existing_score.get("best_score_pct"), 0), _i(result["score_pct"], 0))
        module_scores[selected_module_id] = {
            "module_id": selected_module_id,
            "module_title": selected_module_title,
            "attempts": _i(existing_score.get("attempts"), 0) + 1,
            "best_score_pct": best_score,
            "last_score_pct": result["score_pct"],
            "last_correct": result["correct"],
            "last_total": result["total"],
            "passed": bool(existing_score.get("passed")) or bool(result["passed"]),
            "last_submitted_at": now.isoformat(),
        }

        completed_quiz_raw = current.get("completed_quiz_module_ids")
        completed_quiz_ids = [
            str(module_id).strip()
            for module_id in (completed_quiz_raw if isinstance(completed_quiz_raw, list) else [])
            if str(module_id).strip()
        ]
        if result["passed"] and selected_module_id not in completed_quiz_ids:
            completed_quiz_ids.append(selected_module_id)

        if result["passed"]:
            progress_doc = _save_module_progress(uid, selected_module_id, complete=True, source="quiz")
            result["progress_updated"] = progress_doc is not None

        app.state.repo.set_learning_doc(
            uid,
            "quizzes",
            {
                "completed": previous_completed + 1,
                "completed_quiz_module_ids": completed_quiz_ids,
                "passed_modules": len(completed_quiz_ids),
                "total_module_quizzes": len(curriculum) or 20,
                "module_scores": module_scores,
                "streak": next_streak,
                "last_completed_on": today_iso,
                "last_submitted_at": now.isoformat(),
                "last_module_id": selected_module_id,
                "last_module_title": selected_module_title,
                "last_passed": result["passed"],
                "last_score_pct": result["score_pct"],
                "last_correct": result["correct"],
                "last_total": result["total"],
                "history": history,
                "milestones": milestones,
            },
            merge=True,
        )
        app.state.repo.set_learning_doc(uid, "streaks", {"quiz_streak_days": next_streak}, merge=True)

        return templates.TemplateResponse(
            request,
            "quizzes.html",
            _context(
                request,
                _quizzes_page_payload(
                    uid,
                    selected_module_id=selected_module_id,
                    result=result,
                    selected_answers=selected_answers,
                ),
            ),
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
        risk_tip = app.state.ai_advisor.tool_tip(
            uid=uid,
            market=market,
            topic="risk",
            payload={**risk, "symbol": symbol, "user_context": _advisor_user_context(uid, market)},
        )
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
        user_context = _advisor_user_context(uid, market)
        portfolio_explainer = app.state.ai_advisor.portfolio_explainer(
            uid=uid,
            market=market,
            payload={"portfolio": portfolio, "focus_symbol": symbol, "user_context": user_context},
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
                "user_context": user_context,
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
        context_payload = build_ai_chat_context(
            uid=uid,
            market=market,
            repo=app.state.repo,
            learning_engine=app.state.learning_engine,
            market_data=app.state.market_data,
        )
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
        mood_tip = app.state.ai_advisor.tool_tip(
            uid=uid,
            market=market,
            topic="market-mood",
            payload={**mood, "user_context": _advisor_user_context(uid, market)},
        )
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
                "user_context": _advisor_user_context(uid, market),
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
