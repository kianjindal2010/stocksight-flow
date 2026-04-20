from __future__ import annotations


def test_learning_chat_uses_full_context(client, auth_headers):
    captured: dict = {}

    def fake_chat_reply(uid, market, message, history=None, context=None):  # type: ignore[no-untyped-def]
        captured["uid"] = uid
        captured["market"] = market
        captured["message"] = message
        captured["history"] = history or []
        captured["context"] = context or {}
        return {"reply": "ok", "source": "test", "generated_at": "now", "model": "test"}

    client.app.state.ai_advisor.chat_reply = fake_chat_reply  # type: ignore[assignment]

    response = client.post("/api/learning/chat", headers=auth_headers, json={"message": "What should I do next?"})
    assert response.status_code == 200

    context = captured["context"]
    assert context["access_mode"] == "full"
    assert "user_profile" in context
    assert "user_preferences" in context
    assert "portfolio" in context
    assert "portfolio_performance" in context
    assert "trades" in context
    assert "orders" in context
    assert "watchlists" in context
    assert "alerts" in context
    assert "notifications" in context
    assert "learning" in context
    assert "market_intel" in context
    assert "holdings_intel" in context
    assert "watchlist_intel" in context
    assert "data_scope" in context


def test_web_ai_chat_uses_full_context(client, auth_headers):
    captured: dict = {}

    def fake_chat_reply(uid, market, message, history=None, context=None):  # type: ignore[no-untyped-def]
        captured["context"] = context or {}
        return {"reply": "ok", "source": "test", "generated_at": "now", "model": "test"}

    client.app.state.ai_advisor.chat_reply = fake_chat_reply  # type: ignore[assignment]

    response = client.post("/ai-chat", headers=auth_headers, data={"message": "Explain my portfolio"})
    assert response.status_code == 200
    assert captured["context"]["access_mode"] == "full"
    assert "market_intel" in captured["context"]
