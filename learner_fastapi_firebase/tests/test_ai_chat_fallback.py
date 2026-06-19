from __future__ import annotations

from types import SimpleNamespace

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


def test_chat_fallback_greeting_does_not_dump_portfolio():
    svc = _service()
    out = svc.chat_reply(
        uid="u1",
        market="US",
        message="hello",
        history=[],
        context=_context_with_positions(),
    )
    reply = out["reply"]
    assert "What would you like to work on" in reply
    assert "account is worth" not in reply
    assert "Entry" not in reply


def test_chat_fallback_improve_named_position_is_specific():
    svc = _service()
    context = _context_with_positions()
    context["portfolio"]["positions"].append(
        {"symbol": "DRAM", "avg_price": 10.0, "last_price": 11.0, "market_value": 2200.0}
    )
    context["portfolio"]["market_value"] = 8000.0
    context["portfolio"]["total_value"] = 12200.0

    out = svc.chat_reply(
        uid="u1",
        market="US",
        message="How can I improve my DRAM position?",
        history=[],
        context=context,
    )
    reply = out["reply"]
    assert "DRAM is about 18.0%" in reply
    assert "10.0% above cost" in reply
    assert "next decision should come from your thesis" in reply
    assert "maximum portfolio weight" in reply


def test_forecast_fallback_reads_nested_forecast_and_position():
    svc = _service()
    out = svc.forecast_explainer(
        uid="u1",
        market="US",
        symbol="DRAM",
        payload={
            "forecast": {"direction": "Up", "confidence": 0.72, "simple_reason": "Short trend is improving."},
            "portfolio": {
                "total_value": 10000.0,
                "positions": [
                    {"symbol": "DRAM", "avg_price": 10.0, "last_price": 11.0, "market_value": 3000.0}
                ],
            },
            "market_mood": {"classification": "Neutral"},
            "headlines": [],
        },
    )
    assert "up with 72% confidence" in out["quick_take"]
    assert "30.0% of the account" in out["portfolio_link"]
    assert "+10.0%" in out["portfolio_link"]
    assert "football" not in out["explain_like_15"].lower()


def test_portfolio_fallback_uses_real_allocations():
    svc = _service()
    out = svc.portfolio_explainer(
        uid="u1",
        market="US",
        payload={"portfolio": _context_with_positions()["portfolio"], "focus_symbol": "AAPL"},
    )
    assert "58.0% invested" in out["plain_english"]
    assert "AAPL is the largest position at 33.0%" in out["plain_english"]
    assert "AAPL is 33.0%" in out["analogy"]
    assert "safety helmet" not in out["analogy"]


def test_nemotron_request_disables_long_hidden_thinking_for_chat_latency():
    svc = _service()
    captured = {}

    class Completions:
        def create(self, **kwargs):  # type: ignore[no-untyped-def]
            captured.update(kwargs)
            delta = SimpleNamespace(content="Natural answer")
            return [SimpleNamespace(choices=[SimpleNamespace(delta=delta)])]

    svc.model = "nvidia/nemotron-3-ultra-550b-a55b"
    svc._client = SimpleNamespace(chat=SimpleNamespace(completions=Completions()))
    reply = svc._stream_chat([{"role": "user", "content": "hello"}], max_tokens=200)

    assert reply == "Natural answer"
    assert captured["stream"] is True
    assert captured["extra_body"] == {"chat_template_kwargs": {"enable_thinking": False}}


def test_deepseek_v4_request_uses_documented_non_streaming_mode():
    svc = _service()
    captured = {}

    class Completions:
        def create(self, **kwargs):  # type: ignore[no-untyped-def]
            captured.update(kwargs)
            message = SimpleNamespace(content="DeepSeek answer")
            return SimpleNamespace(choices=[SimpleNamespace(message=message)])

    svc.model = "deepseek-ai/deepseek-v4-pro"
    svc._client = SimpleNamespace(chat=SimpleNamespace(completions=Completions()))
    reply = svc._stream_chat([{"role": "user", "content": "hello"}], max_tokens=200)

    assert reply == "DeepSeek answer"
    assert captured["stream"] is False
    assert captured["extra_body"] == {"chat_template_kwargs": {"thinking": False}}
