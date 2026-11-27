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


def test_portfolio_deposit_increases_cash(client, auth_headers):
    before = client.get("/api/portfolio", headers=auth_headers)
    assert before.status_code == 200
    before_cash = before.json()["cash"]

    deposit = client.post(
        "/api/portfolio/deposit",
        headers=auth_headers,
        json={"amount": 500, "notes": "manual top-up"},
    )
    assert deposit.status_code == 200
    payload = deposit.json()
    assert payload["amount"] == 500
    assert payload["cash"] == before_cash + 500
    assert payload["portfolio"]["cash"] == before_cash + 500


def test_portfolio_deposit_requires_positive_amount(client, auth_headers):
    response = client.post("/api/portfolio/deposit", headers=auth_headers, json={"amount": 0})
    assert response.status_code == 422


def test_portfolio_performance_total_return_excludes_cash_deposits(client, auth_headers):
    deposit = client.post(
        "/api/portfolio/deposit",
        headers=auth_headers,
        json={"amount": 10000, "notes": "top-up"},
    )
    assert deposit.status_code == 200

    perf = client.get("/api/portfolio/performance", headers=auth_headers)
    assert perf.status_code == 200
    payload = perf.json()
    assert payload["return_total_pct"] == 0.0


def test_portfolio_performance_today_return_includes_open_position_day_move(client, auth_headers):
    buy = client.post(
        "/api/trades/buy",
        headers=auth_headers,
        json={
            "symbol": "AAPL",
            "quantity": 2,
            "order_type": "market",
            "notes": "today return check",
            "checklist": {
                "thesis": "trend continuation",
                "risk_level": "medium",
                "time_horizon": "2 weeks",
                "buy_reason": "measure intraday move",
                "trade_type": "speculative",
            },
        },
    )
    assert buy.status_code == 200

    # The dashboard refreshes price marks after its page opens.
    summary = client.get("/api/dashboard/summary", headers=auth_headers)
    assert summary.status_code == 200

    perf = client.get("/api/portfolio/performance", headers=auth_headers)
    assert perf.status_code == 200
    payload = perf.json()
    assert payload["return_today_pct"] != 0.0


def test_portfolio_performance_infers_legacy_deposits_from_accounting_identity(client, auth_headers):
    repo = client.app.state.repo
    state = repo._load_state("test-user")
    portfolio, _ = repo._ensure_market_bucket(state, "US")
    portfolio["cash"] = 20000.0
    portfolio["starting_cash"] = 10000.0
    portfolio["realized_pnl"] = 0.0
    portfolio["net_deposits"] = 0.0
    repo._save_state("test-user", state)

    perf = client.get("/api/portfolio/performance", headers=auth_headers)
    assert perf.status_code == 200
    payload = perf.json()
    assert payload["return_total_pct"] == 0.0


def test_dashboard_pl_pct_uses_price_vs_avg_fallback(client, auth_headers):
    buy = client.post(
        "/api/trades/buy",
        headers=auth_headers,
        json={
            "symbol": "AAPL",
            "quantity": 2,
            "order_type": "market",
            "notes": "pl pct fallback check",
            "checklist": {
                "thesis": "trend continuation",
                "risk_level": "medium",
                "time_horizon": "2 weeks",
                "buy_reason": "pl fallback",
                "trade_type": "speculative",
            },
        },
    )
    assert buy.status_code == 200

    client.app.state.market_data.quote = lambda symbol, market: {  # type: ignore[assignment]
        "symbol": "AAPL",
        "name": "Apple Inc.",
        "price": 120.0,
        "change_pct": 2.5,
        "currency": "USD",
    }

    summary = client.get("/api/dashboard/summary", headers=auth_headers)
    assert summary.status_code == 200
    assert summary.json()["positions"][0]["total_change_pct"] == 20.0


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
    assert "$150.00" not in response.text
    summary = client.get("/api/dashboard/summary", headers=auth_headers)
    assert summary.status_code == 200
    assert summary.json()["positions"][0]["last_price"] == 150.0
    assert summary.json()["portfolio"]["total_value"] == 10100.0


def test_dashboard_performer_cards_use_daily_change(client, auth_headers):
    repo = client.app.state.repo
    for symbol, avg_price in [
        ("WIN", 100.0),
        ("LOSS", 100.0),
        ("UPLOSS", 120.0),
        ("DOWNGAIN", 100.0),
    ]:
        repo.apply_trade(
            uid="test-user",
            market="US",
            side="buy",
            symbol=symbol,
            quantity=10,
            price=avg_price,
            order_type="market",
        )

    quotes = {
        "WIN": {"price": 130.0, "change_pct": 3.0},
        "LOSS": {"price": 90.0, "change_pct": -2.0},
        "UPLOSS": {"price": 95.0, "change_pct": 1.0},
        "DOWNGAIN": {"price": 110.0, "change_pct": -1.0},
    }

    def quote(symbol, market):
        row = quotes[str(symbol).upper()]
        return {
            "symbol": symbol,
            "name": symbol,
            "price": row["price"],
            "change_pct": row["change_pct"],
            "currency": "USD",
        }

    client.app.state.market_data.quote = quote  # type: ignore[assignment]

    response = client.get("/api/dashboard/summary", headers=auth_headers)
    assert response.status_code == 200
    data = response.json()
    top = {row["symbol"]: row["day_change_pct"] for row in data["top_positions"]}
    worst = {row["symbol"]: row["day_change_pct"] for row in data["worst_positions"]}
    assert top == {"WIN": 3.0, "UPLOSS": 1.0}
    assert worst == {"LOSS": -2.0, "DOWNGAIN": -1.0}


def test_modules_page_completion_updates_learning_progress(client, auth_headers):
    page = client.get("/modules", headers=auth_headers)
    assert page.status_code == 200
    assert "Learning Modules" in page.text

    submit = client.post(
        "/modules/complete",
        headers=auth_headers,
        data={"module_id": "market_basics", "action": "complete"},
    )
    assert submit.status_code == 200

    progress = client.app.state.repo.get_learning_doc("test-user", "progress", default={})
    assert progress.get("completed_modules") == 1
    assert "market_basics" in (progress.get("completed_module_ids") or [])

    learning_page = client.get("/learning-progress", headers=auth_headers)
    assert learning_page.status_code == 200
    assert "1 / 20 modules completed" in learning_page.text


def test_each_module_has_quiz_and_passing_updates_learning_progress(client, auth_headers):
    from learner_fastapi_firebase.app.services import quiz_bank

    curriculum = client.app.state.learning_engine.curriculum()
    for module in curriculum:
        questions = quiz_bank.quiz_question_bank(curriculum, module["id"])
        assert len(questions) == 20

    page = client.get("/quizzes?module_id=market_basics", headers=auth_headers)
    assert page.status_code == 200
    assert "Market Basics" in page.text
    assert page.text.count('name="answer_market_basics_q') == 80

    questions = quiz_bank.quiz_question_bank(curriculum, "market_basics")
    data = {"module_id": "market_basics"}
    data.update({f"answer_{question['id']}": str(question["answer_index"]) for question in questions})
    submit = client.post("/quizzes/submit", headers=auth_headers, data=data)
    assert submit.status_code == 200
    assert "Market Basics score: 100%" in submit.text

    progress = client.app.state.repo.get_learning_doc("test-user", "progress", default={})
    assert progress.get("completed_modules") == 1
    assert "market_basics" in (progress.get("completed_module_ids") or [])

    quizzes = client.app.state.repo.get_learning_doc("test-user", "quizzes", default={})
    assert quizzes.get("passed_modules") == 1
    assert "market_basics" in (quizzes.get("completed_quiz_module_ids") or [])


def test_protected_routes_require_auth(client):
    response = client.get("/api/portfolio")
    assert response.status_code == 401


def test_public_preview_dashboard_without_login(client):
    response = client.get("/")
    assert response.status_code == 200
    assert "My Portfolio" in response.text
    assert "Preview Mode" in response.text

    summary = client.get("/api/dashboard/summary")
    assert summary.status_code == 200
    assert summary.json()["portfolio"]["positions"]


def test_absent_pro_admin_routes(client):
    for path in ["/api/admin", "/api/team", "/api/subscriptions", "/api/pricing"]:
        response = client.get(path)
        assert response.status_code == 404


def test_watchlist_page_loads_before_quotes(client, auth_headers, monkeypatch):
    repo = client.app.state.repo
    repo.add_symbol_to_default_watchlist("test-user", "AAPL")
    calls = []

    def quote(symbol, market):
        calls.append((symbol, market))
        return {"name": "Apple", "price": 123.0, "currency": "USD", "change_pct": 2.0}

    monkeypatch.setattr(client.app.state.market_data, "quote", quote)
    page = client.get("/watchlist", headers=auth_headers)
    assert page.status_code == 200
    assert 'data-watch-symbol="AAPL"' in page.text
    assert not calls

    quotes = client.get("/api/watchlist/quotes", headers=auth_headers)
    assert quotes.status_code == 200
    assert quotes.json()["AAPL"]["price"] == 123.0
    assert calls == [("AAPL", "US")]
    assert client.get("/api/watchlist/quotes", headers=auth_headers).json() == quotes.json()
    assert calls == [("AAPL", "US")]


def test_reopening_dashboard_reuses_data_until_the_portfolio_changes(client, auth_headers, monkeypatch):
    state = client.app.state
    calls = {"coach": 0, "benchmark": 0}
    original_coach = state.ai_advisor.dashboard_brief
    original_benchmark = state.market_data.benchmark_quote

    def coach(*args, **kwargs):
        calls["coach"] += 1
        return original_coach(*args, **kwargs)

    def benchmark(*args, **kwargs):
        calls["benchmark"] += 1
        return original_benchmark(*args, **kwargs)

    monkeypatch.setattr(state.ai_advisor, "dashboard_brief", coach)
    monkeypatch.setattr(state.market_data, "benchmark_quote", benchmark)
    assert client.get("/", headers=auth_headers).status_code == 200
    for endpoint in ("/api/dashboard/summary", "/api/ai/dashboard-brief"):
        assert client.get(endpoint, headers=auth_headers).status_code == 200
    cached_calls = calls.copy()
    assert client.get("/ai-chat", headers=auth_headers).status_code == 200
    home = client.get("/", headers=auth_headers)
    assert "Test coach summary" in home.text
    for endpoint in ("/api/dashboard/summary", "/api/ai/dashboard-brief"):
        assert client.get(endpoint, headers=auth_headers).status_code == 200
    assert calls == cached_calls

    state.repo.deposit_cash("test-user", "US", 25.0)
    summary = client.get("/api/dashboard/summary", headers=auth_headers)
    assert summary.json()["portfolio"]["cash"] == 10025.0
    assert client.get("/api/ai/dashboard-brief", headers=auth_headers).status_code == 200
    assert calls["benchmark"] > cached_calls["benchmark"]
    assert calls["coach"] == cached_calls["coach"] + 1
