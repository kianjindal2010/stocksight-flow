from __future__ import annotations


def test_pro_dashboard_and_stock_workspace_are_available(client, auth_headers, app, monkeypatch):
    intel = app.state.pro_market_intel
    monkeypatch.setattr(
        intel,
        "snapshot",
        lambda _uid, symbol, market, **_kwargs: {
            "symbol": symbol,
            "market": market,
            "generated_at": "2026-01-01T00:00:00+00:00",
            "quote": {"symbol": symbol, "name": "Apple Inc.", "price": 100, "change_pct": 1, "currency": "USD"},
            "history": {"close": [95, 100]}, "actions": {}, "news": [], "risk": {}, "forecast": {}, "benchmark": {}, "market_mood": {},
            "technical": {"month_change_pct": 2.0}, "sources": [], "filings": [], "fundamentals": {}, "earnings": {},
            "community": {"label": "Community Pulse — Unverified", "mention_count": 0, "posts": []},
        },
    )
    dashboard = client.get("/pro", headers=auth_headers)
    stock = client.get("/pro/stocks/AAPL", headers=auth_headers)
    assert dashboard.status_code == 200
    assert "Research Desk" in dashboard.text
    assert stock.status_code == 200
    assert "Community Pulse" in stock.text
    assert "AI Research Brief" in stock.text


def test_pro_research_is_saved_separately_from_flow(client, auth_headers, app):
    response = client.post(
        "/pro/stocks/AAPL/research",
        headers=auth_headers,
        data={"thesis": "Quality cash flows", "catalysts": "Earnings", "review_date": "2026-09-01", "notes": "Check valuation."},
        follow_redirects=False,
    )
    assert response.status_code == 303
    saved = app.state.repo.get_learning_doc("test-user", "pro_workspace")
    assert saved["research"]["AAPL"]["thesis"] == "Quality cash flows"
    # Flow's separate watchlist document is untouched by a Pro note.
    assert app.state.repo.list_watchlists("test-user") == []


def test_pro_watchlist_is_isolated_from_flow_watchlists(client, auth_headers, app):
    response = client.post("/pro/watchlist", headers=auth_headers, data={"symbol": "msft"}, follow_redirects=False)
    assert response.status_code == 303
    workspace = app.state.repo.get_learning_doc("test-user", "pro_workspace")
    assert workspace["watchlist_symbols"] == ["MSFT"]
    assert app.state.repo.list_watchlists("test-user") == []
