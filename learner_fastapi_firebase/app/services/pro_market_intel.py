from __future__ import annotations

"""Pro-only market research aggregation.

Flow deliberately keeps using MarketDataService directly.  Pro uses this
adapter so its optional hosted sources can fail independently without taking
away the baseline price, chart and news information.
"""

import logging
import json
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from typing import Any, Callable

import requests

from .market_data import MarketDataService

logger = logging.getLogger(__name__)


class ProMarketIntelService:
    def __init__(
        self,
        market_data: MarketDataService,
        *,
        appwrite_endpoint: str = "",
        appwrite_project_id: str = "",
        appwrite_function_id: str = "",
        session_provider: Callable[[str], str] | None = None,
        cache_seconds: int = 600,
    ) -> None:
        self.market_data = market_data
        self.appwrite_endpoint = appwrite_endpoint.rstrip("/")
        self.appwrite_project_id = appwrite_project_id
        self.appwrite_function_id = appwrite_function_id
        self.session_provider = session_provider or (lambda _uid: "")
        self.cache_seconds = max(60, int(cache_seconds))
        self._cache: dict[str, tuple[float, dict[str, Any]]] = {}
        self._lock = threading.Lock()

    @staticmethod
    def _now() -> str:
        return datetime.now(timezone.utc).isoformat()

    @staticmethod
    def _source(name: str, status: str, *, detail: str = "", freshness: str = "") -> dict[str, str]:
        return {"name": name, "status": status, "detail": detail, "freshness": freshness}

    def _hosted_intel(self, uid: str, symbol: str, market: str, *, refresh: bool = False) -> dict[str, Any]:
        if not (self.appwrite_endpoint and self.appwrite_project_id and self.appwrite_function_id):
            return {"sources": [self._source("Optional Pro sources", "not_configured", detail="Connect the Market Intelligence Appwrite Function to add filings, Alpha Vantage and Reddit.")]}
        token = self.session_provider(uid)
        if not token:
            return {"sources": [self._source("Optional Pro sources", "unavailable", detail="Sign in again to load hosted research sources.")]}
        url = f"{self.appwrite_endpoint}/functions/{self.appwrite_function_id}/executions"
        try:
            response = requests.post(
                url,
                headers={
                    "X-Appwrite-Project": self.appwrite_project_id,
                    "X-Appwrite-Session": token,
                    "Cookie": f"a_session_{self.appwrite_project_id}={token}",
                    "Content-Type": "application/json",
                },
                json={"body": json.dumps({"symbol": symbol, "market": market, **({"refresh": True} if refresh else {})}, separators=(",", ":")), "async": False, "method": "POST", "path": "/"},
                timeout=28,
            )
            response.raise_for_status()
            execution = response.json()
            body = execution.get("responseBody") or "{}"
            payload = json.loads(body)
            return payload if isinstance(payload, dict) else {}
        except Exception as exc:  # One provider must never block the workspace.
            logger.info("pro_hosted_intel_unavailable symbol=%s error=%s", symbol, exc)
            return {"sources": [self._source("Optional Pro sources", "unavailable", detail="Hosted sources are temporarily unavailable.")]}

    def snapshot(self, uid: str, symbol: str, market: str, *, include_hosted: bool = True, refresh: bool = False) -> dict[str, Any]:
        symbol = str(symbol or "").upper().strip()
        market = str(market or "US").upper().strip()
        cache_key = f"{uid}:{market}:{symbol}:{'full' if include_hosted else 'baseline'}"
        with self._lock:
            cached = self._cache.get(cache_key)
            if not refresh and cached and cached[0] > time.monotonic():
                return cached[1]

        # Local and hosted sources are independent.  Fan them out so a slow
        # chart or a hosted provider never serially delays the whole panel.
        tasks: dict[str, Callable[[], Any]] = {
            "quote": lambda: self.market_data.quote(symbol, market),
            "history": lambda: self.market_data.quote_history(symbol, market, period="1y", interval="1d"),
            "actions": lambda: self.market_data.quote_corporate_actions(symbol, market, limit=12),
            "news": lambda: self.market_data.stock_news(symbol, market, limit=10),
            "risk": lambda: self.market_data.risk_lite(symbol, market),
            "forecast": lambda: self.market_data.forecast_lite(symbol, market),
            "benchmark": lambda: self.market_data.benchmark_quote(market),
            "mood": lambda: self.market_data.market_mood(market),
        }
        if include_hosted:
            tasks["hosted"] = lambda: self._hosted_intel(uid, symbol, market, refresh=refresh)
        with ThreadPoolExecutor(max_workers=len(tasks)) as pool:
            futures = {name: pool.submit(task) for name, task in tasks.items()}
            values = {}
            for name, future in futures.items():
                try:
                    values[name] = future.result()
                except Exception as exc:
                    logger.info("pro_intel_source_unavailable symbol=%s source=%s error=%s", symbol, name, exc)
                    values[name] = [] if name == "news" else {}
        quote = values["quote"]
        history = values["history"]
        actions = values["actions"]
        news = values["news"] or []
        risk = values["risk"]
        forecast = values["forecast"]
        benchmark = values["benchmark"]
        mood = values["mood"]
        hosted = values.get("hosted") or {}
        closes = [float(v) for v in (history.get("close") or []) if isinstance(v, (int, float))]
        recent = closes[-21:]
        month_change = round(((recent[-1] - recent[0]) / recent[0] * 100), 2) if len(recent) > 1 and recent[0] else 0.0
        alpha_news = [
            {
                "title": str(row.get("title") or ""),
                "link": str(row.get("url") or ""),
                "source": str(row.get("source") or "Alpha Vantage"),
                "published": str(row.get("published_at") or ""),
            }
            for row in (hosted.get("alpha_news") or [])
            if isinstance(row, dict) and str(row.get("title") or "").strip()
        ]
        snapshot = {
            "symbol": symbol,
            "market": market,
            "generated_at": self._now(),
            "quote": quote,
            "history": history,
            "actions": actions,
            "news": [*news, *alpha_news][:16],
            "risk": risk,
            "forecast": forecast,
            "benchmark": benchmark,
            "market_mood": mood,
            "technical": {"month_change_pct": month_change, "observations": len(closes)},
            "sources": [
                self._source("Yahoo Finance", "available", freshness="Price, history, corporate actions"),
                self._source("Google News RSS", "available", freshness="Recent headlines; timestamps shown per item"),
                *(hosted.get("sources") or []),
            ],
            "filings": hosted.get("filings") or [],
            "company_facts": hosted.get("financials") or hosted.get("company_facts") or {"metrics": [], "health": {}},
            "fundamentals": hosted.get("fundamentals") or {},
            "earnings": hosted.get("earnings") or {},
            "macro": hosted.get("macro") or {"fred": [], "bls": []},
            "ownership": hosted.get("ownership") or {"official_filings": [], "insiders": []},
            "analyst_context": hosted.get("analyst_context") or {"recommendations": [], "price_target": {}, "peers": []},
            "global_media": hosted.get("global_media") or {"label": "Global media attention — context only", "articles": []},
            "community": hosted.get("community") or {"label": "Community Pulse — Unverified", "posts": [], "mention_count": 0},
            "hosted_loaded": include_hosted,
            "cached": bool(hosted.get("cached")) if include_hosted else False,
        }
        with self._lock:
            self._cache[cache_key] = (time.monotonic() + self.cache_seconds, snapshot)
        return snapshot
