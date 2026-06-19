from __future__ import annotations

from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from learner_fastapi_firebase.app.services.market_data import MarketDataService


def _buy_sample_position(client, auth_headers):
    response = client.post(
        "/api/trades/buy",
        headers=auth_headers,
        json={
            "symbol": "AAPL",
            "quantity": 1,
            "order_type": "market",
            "notes": "seed position",
            "checklist": {
                "thesis": "seed trade",
                "risk_level": "medium",
                "time_horizon": "2 weeks",
                "buy_reason": "set up stop-loss test",
                "trade_type": "speculative",
            },
        },
    )
    assert response.status_code == 200


def test_us_market_is_closed_at_1245_ist():
    service = MarketDataService()
    sample_utc = datetime(2026, 4, 21, 12, 45, tzinfo=ZoneInfo("Asia/Kolkata")).astimezone(timezone.utc)
    status = service.market_session("US", now_utc=sample_utc)
    assert status["status"] == "closed"
    assert status["label"] == "Closed"


def test_trailing_stop_sell_tracks_anchor_and_fills(client, auth_headers):
    _buy_sample_position(client, auth_headers)

    create = client.post(
        "/orders/place",
        headers=auth_headers,
        data={
            "symbol": "AAPL",
            "quantity": "1",
            "side": "sell",
            "order_type": "trailing_stop",
            "trail_percent": "3",
        },
        follow_redirects=False,
    )
    assert create.status_code == 303

    prices = iter([100.0, 110.0, 106.0])
    client.app.state.market_data.quote = lambda symbol, market: {  # type: ignore[assignment]
        "symbol": "AAPL",
        "name": "Apple Inc.",
        "price": float(next(prices)),
        "change_pct": 0.0,
        "currency": "USD",
    }

    client.get("/orders", headers=auth_headers)
    client.get("/orders", headers=auth_headers)
    client.get("/orders", headers=auth_headers)

    orders = client.app.state.repo.list_orders("test-user", "US")
    assert len(orders) == 1
    order = orders[0]
    assert order["order_type"] == "trailing_stop"
    assert order["status"] == "filled"
    assert order["trail_anchor_price"] == 110.0
    assert order["trigger_price"] == 106.7

    trades = client.app.state.repo.list_trades("test-user", market="US")
    assert trades[0]["order_type"] == "trailing_stop"


def test_buy_page_trailing_stop_starts_from_entry_price(client, auth_headers):
    response = client.post(
        "/buy",
        headers=auth_headers,
        data={
            "symbol": "AAPL",
            "quantity": "2",
            "trailing_stop_percent": "5",
        },
        follow_redirects=False,
    )

    assert response.status_code == 303
    orders = client.app.state.repo.list_orders("test-user", "US")
    assert len(orders) == 1
    assert orders[0]["trail_anchor_price"] == 100.0
    assert orders[0]["trigger_price"] == 95.0


def test_buy_page_rejects_two_protection_types_before_buying(client, auth_headers):
    response = client.post(
        "/buy",
        headers=auth_headers,
        data={
            "symbol": "AAPL",
            "quantity": "1",
            "stop_loss_price": "90",
            "trailing_stop_percent": "5",
        },
        follow_redirects=False,
    )

    assert response.status_code == 303
    assert client.app.state.repo.list_trades("test-user", market="US") == []
    assert client.app.state.repo.list_orders("test-user", "US") == []


def test_stop_loss_is_checked_outside_orders_page(client, auth_headers):
    response = client.post(
        "/buy",
        headers=auth_headers,
        data={
            "symbol": "AAPL",
            "quantity": "1",
            "stop_loss_price": "95",
        },
        follow_redirects=False,
    )
    assert response.status_code == 303

    client.app.state.market_data.quote = lambda symbol, market: {  # type: ignore[assignment]
        "symbol": "AAPL",
        "name": "Apple Inc.",
        "price": 94.0,
        "change_pct": 0.0,
        "currency": "USD",
    }
    check = client.post("/orders/check", headers=auth_headers)

    assert check.status_code == 200
    assert check.json() == {"filled": 1, "open": 0}
    orders = client.app.state.repo.list_orders("test-user", "US")
    assert orders[0]["status"] == "filled"


def test_sell_page_shows_owned_shares_and_quick_amounts(client, auth_headers):
    buy = client.post(
        "/api/trades/buy",
        headers=auth_headers,
        json={
            "symbol": "AAPL",
            "quantity": 8,
            "order_type": "market",
            "notes": "seed position",
            "checklist": {
                "thesis": "seed trade",
                "risk_level": "medium",
                "time_horizon": "2 weeks",
                "buy_reason": "test sell controls",
                "trade_type": "speculative",
            },
        },
    )
    assert buy.status_code == 200

    page = client.get("/sell", headers=auth_headers)

    assert page.status_code == 200
    assert "8 shares owned" in page.text
    assert 'data-sell-fraction="0.25"' in page.text
    assert 'data-sell-fraction="0.5"' in page.text
    assert 'data-sell-fraction="1"' in page.text


def test_paired_api_protective_orders_cancel_the_unused_exit(client, auth_headers):
    buy = client.post(
        "/api/trades/buy",
        headers=auth_headers,
        json={
            "symbol": "AAPL",
            "quantity": 1,
            "order_type": "market",
            "stop_loss_price": 95.0,
            "trailing_stop_percent": 5.0,
            "checklist": {
                "thesis": "paired protection",
                "risk_level": "medium",
                "time_horizon": "2 weeks",
                "buy_reason": "test linked exits",
                "trade_type": "speculative",
            },
        },
    )
    assert buy.status_code == 200

    client.app.state.market_data.quote = lambda symbol, market: {  # type: ignore[assignment]
        "symbol": "AAPL",
        "name": "Apple Inc.",
        "price": 94.0,
        "change_pct": 0.0,
        "currency": "USD",
    }
    check = client.post("/orders/check", headers=auth_headers)

    assert check.status_code == 200
    assert check.json() == {"filled": 1, "open": 0}
    statuses = {row["status"] for row in client.app.state.repo.list_orders("test-user", "US")}
    assert statuses == {"filled", "cancelled"}
