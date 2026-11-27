from __future__ import annotations


def test_pro_search_form_opens_stock_without_javascript(client, auth_headers):
    result = client.get("/pro/stocks", params={"symbol": " aapl "}, headers=auth_headers)
    assert result.status_code == 200
    assert result.url.path == "/pro/stocks/AAPL"
    assert 'data-symbol="AAPL"' in result.text


def test_pro_quote_search_resolves_company_name(client, auth_headers, app, monkeypatch):
    monkeypatch.setattr(app.state.market_data, "search_symbols", lambda query, market, limit: [
        {"symbol": "AAPL", "name": "Apple Inc."}
    ] if query == "Apple" else [])
    result = client.get("/pro/stocks", params={"q": "Apple"}, headers=auth_headers)
    assert result.status_code == 200
    assert result.url.path == "/pro/stocks/AAPL"
    assert 'data-pro-search-form' in result.text
    assert 'data-section-state="technicals"' in result.text


def test_portfolio_page_does_not_wait_for_ai(client, auth_headers, app, monkeypatch):
    def unavailable(*args, **kwargs):
        raise AssertionError("Portfolio page called hosted AI before rendering")

    monkeypatch.setattr(app.state.ai_advisor, "portfolio_explainer", unavailable)
    assert client.get("/portfolio-insights", headers=auth_headers).status_code == 200


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


def test_pro_review_dates_are_displayed_as_day_month_name_year(client, auth_headers, app):
    form = {"thesis": "Watch margins", "review_date": "25 Nov 2026"}
    response = client.post("/pro/stocks/NVDA/research", headers=auth_headers, data=form)
    assert response.status_code == 200
    assert 'value="25 Nov 2026"' in response.text
    assert 'type="date"' not in response.text
    assert 'data-chart="volume"' in response.text
    assert 'data-chart="revenue"' in response.text
    workspace = app.state.repo.get_learning_doc("test-user", "pro_workspace")
    assert workspace["research"]["NVDA"]["review_date"] == "2026-11-25"
    dashboard = client.get("/pro", headers=auth_headers)
    assert "25 Nov 2026" in dashboard.text
    assert 'type="date"' not in dashboard.text


def test_market_chart_data_does_not_wait_for_hosted_research(client, auth_headers, app, monkeypatch):
    def unexpected(*args, **kwargs):
        raise AssertionError("Market view contacted hosted research")

    monkeypatch.setattr(app.state.pro_market_intel, "snapshot", unexpected)
    monkeypatch.setattr(app.state.market_data, "quote_history",
                        lambda *args, **kwargs: {"close": [100, 110], "volume": [12, 20]})
    result = client.get("/api/pro/stocks/NVDA/snapshot?view=market", headers=auth_headers)
    assert result.status_code == 200
    assert result.json()["history"]["volume"] == [12, 20]
