from __future__ import annotations

from types import SimpleNamespace

from learner_fastapi_firebase.app.services.pro_market_intel import ProMarketIntelService


class _Market:
    def quote(self, symbol, market): return {"symbol": symbol, "price": 10.0}
    def quote_history(self, symbol, market, **_kwargs): return {"close": [9.0, 10.0]}
    def quote_corporate_actions(self, symbol, market, **_kwargs): return {"dividends": [], "splits": []}
    def stock_news(self, symbol, market, **_kwargs): return []
    def risk_lite(self, symbol, market): return {}
    def forecast_lite(self, symbol, market): return {}
    def benchmark_quote(self, market): return {}
    def market_mood(self, market): return {}


def test_pro_snapshot_has_baseline_when_hosted_sources_are_not_configured():
    service = ProMarketIntelService(_Market())
    snapshot = service.snapshot("u1", "aapl", "US")
    assert snapshot["symbol"] == "AAPL"
    assert snapshot["technical"]["month_change_pct"] == 11.11
    assert snapshot["community"]["label"] == "Community Pulse — Unverified"
    assert snapshot["sources"][-1]["status"] == "not_configured"


def test_hosted_intel_uses_a_signed_in_execution_request(monkeypatch):
    service = ProMarketIntelService(
        _Market(), appwrite_endpoint="https://example.appwrite.io/v1", appwrite_project_id="project",
        appwrite_function_id="intel", session_provider=lambda _uid: "session-token",
    )
    captured = {}
    def fake_post(url, **kwargs):
        captured["url"] = url; captured.update(kwargs)
        return SimpleNamespace(raise_for_status=lambda: None, json=lambda: {"responseBody": '{"sources":[]}'})
    monkeypatch.setattr("learner_fastapi_firebase.app.services.pro_market_intel.requests.post", fake_post)
    assert service._hosted_intel("u1", "AAPL", "US") == {"sources": []}
    assert captured["headers"]["X-Appwrite-Session"] == "session-token"
    assert captured["headers"]["Cookie"] == "a_session_project=session-token"
    assert captured["json"]["body"] == '{"symbol":"AAPL","market":"US"}'
