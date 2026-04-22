from __future__ import annotations


def test_core_contract_endpoints_exist(client, auth_headers):
    paths = [
        "/api/markets",
        "/api/search?q=AAPL",
        "/api/quote/AAPL",
        "/api/portfolio",
        "/api/portfolio/performance",
        "/api/trades/history",
        "/api/watchlists",
        "/api/alerts",
        "/api/news/market",
        "/api/news/stock/AAPL",
        "/api/news/sector",
        "/api/news/macro",
        "/api/calendar/events",
        "/api/learning/dashboard",
        "/api/learning/curriculum",
        "/api/learning/weekly-summary",
        "/api/learning/health-score",
        "/api/learning/explain-portfolio",
        "/api/learning/portfolio-move-why",
        "/api/learning/mistakes",
        "/api/learning/coach",
        "/api/learning/chat/history",
        "/api/learning/center",
        "/api/learning/quizzes",
        "/api/learning/challenges",
        "/api/learning/streaks",
        "/api/help/onboarding",
        "/api/help/glossary",
        "/api/help/tooltips",
        "/api/help/support",
        "/api/ai/dashboard-brief",
        "/api/ai/quote-signal?symbol=AAPL",
        "/api/dashboard/summary",
        "/api/tools/sip-calculator?monthly_investment=1000&years=10",
        "/api/tools/scenario-simulator?market_move_pct=-5",
        "/api/tools/risk-lite?symbol=AAPL",
        "/api/tools/forecast-lite?symbol=AAPL",
    ]
    for path in paths:
        response = client.get(path, headers=auth_headers)
        assert response.status_code in {200, 422}, f"{path} failed with {response.status_code}"


def test_trade_flow_with_checklist(client, auth_headers):
    response = client.post(
        "/api/trades/buy",
        headers=auth_headers,
        json={"symbol": "AAPL", "quantity": 2, "order_type": "market", "notes": "starter trade"},
    )
    assert response.status_code == 400

    response = client.post(
        "/api/trades/buy",
        headers=auth_headers,
        json={
            "symbol": "AAPL",
            "quantity": 2,
            "order_type": "market",
            "notes": "starter trade",
            "checklist": {
                "thesis": "trend continuation",
                "risk_level": "medium",
                "time_horizon": "2 weeks",
                "buy_reason": "learning setup",
                "trade_type": "speculative",
            },
        },
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["trade"]["side"] == "buy"
    assert payload["portfolio"]["positions"]


def test_trade_buy_can_create_stop_loss_and_trailing_stop_orders(client, auth_headers):
    response = client.post(
        "/api/trades/buy",
        headers=auth_headers,
        json={
            "symbol": "AAPL",
            "quantity": 2,
            "order_type": "market",
            "notes": "starter trade",
            "stop_loss_price": 95.0,
            "trailing_stop_percent": 2.0,
            "checklist": {
                "thesis": "trend continuation",
                "risk_level": "medium",
                "time_horizon": "2 weeks",
                "buy_reason": "risk control",
                "trade_type": "speculative",
            },
        },
    )
    assert response.status_code == 200
    payload = response.json()
    assert len(payload.get("protective_orders", [])) == 2
    order_types = {row["order_type"] for row in payload["protective_orders"]}
    assert order_types == {"stop_loss", "trailing_stop"}

    orders = client.app.state.repo.list_orders("test-user", market="US")
    assert len(orders) == 2


def test_trade_buy_rejects_both_trailing_percent_and_amount(client, auth_headers):
    response = client.post(
        "/api/trades/buy",
        headers=auth_headers,
        json={
            "symbol": "AAPL",
            "quantity": 1,
            "order_type": "market",
            "trailing_stop_percent": 2.0,
            "trailing_stop_amount": 1.0,
            "checklist": {
                "thesis": "validation check",
                "risk_level": "medium",
                "time_horizon": "2 weeks",
                "buy_reason": "validation",
                "trade_type": "speculative",
            },
        },
    )
    assert response.status_code == 422


def test_watchlist_crud(client, auth_headers):
    create = client.post("/api/watchlists", headers=auth_headers, json={"name": "Tech", "symbols": ["AAPL"]})
    assert create.status_code == 200
    watchlist_id = create.json()["id"]

    update = client.put(f"/api/watchlists/{watchlist_id}", headers=auth_headers, json={"notes": "Learner list"})
    assert update.status_code == 200
    assert update.json()["notes"] == "Learner list"

    listing = client.get("/api/watchlists", headers=auth_headers)
    assert listing.status_code == 200
    assert len(listing.json()["watchlists"]) >= 1

    shared = client.get(f"/api/watchlists/share/{watchlist_id}")
    assert shared.status_code == 200
    assert shared.json()["watchlist"]["id"] == watchlist_id

    deletion = client.delete(f"/api/watchlists/{watchlist_id}", headers=auth_headers)
    assert deletion.status_code == 200


def test_dashboard_refreshes_position_prices_from_quote_feed(client, auth_headers):
    buy = client.post(
        "/api/trades/buy",
        headers=auth_headers,
        json={
            "symbol": "AAPL",
            "quantity": 2,
            "order_type": "market",
            "notes": "price sync check",
            "checklist": {
                "thesis": "sync test",
                "risk_level": "medium",
                "time_horizon": "2 weeks",
                "buy_reason": "verify dashboard mark-to-market",
                "trade_type": "speculative",
            },
        },
    )
    assert buy.status_code == 200

    client.app.state.market_data.quote = lambda symbol, market: {  # type: ignore[assignment]
        "symbol": "AAPL",
        "name": "Apple Inc.",
        "price": 150.0,
        "change_pct": 2.5,
        "currency": "USD",
    }

    response = client.get("/", headers=auth_headers)
    assert response.status_code == 200
    assert "$150.00" in response.text
    assert "$10100.00" in response.text


def test_protected_routes_require_auth(client):
    response = client.get("/api/portfolio")
    assert response.status_code == 401


def test_absent_pro_admin_routes(client):
    for path in ["/api/admin", "/api/team", "/api/subscriptions", "/api/pricing"]:
        response = client.get(path)
        assert response.status_code == 404
