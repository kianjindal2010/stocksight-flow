from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
import time
from typing import Any
from uuid import uuid4


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _f(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _i(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


class FirestoreRepository:
    """
    Repository abstraction with two backends:
    - Firestore (when client is available)
    - In-memory fallback (for tests/local mode)
    """

    def __init__(self, firestore_client=None) -> None:
        self.client = firestore_client
        self._mem: dict[str, dict[str, Any]] = {}
        self._state_cache: dict[str, tuple[float, dict[str, Any]]] = {}
        self._state_cache_seconds = 10.0

    def _memory(self) -> bool:
        return self.client is None

    def _uid_defaults(self, uid: str, email: str = "", display_name: str = "") -> dict[str, Any]:
        now = utc_now()
        return {
            "user": {
                "uid": uid,
                "email": email,
                "profile": {
                    "display_name": display_name or (email.split("@")[0] if email else "Learner"),
                    "workspace_name": "Trading Workspace",
                    "language": "en",
                    "timezone": "Asia/Kolkata",
                },
                "preferences": {
                    "theme_mode": "light",
                    "theme_color": "blue",
                    "layout_mode": "sidebar",
                    "saved_filters": [],
                },
                "notifications": {
                    "email_alerts": True,
                    "in_app_alerts": True,
                    "learning_reminders": True,
                },
                "selected_market": "US",
                "favorite_markets": ["US", "INDIA"],
                "created_at": now,
                "updated_at": now,
            },
            "watchlists": {},
            "alerts": {},
            "portfolio": {},
            "positions": {},
            "trades": {},
            "journal": {},
            "learning": {},
            "notifications": {},
            "orders": {},
            "cash_flows": {},
        }

    def _normalize_state(self, uid: str, state: dict[str, Any]) -> dict[str, Any]:
        defaults = self._uid_defaults(uid)
        state.setdefault("user", defaults["user"])
        user = state["user"]
        user.setdefault("profile", defaults["user"]["profile"])
        user.setdefault("preferences", defaults["user"]["preferences"])
        user.setdefault("notifications", defaults["user"]["notifications"])
        user["preferences"].setdefault("saved_filters", [])
        user.setdefault("selected_market", "US")
        user.setdefault("favorite_markets", ["US", "INDIA"])
        for key in [
            "watchlists",
            "alerts",
            "portfolio",
            "positions",
            "trades",
            "journal",
            "learning",
            "notifications",
            "orders",
            "cash_flows",
        ]:
            state.setdefault(key, {})
        return state

    def _state_ref(self, uid: str):
        return self.client.collection("users").document(uid)

    def _get_cached_state(self, uid: str) -> dict[str, Any] | None:
        row = self._state_cache.get(uid)
        if not row:
            return None
        ts, state = row
        if time.monotonic() - ts > self._state_cache_seconds:
            self._state_cache.pop(uid, None)
            return None
        return deepcopy(state)

    def _set_cached_state(self, uid: str, state: dict[str, Any]) -> None:
        self._state_cache[uid] = (time.monotonic(), deepcopy(state))

    def _load_state(self, uid: str) -> dict[str, Any]:
        if self._memory():
            if uid not in self._mem:
                self._mem[uid] = self._uid_defaults(uid)
            return self._normalize_state(uid, self._mem[uid])
        cached = self._get_cached_state(uid)
        if cached is not None:
            return self._normalize_state(uid, cached)
        snap = self._state_ref(uid).get()
        if not snap.exists:
            state = self._uid_defaults(uid)
            self._state_ref(uid).set(state, merge=True)
            self._set_cached_state(uid, state)
            return state
        state = self._normalize_state(uid, snap.to_dict() or self._uid_defaults(uid))
        self._set_cached_state(uid, state)
        return state

    def _save_state(self, uid: str, state: dict[str, Any]) -> None:
        if self._memory():
            self._mem[uid] = state
            return
        # Persist the full user document so removed nested keys (for example,
        # sold-out symbols under positions.<market>) are actually deleted.
        self._state_ref(uid).set(state)
        self._set_cached_state(uid, state)

    def ensure_user(self, uid: str, email: str = "", display_name: str = "") -> dict[str, Any]:
        state = self._load_state(uid)
        user = state["user"]
        changed = False
        if email:
            next_email = str(email)
            if str(user.get("email", "")) != next_email:
                user["email"] = next_email
                changed = True
        if display_name:
            next_name = str(display_name)
            if str(user["profile"].get("display_name", "")) != next_name:
                user["profile"]["display_name"] = next_name
                changed = True
        if changed:
            user["updated_at"] = utc_now()
            self._save_state(uid, state)
        return deepcopy(user)

    def get_profile(self, uid: str) -> dict[str, Any]:
        return deepcopy(self._load_state(uid)["user"]["profile"])

    def update_profile(self, uid: str, payload: dict[str, Any]) -> dict[str, Any]:
        state = self._load_state(uid)
        profile = state["user"]["profile"]
        profile.update({k: v for k, v in payload.items() if v is not None})
        state["user"]["updated_at"] = utc_now()
        self._save_state(uid, state)
        return deepcopy(profile)

    def get_preferences(self, uid: str) -> dict[str, Any]:
        return deepcopy(self._load_state(uid)["user"]["preferences"])

    def update_preferences(self, uid: str, payload: dict[str, Any]) -> dict[str, Any]:
        state = self._load_state(uid)
        prefs = state["user"]["preferences"]
        prefs.update({k: v for k, v in payload.items() if v is not None})
        if "saved_filters" in prefs and not isinstance(prefs["saved_filters"], list):
            prefs["saved_filters"] = []
        state["user"]["updated_at"] = utc_now()
        self._save_state(uid, state)
        return deepcopy(prefs)

    def get_saved_filters(self, uid: str) -> list[dict[str, Any]]:
        prefs = self.get_preferences(uid)
        rows = prefs.get("saved_filters") or []
        if not isinstance(rows, list):
            return []
        out: list[dict[str, Any]] = []
        for row in rows:
            if isinstance(row, dict):
                out.append(row)
        return out

    def set_saved_filters(self, uid: str, filters: list[dict[str, Any]]) -> list[dict[str, Any]]:
        clean = [row for row in filters if isinstance(row, dict)]
        self.update_preferences(uid, {"saved_filters": clean})
        return clean

    def update_notifications(self, uid: str, payload: dict[str, Any]) -> dict[str, Any]:
        state = self._load_state(uid)
        n = state["user"]["notifications"]
        n.update({k: bool(v) for k, v in payload.items()})
        state["user"]["updated_at"] = utc_now()
        self._save_state(uid, state)
        return deepcopy(n)

    def get_selected_market(self, uid: str) -> str:
        return str(self._load_state(uid)["user"].get("selected_market", "US"))

    def set_selected_market(self, uid: str, market: str) -> dict[str, Any]:
        state = self._load_state(uid)
        state["user"]["selected_market"] = market
        favorites = state["user"].setdefault("favorite_markets", [])
        if market not in favorites:
            favorites.append(market)
        state["user"]["updated_at"] = utc_now()
        self._save_state(uid, state)
        return {"selected_market": market, "favorite_markets": favorites}

    def list_watchlists(self, uid: str) -> list[dict[str, Any]]:
        state = self._load_state(uid)
        rows = list(state["watchlists"].values())
        rows.sort(key=lambda row: row.get("created_at", ""))
        return deepcopy(rows)

    def ensure_default_watchlist(self, uid: str) -> dict[str, Any]:
        state = self._load_state(uid)
        if state["watchlists"]:
            row = sorted(
                state["watchlists"].values(),
                key=lambda item: item.get("created_at", ""),
            )[0]
            return deepcopy(row)
        row = self.create_watchlist(
            uid,
            {"name": "My Watchlist", "symbols": [], "tags": ["default"], "group": "default"},
        )
        return row

    def add_symbol_to_default_watchlist(self, uid: str, symbol: str) -> dict[str, Any]:
        state = self._load_state(uid)
        row = self.ensure_default_watchlist(uid)
        symbols = [str(s).upper().strip() for s in row.get("symbols", []) if str(s).strip()]
        symbol = str(symbol).upper().strip()
        if symbol and symbol not in symbols:
            symbols.append(symbol)
        updated = self.update_watchlist(uid, row["id"], {"symbols": symbols})
        return updated

    def remove_symbol_from_default_watchlist(self, uid: str, symbol: str) -> dict[str, Any]:
        row = self.ensure_default_watchlist(uid)
        symbol = str(symbol).upper().strip()
        symbols = [s for s in row.get("symbols", []) if str(s).upper().strip() != symbol]
        updated = self.update_watchlist(uid, row["id"], {"symbols": symbols})
        return updated

    def create_watchlist(self, uid: str, payload: dict[str, Any]) -> dict[str, Any]:
        state = self._load_state(uid)
        watchlist_id = payload.get("id") or uuid4().hex[:12]
        now = utc_now()
        row = {
            "id": watchlist_id,
            "name": payload.get("name") or "My Watchlist",
            "symbols": payload.get("symbols") or [],
            "tags": payload.get("tags") or [],
            "notes": payload.get("notes") or "",
            "group": payload.get("group") or "default",
            "share_slug": payload.get("share_slug") or uuid4().hex[:10],
            "share_url": f"/api/watchlists/share/{watchlist_id}",
            "created_at": now,
            "updated_at": now,
        }
        state["watchlists"][watchlist_id] = row
        self._save_state(uid, state)
        return deepcopy(row)

    def update_watchlist(self, uid: str, watchlist_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        state = self._load_state(uid)
        row = state["watchlists"].get(watchlist_id)
        if not row:
            raise KeyError("Watchlist not found")
        row.update({k: v for k, v in payload.items() if v is not None})
        row["share_url"] = f"/api/watchlists/share/{watchlist_id}"
        row["updated_at"] = utc_now()
        self._save_state(uid, state)
        return deepcopy(row)

    def delete_watchlist(self, uid: str, watchlist_id: str) -> None:
        state = self._load_state(uid)
        state["watchlists"].pop(watchlist_id, None)
        self._save_state(uid, state)

    def get_shared_watchlist(self, watchlist_id: str) -> dict[str, Any] | None:
        # Simple lookup across memory-backed user states. In Firestore mode this
        # still works because state is loaded via user document abstraction.
        if self._memory():
            for state in self._mem.values():
                row = state.get("watchlists", {}).get(watchlist_id)
                if row:
                    return deepcopy(row)
            return None
        users = self.client.collection("users").stream()
        for snap in users:
            state = snap.to_dict() or {}
            row = (state.get("watchlists") or {}).get(watchlist_id)
            if row:
                return deepcopy(row)
        return None

    def list_alerts(self, uid: str) -> list[dict[str, Any]]:
        state = self._load_state(uid)
        rows = list(state["alerts"].values())
        rows.sort(key=lambda row: row.get("created_at", ""), reverse=True)
        return deepcopy(rows)

    def create_alert(self, uid: str, payload: dict[str, Any]) -> dict[str, Any]:
        state = self._load_state(uid)
        alert_id = uuid4().hex[:12]
        now = utc_now()
        row = {
            "id": alert_id,
            "type": payload.get("type", "price"),
            "symbol": payload.get("symbol", ""),
            "direction": payload.get("direction", "above"),
            "target": payload.get("target"),
            "message": payload.get("message", ""),
            "active": True,
            "triggered_at": None,
            "created_at": now,
            "updated_at": now,
        }
        state["alerts"][alert_id] = row
        self._save_state(uid, state)
        return deepcopy(row)

    def delete_alert(self, uid: str, alert_id: str) -> None:
        state = self._load_state(uid)
        state["alerts"].pop(alert_id, None)
        self._save_state(uid, state)

    def _ensure_market_bucket(self, state: dict[str, Any], market: str) -> tuple[dict[str, Any], bool]:
        changed = False
        if market not in state["portfolio"]:
            state["portfolio"][market] = {
                "market": market,
                "cash": 10000.0,
                "starting_cash": 10000.0,
                "net_deposits": 0.0,
                "realized_pnl": 0.0,
                "updated_at": utc_now(),
            }
            changed = True
        elif "net_deposits" not in state["portfolio"][market]:
            state["portfolio"][market]["net_deposits"] = 0.0
            changed = True
        if market not in state["positions"]:
            state["positions"][market] = {}
            changed = True
        return state["portfolio"][market], changed

    def _net_shares_for_symbol(self, state: dict[str, Any], market: str, symbol: str) -> int:
        normalized_symbol = str(symbol or "").upper().strip()
        if not normalized_symbol:
            return 0
        net = 0
        for trade in state.get("trades", {}).values():
            if str(trade.get("market", "")).upper() != str(market).upper():
                continue
            if str(trade.get("symbol", "")).upper().strip() != normalized_symbol:
                continue
            qty = max(0, _i(trade.get("quantity"), 0))
            if str(trade.get("side", "")).lower().strip() == "buy":
                net += qty
            elif str(trade.get("side", "")).lower().strip() == "sell":
                net -= qty
        return net

    def _repair_stale_positions(self, state: dict[str, Any], market: str) -> bool:
        """
        Firestore map merges can leave removed symbols behind in historical data.
        Reconcile obvious stale positions where net shares from trade ledger <= 0.
        """
        positions = state.get("positions", {}).get(market, {})
        if not isinstance(positions, dict):
            return False
        changed = False
        for symbol in list(positions.keys()):
            net_shares = self._net_shares_for_symbol(state, market, symbol)
            if net_shares <= 0:
                positions.pop(symbol, None)
                changed = True
        return changed

    def get_portfolio(self, uid: str, market: str) -> dict[str, Any]:
        state = self._load_state(uid)
        portfolio, changed = self._ensure_market_bucket(state, market)
        changed = self._repair_stale_positions(state, market) or changed
        positions = list(state["positions"][market].values())
        market_value = sum(_f(pos.get("market_value"), 0.0) for pos in positions)
        total_value = _f(portfolio.get("cash"), 0.0) + market_value
        unrealized = sum(_f(pos.get("unrealized_pnl"), 0.0) for pos in positions)
        out = {
            "market": market,
            "cash": round(_f(portfolio.get("cash")), 2),
            "starting_cash": round(_f(portfolio.get("starting_cash")), 2),
            "net_deposits": round(_f(portfolio.get("net_deposits")), 2),
            "realized_pnl": round(_f(portfolio.get("realized_pnl")), 2),
            "unrealized_pnl": round(unrealized, 2),
            "market_value": round(market_value, 2),
            "total_value": round(total_value, 2),
            "positions": deepcopy(positions),
            "updated_at": portfolio.get("updated_at", utc_now()),
        }
        if changed:
            portfolio["updated_at"] = utc_now()
            self._save_state(uid, state)
        return out

    def refresh_position_prices(self, uid: str, market: str, latest_prices: dict[str, Any]) -> dict[str, Any]:
        state = self._load_state(uid)
        portfolio, changed = self._ensure_market_bucket(state, market)
        positions = state["positions"][market]

        updated = False
        for symbol, row in positions.items():
            key = str(symbol).upper().strip()
            payload = latest_prices.get(key)
            if isinstance(payload, dict):
                last_price = _f(payload.get("price"), 0.0)
                day_change_pct = _f(payload.get("change_pct"), _f(row.get("day_change_pct"), 0.0))
                previous_close = _f(payload.get("previous_close"), _f(row.get("previous_close"), 0.0))
            else:
                last_price = _f(payload, 0.0)
                day_change_pct = _f(row.get("day_change_pct"), 0.0)
                previous_close = _f(row.get("previous_close"), 0.0)
            if last_price <= 0:
                continue
            shares = max(0, _i(row.get("shares"), 0))
            avg_price = _f(row.get("avg_price"), 0.0)
            if previous_close <= 0 and day_change_pct > -100.0:
                previous_close = last_price / (1 + (day_change_pct / 100.0))
            if previous_close <= 0:
                previous_close = last_price
            day_unrealized = (last_price - previous_close) * shares
            row["last_price"] = round(last_price, 4)
            row["market_value"] = round(shares * last_price, 2)
            row["unrealized_pnl"] = round((last_price - avg_price) * shares, 2)
            row["previous_close"] = round(previous_close, 4)
            row["day_change_pct"] = round(day_change_pct, 2)
            row["day_unrealized_pnl"] = round(day_unrealized, 2)
            row["updated_at"] = utc_now()
            positions[symbol] = row
            updated = True

        if updated:
            portfolio["updated_at"] = utc_now()
            self._save_state(uid, state)
        elif changed:
            self._save_state(uid, state)
        return self.get_portfolio(uid, market)

    def get_portfolio_performance(self, uid: str, market: str) -> dict[str, Any]:
        state = self._load_state(uid)
        portfolio = self.get_portfolio(uid, market)
        start = _f(portfolio.get("starting_cash"), 0.0)
        net_deposits = _f(portfolio.get("net_deposits"), 0.0)
        realized = _f(portfolio.get("realized_pnl"), 0.0)
        unrealized = _f(portfolio.get("unrealized_pnl"), 0.0)
        invested_capital = start + net_deposits
        total = _f(portfolio.get("total_value"), 0.0)

        # One-time legacy migration support:
        # accounts that had deposits before net_deposits/cash_flows existed can
        # be inferred from accounting identity:
        # total_value = starting_cash + net_deposits + realized + unrealized
        inferred_legacy_deposits = total - start - realized - unrealized
        if net_deposits <= 0 and inferred_legacy_deposits > 0.01:
            net_deposits = round(inferred_legacy_deposits, 2)
            invested_capital = start + net_deposits
            bucket = state.get("portfolio", {}).get(market)
            if isinstance(bucket, dict):
                bucket["net_deposits"] = net_deposits
                bucket["updated_at"] = utc_now()
                self._save_state(uid, state)

        ret_total = ((total - invested_capital) / invested_capital) * 100 if invested_capital > 0 else 0.0

        trades = sorted(
            [t for t in state["trades"].values() if t.get("market") == market],
            key=lambda row: row.get("created_at", ""),
        )
        daily_realized: dict[str, float] = {}
        for trade in trades:
            day = str(trade.get("created_at", ""))[:10]
            daily_realized.setdefault(day, 0.0)
            daily_realized[day] += _f(trade.get("realized_pnl"), 0.0)

        cash_flows = [
            flow
            for flow in state.get("cash_flows", {}).values()
            if str(flow.get("market", "")).upper() == str(market).upper()
            and str(flow.get("type", "")).lower() == "deposit"
        ]
        daily_deposits: dict[str, float] = {}
        for flow in cash_flows:
            day = str(flow.get("created_at", ""))[:10]
            daily_deposits.setdefault(day, 0.0)
            daily_deposits[day] += _f(flow.get("amount"), 0.0)

        eq = start
        curve = []
        for day in sorted(set(daily_realized.keys()) | set(daily_deposits.keys())):
            eq += daily_deposits.get(day, 0.0)
            eq += daily_realized.get(day, 0.0)
            curve.append({"date": day, "equity": round(eq, 2)})
        if not curve:
            curve.append({"date": utc_now()[:10], "equity": round(total, 2)})

        today = utc_now()[:10]
        today_realized = daily_realized.get(today, 0.0)
        today_deposits = daily_deposits.get(today, 0.0)
        today_unrealized = sum(_f(pos.get("day_unrealized_pnl"), 0.0) for pos in (portfolio.get("positions") or []))
        today_pnl = today_realized + today_unrealized
        today_base = total - today_pnl - today_deposits
        ret_today = (today_pnl / today_base * 100) if today_base > 0 else 0.0
        return {
            "market": market,
            "return_total_pct": round(ret_total, 2),
            "return_today_pct": round(ret_today, 2),
            "equity_curve": curve,
        }

    def deposit_cash(self, uid: str, market: str, amount: float, notes: str = "") -> dict[str, Any]:
        state = self._load_state(uid)
        portfolio, _ = self._ensure_market_bucket(state, market)
        deposit_amount = round(_f(amount), 2)
        if deposit_amount <= 0:
            raise ValueError("Deposit amount must be greater than zero")

        current_cash = _f(portfolio.get("cash"), 0.0)
        portfolio["cash"] = round(current_cash + deposit_amount, 2)
        portfolio["net_deposits"] = round(_f(portfolio.get("net_deposits"), 0.0) + deposit_amount, 2)
        portfolio["updated_at"] = utc_now()
        flow_id = uuid4().hex[:14]
        state["cash_flows"][flow_id] = {
            "id": flow_id,
            "market": market,
            "type": "deposit",
            "amount": deposit_amount,
            "notes": notes or "",
            "created_at": utc_now(),
        }
        self._save_state(uid, state)

        return {
            "market": market,
            "amount": deposit_amount,
            "cash": round(_f(portfolio.get("cash"), 0.0), 2),
            "notes": notes or "",
            "portfolio": self.get_portfolio(uid, market),
        }

    def apply_trade(
        self,
        uid: str,
        market: str,
        side: str,
        symbol: str,
        quantity: int,
        price: float,
        order_type: str,
        notes: str = "",
    ) -> dict[str, Any]:
        state = self._load_state(uid)
        portfolio, _ = self._ensure_market_bucket(state, market)
        positions = state["positions"][market]

        side = (side or "").lower().strip()
        symbol = (symbol or "").upper().strip()
        qty = max(1, _i(quantity, 1))
        px = _f(price, 0.0)
        if px <= 0:
            raise ValueError("Price must be greater than zero")

        pos = positions.get(symbol, {"symbol": symbol, "shares": 0, "avg_price": 0.0})
        # Heal stale position rows for this symbol before enforcing sell checks.
        if self._net_shares_for_symbol(state, market, symbol) <= 0:
            positions.pop(symbol, None)
            pos = {"symbol": symbol, "shares": 0, "avg_price": 0.0}
        shares = _i(pos.get("shares"), 0)
        avg_price = _f(pos.get("avg_price"), 0.0)
        trade_value = round(px * qty, 2)
        realized = 0.0

        if side == "buy":
            cash = _f(portfolio.get("cash"), 0.0)
            if cash < trade_value:
                raise ValueError("Insufficient cash")
            new_shares = shares + qty
            new_avg = ((shares * avg_price) + trade_value) / new_shares
            portfolio["cash"] = round(cash - trade_value, 2)
            positions[symbol] = {
                "symbol": symbol,
                "shares": new_shares,
                "avg_price": round(new_avg, 4),
                "last_price": px,
                "market_value": round(new_shares * px, 2),
                "unrealized_pnl": round((px - new_avg) * new_shares, 2),
                "updated_at": utc_now(),
            }
        elif side == "sell":
            if shares < qty:
                raise ValueError("Insufficient shares")
            cash = _f(portfolio.get("cash"), 0.0)
            realized = round((px - avg_price) * qty, 2)
            new_shares = shares - qty
            portfolio["cash"] = round(cash + trade_value, 2)
            portfolio["realized_pnl"] = round(_f(portfolio.get("realized_pnl"), 0.0) + realized, 2)
            if new_shares <= 0:
                positions.pop(symbol, None)
            else:
                positions[symbol] = {
                    "symbol": symbol,
                    "shares": new_shares,
                    "avg_price": round(avg_price, 4),
                    "last_price": px,
                    "market_value": round(new_shares * px, 2),
                    "unrealized_pnl": round((px - avg_price) * new_shares, 2),
                    "updated_at": utc_now(),
                }
        else:
            raise ValueError("Invalid side")

        trade_id = uuid4().hex[:14]
        trade = {
            "id": trade_id,
            "market": market,
            "side": side,
            "symbol": symbol,
            "quantity": qty,
            "price": px,
            "trade_value": trade_value,
            "order_type": order_type,
            "realized_pnl": realized,
            "notes": notes,
            "created_at": utc_now(),
        }
        state["trades"][trade_id] = trade
        if notes:
            state["journal"][trade_id] = {
                "trade_id": trade_id,
                "thesis": notes,
                "reason_for_entry": notes if side == "buy" else "",
                "reason_for_exit": notes if side == "sell" else "",
                "lessons_learned": "",
                "outcome_review": "",
                "updated_at": utc_now(),
            }
        portfolio["updated_at"] = utc_now()
        self._save_state(uid, state)
        return {"trade": deepcopy(trade), "portfolio": self.get_portfolio(uid, market)}

    def list_trades(self, uid: str, market: str = "") -> list[dict[str, Any]]:
        state = self._load_state(uid)
        rows = list(state["trades"].values())
        if market:
            rows = [r for r in rows if r.get("market") == market]
        rows.sort(key=lambda row: row.get("created_at", ""), reverse=True)
        return deepcopy(rows)

    def list_orders(self, uid: str, market: str = "") -> list[dict[str, Any]]:
        state = self._load_state(uid)
        rows = list(state["orders"].values())
        if market:
            rows = [r for r in rows if str(r.get("market", "")).upper() == str(market).upper()]
        rows.sort(key=lambda row: row.get("created_at", ""), reverse=True)
        return deepcopy(rows)

    def create_order(
        self,
        uid: str,
        market: str,
        side: str,
        symbol: str,
        quantity: int,
        order_type: str = "limit",
        trigger_price: float | None = None,
        trail_percent: float | None = None,
        trail_amount: float | None = None,
        notes: str = "",
    ) -> dict[str, Any]:
        state = self._load_state(uid)
        order_id = uuid4().hex[:14]
        normalized_type = str(order_type).lower().strip() or "limit"
        normalized_side = str(side).lower().strip()
        allowed_types = {"market", "limit", "stop_loss", "trailing_stop"}
        if normalized_type not in allowed_types:
            raise ValueError("Unsupported order type")
        if normalized_side not in {"buy", "sell"}:
            raise ValueError("Invalid side")

        normalized_trigger = _f(trigger_price) if trigger_price is not None else None
        normalized_trail_percent = _f(trail_percent) if trail_percent is not None else None
        normalized_trail_amount = _f(trail_amount) if trail_amount is not None else None

        if normalized_type in {"limit", "stop_loss"}:
            if normalized_trigger is None or normalized_trigger <= 0:
                raise ValueError("Trigger price is required for limit/stop-loss orders")
            normalized_trail_percent = None
            normalized_trail_amount = None
        elif normalized_type == "trailing_stop":
            normalized_trigger = None
            if normalized_trail_percent is not None and normalized_trail_percent <= 0:
                raise ValueError("Trailing percent must be greater than zero")
            if normalized_trail_amount is not None and normalized_trail_amount <= 0:
                raise ValueError("Trailing amount must be greater than zero")
            if normalized_trail_percent is None and normalized_trail_amount is None:
                raise ValueError("Provide trailing percent or trailing amount for trailing stop orders")
            if normalized_trail_percent is not None and normalized_trail_amount is not None:
                raise ValueError("Use either trailing percent or trailing amount, not both")
        else:
            normalized_trigger = None
            normalized_trail_percent = None
            normalized_trail_amount = None

        row = {
            "id": order_id,
            "market": market,
            "side": normalized_side,
            "symbol": str(symbol).upper().strip(),
            "quantity": max(1, _i(quantity, 1)),
            "order_type": normalized_type,
            "trigger_price": round(normalized_trigger, 4) if normalized_trigger is not None else None,
            "trail_percent": round(normalized_trail_percent, 4) if normalized_trail_percent is not None else None,
            "trail_amount": round(normalized_trail_amount, 4) if normalized_trail_amount is not None else None,
            "trail_anchor_price": None,
            "status": "open",
            "notes": notes or "",
            "created_at": utc_now(),
            "updated_at": utc_now(),
            "filled_at": None,
            "fill_price": None,
            "trade_id": None,
        }
        state["orders"][order_id] = row
        self._save_state(uid, state)
        return deepcopy(row)

    def update_order(self, uid: str, order_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        state = self._load_state(uid)
        row = state["orders"].get(order_id)
        if not row:
            raise KeyError("Order not found")
        row.update({k: v for k, v in payload.items() if v is not None})
        row["updated_at"] = utc_now()
        state["orders"][order_id] = row
        self._save_state(uid, state)
        return deepcopy(row)

    def mark_order_filled(self, uid: str, order_id: str, fill_price: float, trade_id: str) -> dict[str, Any]:
        return self.update_order(
            uid,
            order_id,
            {
                "status": "filled",
                "fill_price": round(_f(fill_price), 4),
                "trade_id": trade_id,
                "filled_at": utc_now(),
            },
        )

    def upsert_trade_journal(self, uid: str, trade_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        state = self._load_state(uid)
        row = state["journal"].get(trade_id, {"trade_id": trade_id})
        row.update({k: v for k, v in payload.items() if v is not None})
        row["updated_at"] = utc_now()
        state["journal"][trade_id] = row
        self._save_state(uid, state)
        return deepcopy(row)

    def get_trade_journal(self, uid: str, trade_id: str) -> dict[str, Any]:
        state = self._load_state(uid)
        row = state["journal"].get(trade_id, {"trade_id": trade_id})
        return deepcopy(row)

    def get_learning_doc(self, uid: str, doc_id: str, default: dict[str, Any] | None = None) -> dict[str, Any]:
        state = self._load_state(uid)
        row = state["learning"].get(doc_id)
        if row is None:
            return deepcopy(default or {})
        return deepcopy(row)

    def set_learning_doc(self, uid: str, doc_id: str, payload: dict[str, Any], merge: bool = True) -> dict[str, Any]:
        state = self._load_state(uid)
        current = state["learning"].get(doc_id, {})
        next_doc = {**current, **payload} if merge else dict(payload)
        next_doc["updated_at"] = utc_now()
        state["learning"][doc_id] = next_doc
        self._save_state(uid, state)
        return deepcopy(next_doc)

    def list_notifications(self, uid: str) -> list[dict[str, Any]]:
        state = self._load_state(uid)
        rows = list(state["notifications"].values())
        rows.sort(key=lambda row: row.get("created_at", ""), reverse=True)
        return deepcopy(rows)

    def add_notification(self, uid: str, payload: dict[str, Any]) -> dict[str, Any]:
        state = self._load_state(uid)
        nid = uuid4().hex[:12]
        row = {
            "id": nid,
            "title": payload.get("title", "Notification"),
            "body": payload.get("body", ""),
            "type": payload.get("type", "info"),
            "read": False,
            "created_at": utc_now(),
        }
        state["notifications"][nid] = row
        self._save_state(uid, state)
        return deepcopy(row)
