from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request

from ..dependencies import current_uid, get_repository
from ..schemas.learning import ChecklistRequest


router = APIRouter(prefix="/api/learning", tags=["learning"])


def _f(value, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _chat_doc_id(market: str) -> str:
    return f"ai_chat_{str(market).lower()}"


def _chat_rows(raw_messages) -> list[dict]:
    if not isinstance(raw_messages, list):
        return []
    rows: list[dict] = []
    for row in raw_messages[-30:]:
        if not isinstance(row, dict):
            continue
        role = str(row.get("role") or "")
        content = str(row.get("content") or "").strip()
        if role not in {"user", "assistant"} or not content:
            continue
        rows.append(
            {
                "role": role,
                "content": content[:4000],
                "created_at": str(row.get("created_at") or ""),
            }
        )
    return rows


@router.get("/dashboard")
def learning_dashboard(request: Request, uid: str = Depends(current_uid), repo=Depends(get_repository)):
    market = repo.get_selected_market(uid)
    return request.app.state.learning_engine.dashboard(uid, market)


@router.get("/curriculum")
def learning_curriculum(request: Request):
    return {"curriculum": request.app.state.learning_engine.curriculum()}


@router.post("/checklist")
def learning_checklist(payload: ChecklistRequest, request: Request, uid: str = Depends(current_uid)):
    return request.app.state.learning_engine.save_checklist(uid, payload.model_dump())


@router.get("/weekly-summary")
def weekly_summary(request: Request, uid: str = Depends(current_uid), repo=Depends(get_repository)):
    market = repo.get_selected_market(uid)
    summary = request.app.state.learning_engine.weekly_summary(uid, market)
    summary["ai_tip"] = request.app.state.ai_advisor.tool_tip(
        uid=uid,
        market=market,
        topic="weekly-summary",
        payload=summary,
    )
    return summary


@router.get("/health-score")
def health_score(request: Request, uid: str = Depends(current_uid), repo=Depends(get_repository)):
    market = repo.get_selected_market(uid)
    return request.app.state.learning_engine.health_score(uid, market)


@router.get("/explain-portfolio")
def explain_portfolio(request: Request, uid: str = Depends(current_uid), repo=Depends(get_repository)):
    market = repo.get_selected_market(uid)
    base = request.app.state.learning_engine.explain_portfolio(uid, market)
    portfolio = repo.get_portfolio(uid, market)
    return request.app.state.ai_advisor.portfolio_explainer(
        uid=uid,
        market=market,
        payload={"plain_english": base.get("plain_english"), "portfolio": portfolio},
    )


@router.get("/portfolio-move-why")
def portfolio_move_why(request: Request, uid: str = Depends(current_uid), repo=Depends(get_repository)):
    market = repo.get_selected_market(uid)
    move = request.app.state.learning_engine.portfolio_move_why(uid, market)
    move["ai_tip"] = request.app.state.ai_advisor.tool_tip(
        uid=uid,
        market=market,
        topic="portfolio-move",
        payload=move,
    )
    return move


@router.get("/mistakes")
def learning_mistakes(request: Request, uid: str = Depends(current_uid), repo=Depends(get_repository)):
    market = repo.get_selected_market(uid)
    return request.app.state.learning_engine.mistake_detection(uid, market)


@router.get("/coach")
def learning_ai_coach(request: Request, uid: str = Depends(current_uid), repo=Depends(get_repository)):
    market = repo.get_selected_market(uid)
    learning_engine = request.app.state.learning_engine
    market_data = request.app.state.market_data

    dashboard = learning_engine.dashboard(uid, market)
    portfolio = repo.get_portfolio(uid, market)
    health = learning_engine.health_score(uid, market)
    mistakes = learning_engine.mistake_detection(uid, market)
    weekly_summary = learning_engine.weekly_summary(uid, market)
    mood = market_data.market_mood(market)
    news = market_data.market_news(market, limit=8)

    positions = portfolio.get("positions", [])
    for pos in positions:
        avg = _f(pos.get("avg_price"))
        last = _f(pos.get("last_price"))
        pos["change_pct"] = round(((last - avg) / avg * 100), 2) if avg else 0.0

    top_positions = sorted(positions, key=lambda row: _f(row.get("change_pct")), reverse=True)[:4]
    worst_positions = sorted(positions, key=lambda row: _f(row.get("change_pct")))[:4]

    return request.app.state.ai_advisor.dashboard_brief(
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


@router.get("/chat/history")
def learning_chat_history(uid: str = Depends(current_uid), repo=Depends(get_repository)):
    market = repo.get_selected_market(uid)
    doc = repo.get_learning_doc(uid, _chat_doc_id(market), default={"messages": []})
    return {"market": market, "messages": _chat_rows(doc.get("messages"))}


@router.post("/chat")
def learning_chat_post(payload: dict, request: Request, uid: str = Depends(current_uid), repo=Depends(get_repository)):
    market = repo.get_selected_market(uid)
    message = str(payload.get("message") or "").strip()
    if not message:
        raise HTTPException(status_code=400, detail="message is required")

    doc = repo.get_learning_doc(uid, _chat_doc_id(market), default={"messages": []})
    history = _chat_rows(doc.get("messages"))
    context_payload = {
        "market": market,
        "dashboard": request.app.state.learning_engine.dashboard(uid, market),
        "portfolio": repo.get_portfolio(uid, market),
        "health": request.app.state.learning_engine.health_score(uid, market),
        "mistakes": request.app.state.learning_engine.mistake_detection(uid, market),
        "weekly_summary": request.app.state.learning_engine.weekly_summary(uid, market),
        "market_mood": request.app.state.market_data.market_mood(market),
        "news": request.app.state.market_data.market_news(market, limit=5),
    }
    reply = request.app.state.ai_advisor.chat_reply(
        uid=uid,
        market=market,
        message=message,
        history=history,
        context=context_payload,
    )
    now = datetime.now(timezone.utc).isoformat()
    messages = history + [
        {"role": "user", "content": message, "created_at": now},
        {"role": "assistant", "content": str(reply.get("reply") or "").strip(), "created_at": now},
    ]
    repo.set_learning_doc(uid, _chat_doc_id(market), {"messages": messages[-30:]}, merge=False)
    return {"market": market, "reply": reply, "messages": messages[-30:]}


@router.delete("/chat/history")
def learning_chat_clear(uid: str = Depends(current_uid), repo=Depends(get_repository)):
    market = repo.get_selected_market(uid)
    repo.set_learning_doc(uid, _chat_doc_id(market), {"messages": []}, merge=False)
    return {"market": market, "status": "cleared"}


@router.get("/goals")
def get_goals(uid: str = Depends(current_uid), repo=Depends(get_repository)):
    return repo.get_learning_doc(
        uid,
        "goals",
        default={
            "learning_goals": [],
            "habit_goals": [],
            "diversification_goals": [],
            "paper_trading_milestones": ["Complete 5 simulated trades"],
        },
    )


@router.put("/goals")
def update_goals(payload: dict, uid: str = Depends(current_uid), repo=Depends(get_repository)):
    return repo.set_learning_doc(uid, "goals", payload, merge=True)


@router.get("/center")
def learning_center():
    topics = [
        "stocks",
        "bonds",
        "ETFs",
        "mutual funds",
        "compounding",
        "volatility",
        "drawdown",
        "diversification",
        "order types",
        "market cycles",
        "saving vs investing",
        "inflation",
        "emergency fund basics",
        "asset classes",
        "risk capacity vs risk tolerance",
    ]
    return {"topics": topics}


@router.get("/quizzes")
def quizzes(uid: str = Depends(current_uid), repo=Depends(get_repository)):
    return repo.get_learning_doc(
        uid,
        "quizzes",
        default={
            "streak": 0,
            "completed": 0,
            "milestones": ["Finish first concept check", "Finish 5 quizzes", "Finish 20 trade-based questions"],
        },
    )


@router.get("/challenges")
def challenges(uid: str = Depends(current_uid), repo=Depends(get_repository)):
    return repo.get_learning_doc(
        uid,
        "challenges",
        default={
            "weekly": ["Complete 2 concept checks", "Review 1 losing trade", "Practice 1 scenario simulation"],
            "diversification": ["Hold at least 3 sectors in paper portfolio"],
            "consistency": ["Log in 5 days this week", "Write thesis before every trade"],
        },
    )


@router.get("/streaks")
def streaks(uid: str = Depends(current_uid), repo=Depends(get_repository)):
    return repo.get_learning_doc(
        uid,
        "streaks",
        default={"learning_streak_days": 0, "quiz_streak_days": 0, "challenge_streak_days": 0},
    )
