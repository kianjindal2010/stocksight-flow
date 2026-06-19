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


def test_web_ai_chat_supports_async_response_and_saves_model_metadata(client, auth_headers):
    def fake_chat_reply(uid, market, message, history=None, context=None):  # type: ignore[no-untyped-def]
        return {
            "reply": "A more natural answer",
            "source": "nvidia_llm",
            "generated_at": "now",
            "model": "nvidia/nemotron-3-ultra-550b-a55b",
        }

    client.app.state.ai_advisor.chat_reply = fake_chat_reply  # type: ignore[assignment]
    headers = {**auth_headers, "X-Requested-With": "stocksight-chat"}
    response = client.post("/ai-chat", headers=headers, data={"message": "Help me think this through"})

    assert response.status_code == 200
    message = response.json()["message"]
    assert message["content"] == "A more natural answer"
    assert message["source"] == "nvidia_llm"
    assert message["model"] == "nvidia/nemotron-3-ultra-550b-a55b"

    history = client.get("/api/learning/chat/history", headers=auth_headers).json()["messages"]
    assert history[-1]["source"] == "nvidia_llm"
    assert history[-1]["model"] == "nvidia/nemotron-3-ultra-550b-a55b"


def test_dashboard_ai_receives_user_tradebook_context(client, auth_headers):
    captured: dict = {}

    def fake_dashboard_brief(uid, market, payload):  # type: ignore[no-untyped-def]
        captured["payload"] = payload
        return {"headline": "ok", "summary": "ok", "risk_level": "Medium", "actions": [], "news_watch": []}

    client.app.state.ai_advisor.dashboard_brief = fake_dashboard_brief  # type: ignore[assignment]

    response = client.get("/api/ai/dashboard-brief", headers=auth_headers)
    assert response.status_code == 200

    context = captured["payload"]["user_context"]
    assert context["access_mode"] == "advisor_compact"
    assert context["data_origin"] == "firestore_repository"
    assert "tradebook" in context
    assert "recent_trades" in context["tradebook"]
    assert "journal_entries" in context["tradebook"]


def test_quote_signal_receives_user_tradebook_context(client, auth_headers):
    captured: dict = {}

    def fake_quote_signal(uid, market, symbol, payload):  # type: ignore[no-untyped-def]
        captured["payload"] = payload
        return {"action": "Hold", "buy_score": 50, "confidence": 50, "news_bias": "Neutral", "factors": []}

    client.app.state.ai_advisor.quote_signal = fake_quote_signal  # type: ignore[assignment]

    response = client.get("/api/ai/quote-signal?symbol=AAPL", headers=auth_headers)
    assert response.status_code == 200

    context = captured["payload"]["user_context"]
    assert context["portfolio"]["market"] == "US"
    assert "portfolio_performance" in context
    assert "tradebook" in context
    assert "stats" in context["tradebook"]
