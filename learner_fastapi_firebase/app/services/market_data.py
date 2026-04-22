from __future__ import annotations

import math
import logging
import threading
import time
from concurrent.futures import ThreadPoolExecutor, TimeoutError
from datetime import datetime, time as daytime, timedelta
from email.utils import parsedate_to_datetime
from time import perf_counter
from typing import Any, Callable
from urllib.parse import quote_plus
from xml.etree import ElementTree as ET
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd
import requests
import yfinance as yf

logger = logging.getLogger(__name__)


SUPPORTED_MARKETS = {
    "US": {"label": "United States", "index_symbol": "^GSPC", "benchmark": "S&P 500", "currency": "USD"},
    "INDIA": {"label": "India", "index_symbol": "^NSEI", "benchmark": "NIFTY 50", "currency": "INR"},
    "UK": {"label": "United Kingdom", "index_symbol": "^FTSE", "benchmark": "FTSE 100", "currency": "GBP"},
}

MARKET_SESSION_WINDOWS = {
    "US": {"tz": "America/New_York", "open": (9, 30), "close": (16, 0)},
    "INDIA": {"tz": "Asia/Kolkata", "open": (9, 15), "close": (15, 30)},
    "UK": {"tz": "Europe/London", "open": (8, 0), "close": (16, 30)},
}


class MarketDataService:
    def __init__(self, cache_seconds: int = 300) -> None:
        self.cache_seconds = max(1, int(cache_seconds))
        self._cache: dict[str, tuple[float, object]] = {}
        self._cache_lock = threading.Lock()
        self._inflight: dict[str, threading.Event] = {}
        self._metrics_lock = threading.Lock()
        self._metrics: dict[str, int] = {
            "cache_hits": 0,
            "cache_misses": 0,
            "coalesced_waits": 0,
            "upstream_calls": 0,
        }
        self._session = requests.Session()
        adapter = requests.adapters.HTTPAdapter(pool_connections=20, pool_maxsize=20)
        self._session.mount("http://", adapter)
        self._session.mount("https://", adapter)
        self._cache_ttl_seconds = {
            "quote": min(30, max(20, self.cache_seconds)),
            "quote_history": min(60, max(45, self.cache_seconds)),
            "market_news": 60,
            "stock_news": 60,
            "rss": 60,
            "risk_lite": min(60, max(45, self.cache_seconds)),
            "forecast_lite": min(60, max(45, self.cache_seconds)),
            "market_mood": min(60, max(45, self.cache_seconds)),
        }
        self._download_timeout_seconds = 5.0
        self._rss_timeouts = (2.5, 5.5)

    def _record_metric(self, key: str, delta: int = 1) -> None:
        with self._metrics_lock:
            self._metrics[key] = self._metrics.get(key, 0) + delta

    def metrics_snapshot(self) -> dict[str, int]:
        with self._metrics_lock:
            return dict(self._metrics)

    def _cache_ttl_for_key(self, key: str) -> int:
        prefix = key.split(":", 1)[0]
        return int(self._cache_ttl_seconds.get(prefix, self.cache_seconds))

    def _timed_upstream(self, op: str, fn: Callable[[], Any], **context: Any):
        started = perf_counter()
        self._record_metric("upstream_calls")
        try:
            return fn()
        finally:
            elapsed_ms = (perf_counter() - started) * 1000
            context_bits = " ".join(f"{k}={v}" for k, v in context.items() if v is not None)
            logger.info("market_data.upstream op=%s duration_ms=%.2f %s", op, elapsed_ms, context_bits)

    def _get_cache(self, key: str):
        with self._cache_lock:
            row = self._cache.get(key)
        if not row:
            self._record_metric("cache_misses")
            return None
        expires_at, value = row
        if time.monotonic() > expires_at:
            with self._cache_lock:
                self._cache.pop(key, None)
            self._record_metric("cache_misses")
            return None
        self._record_metric("cache_hits")
        return value

    def _set_cache(self, key: str, value: object, ttl_seconds: int | None = None) -> object:
        ttl = int(ttl_seconds or self._cache_ttl_for_key(key))
        expires_at = time.monotonic() + max(1, ttl)
        with self._cache_lock:
            self._cache[key] = (expires_at, value)
        return value

    def _coalesced_fetch(self, key: str, fetcher: Callable[[], Any]):
        cached = self._get_cache(key)
        if cached is not None:
            return cached
        owner = False
        with self._cache_lock:
            event = self._inflight.get(key)
            if event is None:
                event = threading.Event()
                self._inflight[key] = event
                owner = True
            else:
                self._record_metric("coalesced_waits")
        if not owner:
            event.wait(timeout=self._download_timeout_seconds + 5.0)
            cached = self._get_cache(key)
            if cached is not None:
                return cached
            return self._set_cache(key, fetcher())
        try:
            value = fetcher()
            return self._set_cache(key, value)
        finally:
            with self._cache_lock:
                done = self._inflight.pop(key, None)
            if done is not None:
                done.set()

    def market_session(self, market: str, now_utc: datetime | None = None) -> dict:
        key = str(market or "US").upper()
        session = MARKET_SESSION_WINDOWS.get(key, MARKET_SESSION_WINDOWS["US"])
        tz = ZoneInfo(session["tz"])
        now_local = (now_utc.astimezone(tz) if now_utc else datetime.now(tz))
        open_h, open_m = session["open"]
        close_h, close_m = session["close"]
        open_time = daytime(hour=open_h, minute=open_m)
        close_time = daytime(hour=close_h, minute=close_m)
        is_weekday = now_local.weekday() < 5
        is_open = is_weekday and open_time <= now_local.time() < close_time

        today_open = now_local.replace(hour=open_h, minute=open_m, second=0, microsecond=0)
        if is_open:
            next_session = f"Closes at {close_time.strftime('%H:%M')} {now_local.tzname() or ''}".strip()
        else:
            next_open = today_open
            if not is_weekday or now_local.time() >= close_time:
                days_ahead = 1
                while (now_local + timedelta(days=days_ahead)).weekday() >= 5:
                    days_ahead += 1
                next_open = (now_local + timedelta(days=days_ahead)).replace(hour=open_h, minute=open_m, second=0, microsecond=0)
            elif now_local.time() < open_time:
                next_open = today_open
            next_session = f"Opens {next_open.strftime('%a %H:%M')} {now_local.tzname() or ''}".strip()

        return {
            "market": key,
            "status": "open" if is_open else "closed",
            "label": "Open" if is_open else "Closed",
            "timezone": session["tz"],
            "local_time": now_local.isoformat(),
            "next_session": next_session,
        }

    def _download_with_timeout(self, tickers, period: str, interval: str) -> pd.DataFrame:
        def _run():
            return self._timed_upstream(
                "yfinance_download",
                lambda: yf.download(tickers, period=period, interval=interval, progress=False),
                tickers=str(tickers)[:80],
                period=period,
                interval=interval,
            )

        pool = ThreadPoolExecutor(max_workers=1)
        future = pool.submit(_run)
        try:
            result = future.result(timeout=self._download_timeout_seconds)
            return result if isinstance(result, pd.DataFrame) else pd.DataFrame()
        except TimeoutError:
            future.cancel()
            return pd.DataFrame()
        except Exception:
            return pd.DataFrame()
        finally:
            pool.shutdown(wait=False, cancel_futures=True)

    def batch_last_prices(self, symbols: list[str], market: str) -> dict[str, float]:
        rows = [self.normalize_symbol(symbol, market) for symbol in symbols if str(symbol).strip()]
        unique_symbols = []
        seen = set()
        for symbol in rows:
            if symbol not in seen:
                seen.add(symbol)
                unique_symbols.append(symbol)
        if not unique_symbols:
            return {}

        hist = self._download_with_timeout(unique_symbols, period="5d", interval="1d")
        if hist.empty:
            return {}

        prices: dict[str, float] = {}
        close = hist["Close"] if isinstance(hist.columns, pd.MultiIndex) and "Close" in hist.columns.get_level_values(0) else hist.get("Close")
        if close is None:
            return {}

        if isinstance(close, pd.Series):
            series = pd.to_numeric(close, errors="coerce").dropna()
            if not series.empty and len(unique_symbols) == 1:
                prices[unique_symbols[0]] = float(series.iloc[-1])
            return prices

        for symbol in close.columns:
            series = pd.to_numeric(close[symbol], errors="coerce").dropna()
            if not series.empty:
                prices[str(symbol)] = float(series.iloc[-1])
        return prices

    def markets(self) -> list[dict]:
        return [{"key": key, **value} for key, value in SUPPORTED_MARKETS.items()]

    def normalize_symbol(self, symbol: str, market: str) -> str:
        s = (symbol or "").strip().upper()
        if market == "INDIA" and s and not s.endswith((".NS", ".BO")) and s.replace("-", "").isalpha():
            s = f"{s}.NS"
        return s

    def search_symbols(self, query: str, market: str, limit: int = 12) -> list[dict]:
        q = (query or "").strip()
        if not q:
            return []
        cache_key = f"search:{market}:{q.lower()}:{limit}"
        cached = self._get_cache(cache_key)
        if cached is not None:
            return cached  # type: ignore[return-value]
        rows: list[dict] = []
        seen: set[str] = set()
        def _fetch_quotes():
            search = yf.Search(q, max_results=max(limit * 3, 20), news_count=0)
            return getattr(search, "quotes", []) or []

        try:
            quotes = self._timed_upstream("search_symbols", _fetch_quotes, market=market, query=q[:40])
        except Exception:
            quotes = []
        for item in quotes:
            symbol = self.normalize_symbol(str(item.get("symbol") or ""), market)
            if not symbol or symbol in seen:
                continue
            name = item.get("shortname") or item.get("longname") or item.get("name") or symbol
            seen.add(symbol)
            rows.append({"symbol": symbol, "name": name})
            if len(rows) >= limit:
                break
        if not rows:
            symbol_guess = self.normalize_symbol(q, market)
            rows = [{"symbol": symbol_guess, "name": symbol_guess}]
        return self._set_cache(cache_key, rows)

    def resolve_symbol(self, query: str, market: str) -> str:
        rows = self.search_symbols(query, market, limit=1)
        return rows[0]["symbol"] if rows else self.normalize_symbol(query, market)

    def quote(self, symbol: str, market: str) -> dict:
        symbol = self.normalize_symbol(symbol, market)
        cache_key = f"quote:{market}:{symbol}"
        def _fetch_quote() -> dict:
            ticker = yf.Ticker(symbol)
            fast: dict[str, Any] = {}
            info: dict[str, Any] = {}
            price = 0.0
            prev = 0.0

            try:
                raw_fast = getattr(ticker, "fast_info", None)
                if raw_fast is not None:
                    fast = dict(raw_fast)
            except Exception:
                fast = {}

            for key in ("lastPrice", "last_price", "regularMarketPrice", "currentPrice"):
                try:
                    v = fast.get(key)
                    if v is not None:
                        price = float(v)
                        if price > 0:
                            break
                except (TypeError, ValueError):
                    continue
            for key in ("previousClose", "previous_close", "regularMarketPreviousClose"):
                try:
                    v = fast.get(key)
                    if v is not None:
                        prev = float(v)
                        if prev > 0:
                            break
                except (TypeError, ValueError):
                    continue

            if price <= 0 or prev <= 0:
                try:
                    hist = ticker.history(period="5d", interval="1d", auto_adjust=False)
                except Exception:
                    hist = pd.DataFrame()
                if isinstance(hist, pd.DataFrame) and not hist.empty and "Close" in hist.columns:
                    close = pd.to_numeric(hist["Close"], errors="coerce").dropna()
                    if not close.empty:
                        price = max(price, float(close.iloc[-1]))
                        if len(close) >= 2:
                            prev = max(prev, float(close.iloc[-2]))

            needs_info = price <= 0 or prev <= 0
            if needs_info:
                try:
                    info = ticker.info or {}
                except Exception:
                    info = {}
                price = float(info.get("regularMarketPrice") or info.get("currentPrice") or price or 0.0)
                prev = float(info.get("regularMarketPreviousClose") or info.get("previousClose") or prev or 0.0)
            change_pct = ((price - prev) / prev * 100) if prev else 0.0

            if not info:
                # Pull richer fields only when needed for display values.
                try:
                    info = ticker.info or {}
                except Exception:
                    info = {}

            dividend_yield = info.get("dividendYield")
            dividend_yield_pct = None
            try:
                if dividend_yield is not None:
                    dividend_yield_pct = round(float(dividend_yield) * 100, 2)
            except (TypeError, ValueError):
                dividend_yield_pct = None
            return {
                "symbol": symbol,
                "name": info.get("longName") or info.get("shortName") or symbol,
                "price": round(price, 4),
                "change_pct": round(change_pct, 2),
                "currency": SUPPORTED_MARKETS.get(market, SUPPORTED_MARKETS["US"])["currency"],
                "summary": info.get("longBusinessSummary", ""),
                "sector": info.get("sector", ""),
                "market_cap": info.get("marketCap"),
                "volume": info.get("volume"),
                "day_high": info.get("dayHigh") or info.get("regularMarketDayHigh"),
                "day_low": info.get("dayLow") or info.get("regularMarketDayLow"),
                "fifty_two_week_high": info.get("fiftyTwoWeekHigh"),
                "fifty_two_week_low": info.get("fiftyTwoWeekLow"),
                "pe_ratio": info.get("trailingPE") or info.get("forwardPE"),
                "dividend_yield_pct": dividend_yield_pct,
                "beta": info.get("beta"),
            }

        return self._coalesced_fetch(
            cache_key,
            lambda: self._timed_upstream("quote", _fetch_quote, market=market, symbol=symbol),
        )

    def quote_history(self, symbol: str, market: str, period: str = "1y", interval: str = "1d") -> dict:
        symbol = self.normalize_symbol(symbol, market)
        cache_key = f"quote_history:{market}:{symbol}:{period}:{interval}"
        def _fetch_history() -> dict:
            hist = self._download_with_timeout(symbol, period=period, interval=interval)
            if hist is None or hist.empty:
                return {"dates": [], "open": [], "high": [], "low": [], "close": [], "volume": []}
            if isinstance(hist.columns, pd.MultiIndex):
                hist = hist.copy()
                hist.columns = hist.columns.get_level_values(0)
            frame = pd.DataFrame(
                {
                    "open": pd.to_numeric(hist.get("Open"), errors="coerce"),
                    "high": pd.to_numeric(hist.get("High"), errors="coerce"),
                    "low": pd.to_numeric(hist.get("Low"), errors="coerce"),
                    "close": pd.to_numeric(hist.get("Close"), errors="coerce"),
                    "volume": pd.to_numeric(hist.get("Volume"), errors="coerce").fillna(0.0),
                },
                index=pd.to_datetime(hist.index, errors="coerce"),
            ).dropna(subset=["close"])
            frame = frame[frame.index.notna()]
            frame["open"] = frame["open"].fillna(frame["close"])
            frame["high"] = frame["high"].fillna(frame["close"])
            frame["low"] = frame["low"].fillna(frame["close"])
            if frame.empty:
                return {"dates": [], "open": [], "high": [], "low": [], "close": [], "volume": []}
            return {
                "dates": [dt.strftime("%Y-%m-%d") for dt in frame.index],
                "open": [round(float(v), 4) for v in frame["open"]],
                "high": [round(float(v), 4) for v in frame["high"]],
                "low": [round(float(v), 4) for v in frame["low"]],
                "close": [round(float(v), 4) for v in frame["close"]],
                "volume": [round(float(v), 0) for v in frame["volume"]],
            }

        return self._coalesced_fetch(
            cache_key,
            lambda: self._timed_upstream(
                "quote_history",
                _fetch_history,
                market=market,
                symbol=symbol,
                period=period,
                interval=interval,
            ),
        )

    def quote_corporate_actions(self, symbol: str, market: str, limit: int = 8) -> dict:
        symbol = self.normalize_symbol(symbol, market)
        cache_key = f"quote_actions:{market}:{symbol}:{limit}"
        def _fetch_actions() -> dict:
            dividends: list[dict[str, object]] = []
            splits: list[dict[str, object]] = []
            try:
                ticker = yf.Ticker(symbol)
                div_series = ticker.dividends
                split_series = ticker.splits
            except Exception:
                div_series = pd.Series(dtype=float)
                split_series = pd.Series(dtype=float)

            if isinstance(div_series, pd.Series) and not div_series.empty:
                for idx, value in div_series.tail(limit).sort_index(ascending=False).items():
                    if pd.isna(value) or float(value) <= 0:
                        continue
                    dt = pd.to_datetime(idx, errors="coerce")
                    date_label = dt.strftime("%Y-%m-%d") if not pd.isna(dt) else str(idx)
                    dividends.append({"date": date_label, "amount": round(float(value), 4)})

            if isinstance(split_series, pd.Series) and not split_series.empty:
                for idx, value in split_series.tail(limit).sort_index(ascending=False).items():
                    if pd.isna(value) or float(value) == 0:
                        continue
                    dt = pd.to_datetime(idx, errors="coerce")
                    date_label = dt.strftime("%Y-%m-%d") if not pd.isna(dt) else str(idx)
                    splits.append({"date": date_label, "ratio": round(float(value), 4)})
            return {"dividends": dividends, "splits": splits}

        return self._coalesced_fetch(
            cache_key,
            lambda: self._timed_upstream("quote_actions", _fetch_actions, market=market, symbol=symbol, limit=limit),
        )

    def benchmark_quote(self, market: str) -> dict:
        config = SUPPORTED_MARKETS.get(market, SUPPORTED_MARKETS["US"])
        q = self.quote(config["index_symbol"], market)
        q["label"] = config["benchmark"]
        return q

    def _rss(self, query: str, gl: str = "US", hl: str = "en-US") -> list[dict]:
        cache_key = f"rss:{gl}:{hl}:{query.strip().lower()}"
        def _fetch_rss() -> list[dict]:
            url = (
                "https://news.google.com/rss/search?q="
                + quote_plus(query)
                + f"&hl={hl}&gl={gl}&ceid={gl}:en"
            )
            try:
                r = self._session.get(
                    url,
                    timeout=self._rss_timeouts,
                    headers={"User-Agent": "StockSightLearner/1.0"},
                )
                r.raise_for_status()
                root = ET.fromstring(r.text)
            except Exception:
                return []
            rows = []
            for item in root.findall(".//item"):
                title = (item.findtext("title") or "").strip()
                link = (item.findtext("link") or "").strip()
                src = item.find("source")
                source = src.text.strip() if src is not None and src.text else "News"
                pub_raw = (item.findtext("pubDate") or "").strip()
                published = ""
                if pub_raw:
                    try:
                        published = parsedate_to_datetime(pub_raw).isoformat()
                    except Exception:
                        published = pub_raw
                rows.append({"title": title, "link": link, "source": source, "published": published})
            return rows

        return self._coalesced_fetch(
            cache_key,
            lambda: self._timed_upstream("rss", _fetch_rss, gl=gl, hl=hl, query=query[:48]),
        )

    def market_news(self, market: str, limit: int = 12) -> list[dict]:
        cache_key = f"market_news:{market}:{limit}"
        def _fetch_market_news() -> list[dict]:
            gl = "IN" if market == "INDIA" else "US"
            hl = "en-IN" if market == "INDIA" else "en-US"
            rows = self._rss("stock market OR inflation OR central bank OR earnings", gl=gl, hl=hl)
            return rows[:limit]

        return self._coalesced_fetch(cache_key, _fetch_market_news)

    def stock_news(self, symbol: str, market: str, limit: int = 8) -> list[dict]:
        symbol = self.normalize_symbol(symbol, market)
        cache_key = f"stock_news:{market}:{symbol}:{limit}"
        def _fetch_stock_news() -> list[dict]:
            rows: list[dict] = []
            try:
                news = self._timed_upstream(
                    "stock_news_feed",
                    lambda: yf.Ticker(symbol).news or [],
                    symbol=symbol,
                    market=market,
                )
            except Exception:
                news = []
            for item in news:
                content = item.get("content") or item
                title = content.get("title") or "Untitled"
                link = content.get("canonicalUrl", {}).get("url") or content.get("link") or content.get("url") or ""
                source = (content.get("provider") or {}).get("displayName") or "News"
                published = content.get("pubDate") or ""
                if link:
                    rows.append({"title": title, "link": link, "source": source, "published": published})
                if len(rows) >= limit:
                    break
            if not rows:
                rows = self._rss(f"{symbol} stock news", gl="IN" if market == "INDIA" else "US")[:limit]
            return rows

        return self._coalesced_fetch(cache_key, _fetch_stock_news)

    def sector_news(self, sector: str = "technology", limit: int = 8) -> list[dict]:
        cache_key = f"sector_news:{sector.strip().lower()}:{limit}"
        return self._coalesced_fetch(cache_key, lambda: self._rss(f"{sector} sector stocks")[:limit])

    def macro_news(self, limit: int = 8) -> list[dict]:
        cache_key = f"macro_news:{limit}"
        return self._coalesced_fetch(
            cache_key,
            lambda: self._rss("inflation GDP central bank interest rates macro economy")[:limit],
        )

    def event_calendar_links(self, market: str) -> list[dict]:
        if market == "INDIA":
            return [
                {"name": "NSE Corporate Announcements", "url": "https://www.nseindia.com/companies-listing/corporate-filings-announcements"},
                {"name": "BSE Corporate Announcements", "url": "https://www.bseindia.com/corporates/ann.html"},
                {"name": "RBI Calendar", "url": "https://www.rbi.org.in/Scripts/BS_PressReleaseDisplay.aspx"},
            ]
        return [
            {"name": "FOMC Calendar", "url": "https://www.federalreserve.gov/monetarypolicy/fomccalendars.htm"},
            {"name": "U.S. Economic Calendar", "url": "https://www.bls.gov/schedule/news_release/"}
        ]

    def screener(self, market: str, preset: str = "top_gainers", limit: int = 20) -> list[dict]:
        cache_key = f"screener:{market}:{preset}:{limit}"
        def _fetch_screener() -> list[dict]:
            universe = (
                ["AAPL", "MSFT", "NVDA", "GOOGL", "META", "AMZN", "TSLA", "JPM", "XOM", "UNH", "AVGO", "COST"]
                if market == "US"
                else ["RELIANCE.NS", "TCS.NS", "INFY.NS", "HDFCBANK.NS", "ICICIBANK.NS", "SBIN.NS", "ITC.NS", "LT.NS"]
            )
            data = self._download_with_timeout(universe, period="1mo", interval="1d")
            if data is None or data.empty:
                return []
            close = data["Close"] if isinstance(data.columns, pd.MultiIndex) else pd.DataFrame({universe[0]: data["Close"]})
            volume = data["Volume"] if isinstance(data.columns, pd.MultiIndex) else pd.DataFrame({universe[0]: data["Volume"]})
            rows = []
            for sym in close.columns:
                series = close[sym].dropna()
                vol = volume[sym].dropna() if sym in volume.columns else pd.Series(dtype=float)
                if len(series) < 6:
                    continue
                last = float(series.iloc[-1])
                week = float(series.iloc[-6])
                change_1w = ((last - week) / week * 100) if week else 0.0
                avg_vol = float(vol.tail(20).mean()) if not vol.empty else 0.0
                row = {
                    "symbol": sym,
                    "price": round(last, 2),
                    "change_1w": round(change_1w, 2),
                    "avg_volume": round(avg_vol, 0),
                    "is_large_cap": sym in {"AAPL", "MSFT", "RELIANCE.NS", "TCS.NS"},
                    "is_dividend": sym in {"XOM", "ITC.NS", "SBIN.NS"},
                }
                rows.append(row)

            if preset == "top_losers":
                rows.sort(key=lambda r: r["change_1w"])
            elif preset == "large_cap":
                rows = [r for r in rows if r["is_large_cap"]]
            elif preset == "high_volume":
                rows.sort(key=lambda r: r["avg_volume"], reverse=True)
            elif preset == "dividend":
                rows = [r for r in rows if r["is_dividend"]]
            else:
                rows.sort(key=lambda r: r["change_1w"], reverse=True)
            return rows[:limit]

        return self._coalesced_fetch(cache_key, _fetch_screener)

    def market_mood(self, market: str) -> dict:
        cache_key = f"market_mood:{market}"
        def _fetch_mood() -> dict:
            idx = SUPPORTED_MARKETS.get(market, SUPPORTED_MARKETS["US"])["index_symbol"]
            hist = self._download_with_timeout(idx, period="6mo", interval="1d")
            if hist is None or hist.empty:
                return {"score": 50.0, "classification": "Neutral", "explanation": "Insufficient data"}
            close = hist["Close"]
            if isinstance(close, pd.DataFrame):
                close = close.iloc[:, 0]
            close = close.dropna()
            if len(close) < 30:
                return {"score": 50.0, "classification": "Neutral", "explanation": "Insufficient data"}
            returns = close.pct_change().dropna()
            momentum = (close.iloc[-1] / close.iloc[-20] - 1) * 100
            vol = returns.tail(20).std() * math.sqrt(252) * 100
            score = max(0, min(100, 50 + momentum - (vol * 0.4)))
            if score >= 67:
                label = "Greed"
            elif score <= 33:
                label = "Fear"
            else:
                label = "Neutral"
            return {
                "score": round(score, 1),
                "classification": label,
                "explanation": f"20-day momentum {momentum:+.2f}% and annualized volatility {vol:.2f}%",
            }

        return self._coalesced_fetch(cache_key, _fetch_mood)

    def risk_lite(self, symbol: str, market: str) -> dict:
        symbol = self.normalize_symbol(symbol, market)
        cache_key = f"risk_lite:{market}:{symbol}"
        def _fetch_risk_lite() -> dict:
            bench = SUPPORTED_MARKETS.get(market, SUPPORTED_MARKETS["US"])["index_symbol"]
            s_hist = self._download_with_timeout(symbol, period="1y", interval="1d")
            b_hist = self._download_with_timeout(bench, period="1y", interval="1d")
            if s_hist is None or s_hist.empty or b_hist is None or b_hist.empty:
                return {
                    "risk_score": 50,
                    "volatility_level": "Medium",
                    "diversification_status": "Unknown",
                    "beta_plain_english": "Not enough data for beta.",
                    "max_loss_warning": "Data unavailable",
                    "suggestions": ["Use more liquid symbols", "Check benchmark alignment"],
                }
            s_close = s_hist["Close"]
            b_close = b_hist["Close"]
            if isinstance(s_close, pd.DataFrame):
                s_close = s_close.iloc[:, 0]
            if isinstance(b_close, pd.DataFrame):
                b_close = b_close.iloc[:, 0]
            df = pd.concat([s_close.pct_change(), b_close.pct_change()], axis=1).dropna()
            df.columns = ["stock", "bench"]
            vol = float(df["stock"].std() * np.sqrt(252) * 100)
            cov = float(np.cov(df["stock"], df["bench"])[0, 1])
            var = float(np.var(df["bench"], ddof=1))
            beta = cov / var if var > 0 else 1.0
            score = int(max(1, min(100, 100 - vol)))
            if vol < 20:
                v_label = "Low"
            elif vol < 35:
                v_label = "Medium"
            else:
                v_label = "High"
            return {
                "risk_score": score,
                "volatility_level": v_label,
                "diversification_status": "Improve by adding uncorrelated holdings",
                "beta_plain_english": f"Beta is {beta:.2f}, meaning moves are {'stronger' if beta > 1 else 'weaker'} than the market.",
                "max_loss_warning": f"Historical drawdowns can exceed {vol * 0.8:.1f}% in stressed periods.",
                "suggestions": [
                    "Keep position sizes modest",
                    "Prefer diversified baskets for learning",
                    "Set stop-loss or review thresholds before entries",
                ],
            }

        return self._coalesced_fetch(cache_key, _fetch_risk_lite)

    def forecast_lite(self, symbol: str, market: str) -> dict:
        symbol = self.normalize_symbol(symbol, market)
        cache_key = f"forecast_lite:{market}:{symbol}"
        def _fetch_forecast_lite() -> dict:
            hist = self._download_with_timeout(symbol, period="6mo", interval="1d")
            if hist is None or hist.empty:
                return {
                    "direction": "Neutral",
                    "confidence": 0.5,
                    "simple_reason": "No recent data available",
                    "model_meaning": "Signal unavailable",
                    "recommended_action": "Observe only",
                }
            close = hist["Close"]
            if isinstance(close, pd.DataFrame):
                close = close.iloc[:, 0]
            close = close.dropna()
            ma10 = close.tail(10).mean()
            ma30 = close.tail(30).mean() if len(close) >= 30 else close.mean()
            slope = (close.iloc[-1] - close.iloc[-10]) / close.iloc[-10] if len(close) >= 10 and close.iloc[-10] else 0.0
            if ma10 > ma30 and slope > 0:
                direction = "Up"
                confidence = min(0.85, 0.55 + abs(slope) * 2)
                action = "Consider small, disciplined long bias (paper trade)."
            elif ma10 < ma30 and slope < 0:
                direction = "Down"
                confidence = min(0.85, 0.55 + abs(slope) * 2)
                action = "Avoid aggressive buys; observe or reduce risk."
            else:
                direction = "Sideways"
                confidence = 0.55
                action = "Wait for clearer trend confirmation."
            return {
                "direction": direction,
                "confidence": round(confidence, 2),
                "simple_reason": f"MA10 {ma10:.2f} vs MA30 {ma30:.2f}, 10-day slope {slope * 100:+.2f}%",
                "model_meaning": "A simple trend-based forecast, not financial advice.",
                "recommended_action": action,
            }

        return self._coalesced_fetch(cache_key, _fetch_forecast_lite)
