from __future__ import annotations

import math
import time
from datetime import datetime
from email.utils import parsedate_to_datetime
from urllib.parse import quote_plus
from xml.etree import ElementTree as ET

import numpy as np
import pandas as pd
import requests
import yfinance as yf


SUPPORTED_MARKETS = {
    "US": {"label": "United States", "index_symbol": "^GSPC", "benchmark": "S&P 500", "currency": "USD"},
    "INDIA": {"label": "India", "index_symbol": "^NSEI", "benchmark": "NIFTY 50", "currency": "INR"},
    "UK": {"label": "United Kingdom", "index_symbol": "^FTSE", "benchmark": "FTSE 100", "currency": "GBP"},
}


class MarketDataService:
    def __init__(self, cache_seconds: int = 300) -> None:
        self.cache_seconds = cache_seconds
        self._cache: dict[str, tuple[float, object]] = {}

    def _get_cache(self, key: str):
        row = self._cache.get(key)
        if not row:
            return None
        ts, value = row
        if time.time() - ts > self.cache_seconds:
            self._cache.pop(key, None)
            return None
        return value

    def _set_cache(self, key: str, value: object) -> object:
        self._cache[key] = (time.time(), value)
        return value

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
        try:
            search = yf.Search(q, max_results=max(limit * 3, 20), news_count=0)
            quotes = getattr(search, "quotes", []) or []
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
        cached = self._get_cache(cache_key)
        if cached is not None:
            return cached  # type: ignore[return-value]
        info = {}
        try:
            info = yf.Ticker(symbol).info or {}
        except Exception:
            info = {}
        price = float(info.get("regularMarketPrice") or info.get("currentPrice") or 0.0)
        prev = float(info.get("regularMarketPreviousClose") or info.get("previousClose") or 0.0)
        change_pct = ((price - prev) / prev * 100) if prev else 0.0
        dividend_yield = info.get("dividendYield")
        dividend_yield_pct = None
        try:
            if dividend_yield is not None:
                dividend_yield_pct = round(float(dividend_yield) * 100, 2)
        except (TypeError, ValueError):
            dividend_yield_pct = None
        out = {
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
        return self._set_cache(cache_key, out)

    def quote_history(self, symbol: str, market: str, period: str = "1y", interval: str = "1d") -> dict:
        symbol = self.normalize_symbol(symbol, market)
        cache_key = f"quote_history:{market}:{symbol}:{period}:{interval}"
        cached = self._get_cache(cache_key)
        if cached is not None:
            return cached  # type: ignore[return-value]
        try:
            hist = yf.download(symbol, period=period, interval=interval, progress=False)
        except Exception:
            hist = pd.DataFrame()
        if hist is None or hist.empty:
            return self._set_cache(
                cache_key,
                {"dates": [], "open": [], "high": [], "low": [], "close": [], "volume": []},
            )
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
            return self._set_cache(
                cache_key,
                {"dates": [], "open": [], "high": [], "low": [], "close": [], "volume": []},
            )
        out = {
            "dates": [dt.strftime("%Y-%m-%d") for dt in frame.index],
            "open": [round(float(v), 4) for v in frame["open"]],
            "high": [round(float(v), 4) for v in frame["high"]],
            "low": [round(float(v), 4) for v in frame["low"]],
            "close": [round(float(v), 4) for v in frame["close"]],
            "volume": [round(float(v), 0) for v in frame["volume"]],
        }
        return self._set_cache(cache_key, out)

    def quote_corporate_actions(self, symbol: str, market: str, limit: int = 8) -> dict:
        symbol = self.normalize_symbol(symbol, market)
        cache_key = f"quote_actions:{market}:{symbol}:{limit}"
        cached = self._get_cache(cache_key)
        if cached is not None:
            return cached  # type: ignore[return-value]
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

        out = {"dividends": dividends, "splits": splits}
        return self._set_cache(cache_key, out)

    def benchmark_quote(self, market: str) -> dict:
        config = SUPPORTED_MARKETS.get(market, SUPPORTED_MARKETS["US"])
        q = self.quote(config["index_symbol"], market)
        q["label"] = config["benchmark"]
        return q

    def _rss(self, query: str, gl: str = "US", hl: str = "en-US") -> list[dict]:
        cache_key = f"rss:{gl}:{hl}:{query.strip().lower()}"
        cached = self._get_cache(cache_key)
        if cached is not None:
            return cached  # type: ignore[return-value]
        url = (
            "https://news.google.com/rss/search?q="
            + quote_plus(query)
            + f"&hl={hl}&gl={gl}&ceid={gl}:en"
        )
        try:
            r = requests.get(url, timeout=6, headers={"User-Agent": "StockSightLearner/1.0"})
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
        return self._set_cache(cache_key, rows)  # type: ignore[return-value]

    def market_news(self, market: str, limit: int = 12) -> list[dict]:
        cache_key = f"market_news:{market}:{limit}"
        cached = self._get_cache(cache_key)
        if cached is not None:
            return cached  # type: ignore[return-value]
        gl = "IN" if market == "INDIA" else "US"
        hl = "en-IN" if market == "INDIA" else "en-US"
        rows = self._rss("stock market OR inflation OR central bank OR earnings", gl=gl, hl=hl)
        return self._set_cache(cache_key, rows[:limit])  # type: ignore[return-value]

    def stock_news(self, symbol: str, market: str, limit: int = 8) -> list[dict]:
        symbol = self.normalize_symbol(symbol, market)
        cache_key = f"stock_news:{market}:{symbol}:{limit}"
        cached = self._get_cache(cache_key)
        if cached is not None:
            return cached  # type: ignore[return-value]
        rows: list[dict] = []
        try:
            news = yf.Ticker(symbol).news or []
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
        return self._set_cache(cache_key, rows)  # type: ignore[return-value]

    def sector_news(self, sector: str = "technology", limit: int = 8) -> list[dict]:
        cache_key = f"sector_news:{sector.strip().lower()}:{limit}"
        cached = self._get_cache(cache_key)
        if cached is not None:
            return cached  # type: ignore[return-value]
        return self._set_cache(cache_key, self._rss(f"{sector} sector stocks")[:limit])  # type: ignore[return-value]

    def macro_news(self, limit: int = 8) -> list[dict]:
        cache_key = f"macro_news:{limit}"
        cached = self._get_cache(cache_key)
        if cached is not None:
            return cached  # type: ignore[return-value]
        return self._set_cache(cache_key, self._rss("inflation GDP central bank interest rates macro economy")[:limit])  # type: ignore[return-value]

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
        cached = self._get_cache(cache_key)
        if cached is not None:
            return cached  # type: ignore[return-value]
        universe = (
            ["AAPL", "MSFT", "NVDA", "GOOGL", "META", "AMZN", "TSLA", "JPM", "XOM", "UNH", "AVGO", "COST"]
            if market == "US"
            else ["RELIANCE.NS", "TCS.NS", "INFY.NS", "HDFCBANK.NS", "ICICIBANK.NS", "SBIN.NS", "ITC.NS", "LT.NS"]
        )
        data = yf.download(universe, period="1mo", interval="1d", progress=False)
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
        return self._set_cache(cache_key, rows[:limit])  # type: ignore[return-value]

    def market_mood(self, market: str) -> dict:
        cache_key = f"market_mood:{market}"
        cached = self._get_cache(cache_key)
        if cached is not None:
            return cached  # type: ignore[return-value]
        idx = SUPPORTED_MARKETS.get(market, SUPPORTED_MARKETS["US"])["index_symbol"]
        hist = yf.download(idx, period="6mo", interval="1d", progress=False)
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
        out = {
            "score": round(score, 1),
            "classification": label,
            "explanation": f"20-day momentum {momentum:+.2f}% and annualized volatility {vol:.2f}%",
        }
        return self._set_cache(cache_key, out)  # type: ignore[return-value]

    def risk_lite(self, symbol: str, market: str) -> dict:
        symbol = self.normalize_symbol(symbol, market)
        cache_key = f"risk_lite:{market}:{symbol}"
        cached = self._get_cache(cache_key)
        if cached is not None:
            return cached  # type: ignore[return-value]
        bench = SUPPORTED_MARKETS.get(market, SUPPORTED_MARKETS["US"])["index_symbol"]
        s_hist = yf.download(symbol, period="1y", interval="1d", progress=False)
        b_hist = yf.download(bench, period="1y", interval="1d", progress=False)
        if s_hist is None or s_hist.empty or b_hist is None or b_hist.empty:
            return self._set_cache(cache_key, {
                "risk_score": 50,
                "volatility_level": "Medium",
                "diversification_status": "Unknown",
                "beta_plain_english": "Not enough data for beta.",
                "max_loss_warning": "Data unavailable",
                "suggestions": ["Use more liquid symbols", "Check benchmark alignment"],
            })  # type: ignore[return-value]
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
        out = {
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
        return self._set_cache(cache_key, out)  # type: ignore[return-value]

    def forecast_lite(self, symbol: str, market: str) -> dict:
        symbol = self.normalize_symbol(symbol, market)
        cache_key = f"forecast_lite:{market}:{symbol}"
        cached = self._get_cache(cache_key)
        if cached is not None:
            return cached  # type: ignore[return-value]
        hist = yf.download(symbol, period="6mo", interval="1d", progress=False)
        if hist is None or hist.empty:
            return self._set_cache(cache_key, {
                "direction": "Neutral",
                "confidence": 0.5,
                "simple_reason": "No recent data available",
                "model_meaning": "Signal unavailable",
                "recommended_action": "Observe only",
            })  # type: ignore[return-value]
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
        out = {
            "direction": direction,
            "confidence": round(confidence, 2),
            "simple_reason": f"MA10 {ma10:.2f} vs MA30 {ma30:.2f}, 10-day slope {slope * 100:+.2f}%",
            "model_meaning": "A simple trend-based forecast, not financial advice.",
            "recommended_action": action,
        }
        return self._set_cache(cache_key, out)  # type: ignore[return-value]
