from __future__ import annotations

from learner_fastapi_firebase.app.services.ai_advisor import AIAdvisorService


def _service() -> AIAdvisorService:
    return AIAdvisorService(
        api_key="",
        base_url="https://example.com/v1",
        model="test-model",
    )


def _context_with_positions() -> dict:
    return {
        "portfolio": {
            "cash": 4200.0,
            "market_value": 5800.0,
            "total_value": 10000.0,
            "positions": [
                {"symbol": "AAPL", "avg_price": 100.0, "last_price": 110.0, "market_value": 3300.0},
                {"symbol": "TSLA", "avg_price": 200.0, "last_price": 180.0, "market_value": 2500.0},
            ],
        },
        "market_mood": {"classification": "Neutral", "score": 55},
        "health": {"score": 62},
        "mistakes": {"mistakes": ["Overtrading: many trades in a short window."]},
    }


def test_chat_fallback_explain_like_15_is_contextual():
    svc = _service()
    out = svc.chat_reply(
        uid="u1",
        market="US",
        message="Explain my portfolio like I am 15.",
        history=[],
        context=_context_with_positions(),
    )
    reply = out["reply"]
    assert "For now, start with this" not in reply
    assert "football team" in reply
    assert "$10,000.00" in reply
    assert "AAPL" in reply


def test_chat_fallback_weakest_position_has_entry_stop_exit():
    svc = _service()
    out = svc.chat_reply(
        uid="u1",
        market="US",
        message="Give me a simple plan for my weakest position.",
        history=[],
        context=_context_with_positions(),
    )
    reply = out["reply"]
    assert "Weakest current position: TSLA" in reply
    assert "Entry:" in reply
    assert "Stop:" in reply
    assert "Exit:" in reply
