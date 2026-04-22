from __future__ import annotations

from copy import deepcopy

import pytest

try:
    from learner_fastapi_firebase.app.services.firestore_repo import FirestoreRepository
except ModuleNotFoundError:  # pragma: no cover - supports package-root pytest runs
    from app.services.firestore_repo import FirestoreRepository


def _deep_merge_keep_missing(base: dict, patch: dict) -> dict:
    out = deepcopy(base)
    for key, value in patch.items():
        if isinstance(value, dict) and isinstance(out.get(key), dict):
            out[key] = _deep_merge_keep_missing(out[key], value)
        else:
            out[key] = deepcopy(value)
    return out


class _FakeSnapshot:
    def __init__(self, payload: dict | None):
        self._payload = deepcopy(payload) if payload is not None else None
        self.exists = payload is not None

    def to_dict(self):
        return deepcopy(self._payload) if self._payload is not None else None


class _FakeDocument:
    def __init__(self, store: dict[str, dict], uid: str):
        self._store = store
        self._uid = uid

    def get(self):
        return _FakeSnapshot(self._store.get(self._uid))

    def set(self, payload, merge: bool = False):
        current = self._store.get(self._uid)
        if current is None:
            self._store[self._uid] = deepcopy(payload)
            return
        if merge:
            self._store[self._uid] = _deep_merge_keep_missing(current, payload)
            return
        self._store[self._uid] = deepcopy(payload)


class _FakeCollection:
    def __init__(self, store: dict[str, dict]):
        self._store = store

    def document(self, uid: str):
        return _FakeDocument(self._store, uid)


class _FakeFirestoreClient:
    def __init__(self):
        self._store: dict[str, dict] = {}

    def collection(self, name: str):
        if name != "users":
            raise KeyError(name)
        return _FakeCollection(self._store)


def test_sell_out_position_removes_symbol_and_blocks_future_oversell():
    repo = FirestoreRepository(firestore_client=_FakeFirestoreClient())
    uid = "sell-test-user"

    repo.apply_trade(uid, "US", "buy", "AAPL", 10, 100.0, "market")
    repo.apply_trade(uid, "US", "sell", "AAPL", 10, 101.0, "market")

    portfolio = repo.get_portfolio(uid, "US")
    assert portfolio["positions"] == []

    with pytest.raises(ValueError, match="Insufficient shares"):
        repo.apply_trade(uid, "US", "sell", "AAPL", 1, 101.0, "market")


def test_portfolio_read_repairs_stale_position_when_trades_net_to_zero():
    repo = FirestoreRepository(firestore_client=_FakeFirestoreClient())
    uid = "stale-position-user"

    state = repo._uid_defaults(uid)
    state["portfolio"]["US"] = {
        "market": "US",
        "cash": 10000.0,
        "starting_cash": 10000.0,
        "realized_pnl": 0.0,
        "updated_at": "2026-04-22T00:00:00+00:00",
    }
    state["positions"]["US"] = {
        "AAPL": {
            "symbol": "AAPL",
            "shares": 10,
            "avg_price": 100.0,
            "last_price": 101.0,
            "market_value": 1010.0,
            "unrealized_pnl": 10.0,
            "updated_at": "2026-04-22T00:00:00+00:00",
        }
    }
    state["trades"] = {
        "t1": {
            "id": "t1",
            "market": "US",
            "side": "buy",
            "symbol": "AAPL",
            "quantity": 10,
            "price": 100.0,
            "trade_value": 1000.0,
            "order_type": "market",
            "realized_pnl": 0.0,
            "notes": "",
            "created_at": "2026-04-22T00:00:00+00:00",
        },
        "t2": {
            "id": "t2",
            "market": "US",
            "side": "sell",
            "symbol": "AAPL",
            "quantity": 10,
            "price": 101.0,
            "trade_value": 1010.0,
            "order_type": "market",
            "realized_pnl": 10.0,
            "notes": "",
            "created_at": "2026-04-22T00:01:00+00:00",
        },
    }
    repo._save_state(uid, state)

    portfolio = repo.get_portfolio(uid, "US")
    assert portfolio["positions"] == []

    with pytest.raises(ValueError, match="Insufficient shares"):
        repo.apply_trade(uid, "US", "sell", "AAPL", 1, 100.0, "market")
