from __future__ import annotations

import os

import pytest
from fastapi.testclient import TestClient


os.environ["FIREBASE_USE_MEMORY"] = "true"


@pytest.fixture()
def app(monkeypatch):
    from learner_fastapi_firebase.app.main import create_app
    import learner_fastapi_firebase.app.main as main_mod

    monkeypatch.setattr(
        main_mod,
        "verify_id_token",
        lambda token: {"uid": "test-user", "email": "test@example.com", "name": "Test User"},
    )
    app = create_app()

    market_data = app.state.market_data
    monkeypatch.setattr(
        market_data,
        "search_symbols",
        lambda query, market, limit=12: [{"symbol": "AAPL", "name": "Apple Inc."}],
    )
    monkeypatch.setattr(
        market_data,
        "resolve_symbol",
        lambda query, market: "AAPL",
    )
    monkeypatch.setattr(
        market_data,
        "quote",
        lambda symbol, market: {
            "symbol": "AAPL",
            "name": "Apple Inc.",
            "price": 100.0,
            "change_pct": 1.0,
            "currency": "USD",
            "summary": "Sample",
            "sector": "Technology",
            "market_cap": 1_000_000,
            "volume": 1_000,
        },
    )
    monkeypatch.setattr(
        market_data,
        "benchmark_quote",
        lambda market: {"label": "S&P 500", "price": 5000.0, "change_pct": 0.5},
    )
    monkeypatch.setattr(market_data, "market_news", lambda market, limit=12: [])
    monkeypatch.setattr(market_data, "stock_news", lambda symbol, market, limit=10: [])
    monkeypatch.setattr(market_data, "sector_news", lambda sector, limit=10: [])
    monkeypatch.setattr(market_data, "macro_news", lambda limit=10: [])
    monkeypatch.setattr(market_data, "event_calendar_links", lambda market: [])
    monkeypatch.setattr(market_data, "screener", lambda market, preset="top_gainers", limit=25: [])
    monkeypatch.setattr(market_data, "market_mood", lambda market: {"score": 55.0, "classification": "Neutral"})
    monkeypatch.setattr(market_data, "risk_lite", lambda symbol, market: {"risk_score": 50})
    monkeypatch.setattr(market_data, "forecast_lite", lambda symbol, market: {"direction": "Up", "confidence": 0.6})

    ai = app.state.ai_advisor
    monkeypatch.setattr(
        ai,
        "dashboard_brief",
        lambda uid, market, payload: {
            "headline": "AI Coach",
            "summary": "Test coach summary",
            "risk_level": "Medium",
            "actions": ["Step 1", "Step 2", "Step 3"],
            "news_watch": ["Item 1", "Item 2"],
            "disclaimer": "Test disclaimer",
        },
    )
    monkeypatch.setattr(
        ai,
        "quote_signal",
        lambda uid, market, symbol, payload: {
            "action": "Hold",
            "buy_score": 50,
            "confidence": 50,
            "news_bias": "Neutral",
            "summary": "Test quote signal",
            "factors": ["Factor 1", "Factor 2"],
            "disclaimer": "Test disclaimer",
        },
    )
    monkeypatch.setattr(
        ai,
        "tool_tip",
        lambda uid, market, topic, payload: {
            "title": "Tip",
            "explain_like_15": "Test tip",
            "steps": ["A", "B", "C"],
            "context": "Test context",
        },
    )
    monkeypatch.setattr(
        ai,
        "portfolio_explainer",
        lambda uid, market, payload: {
            "plain_english": "Test plain english",
            "analogy": "Test analogy",
            "why_it_moved": "Test move",
            "next_steps": ["A", "B"],
        },
    )
    monkeypatch.setattr(
        ai,
        "forecast_explainer",
        lambda uid, market, symbol, payload: {
            "quick_take": "Test",
            "explain_like_15": "Test",
            "portfolio_link": "Test",
            "next_steps": ["A", "B"],
        },
    )
    monkeypatch.setattr(
        ai,
        "chat_reply",
        lambda uid, market, message, history=None, context=None: {"reply": "Test reply"},
    )
    return app


@pytest.fixture()
def client(app):
    return TestClient(app)


@pytest.fixture()
def auth_headers():
    return {"Authorization": "Bearer test-token"}
