from __future__ import annotations

import json
import time
from datetime import datetime, timezone
from typing import Any, Callable

try:
    from openai import OpenAI
except Exception:  # pragma: no cover - optional dependency fallback
    OpenAI = None  # type: ignore[assignment]


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _f(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def _score_1_to_100(value: Any, default: int = 50) -> int:
    return int(round(_clamp(_f(value, default), 1, 100)))


def _valid_api_key(value: str) -> bool:
    token = (value or "").strip()
    if not token:
        return False
    lowered = token.lower()
    blocked = {
        "your_nvidia_api_key_here",
        "$nvidia_api_key",
        "replace_me",
        "changeme",
    }
    return lowered not in blocked


class AIAdvisorService:
    def __init__(
        self,
        api_key: str,
        base_url: str,
        model: str,
        timeout_seconds: float = 20,
        cache_seconds: int = 240,
    ) -> None:
        self.model = model
        self.cache_seconds = max(30, int(cache_seconds))
        self._cache: dict[str, tuple[float, dict[str, Any]]] = {}
        self._enabled = bool(_valid_api_key(api_key) and OpenAI is not None)
        self._client = (
            OpenAI(base_url=base_url, api_key=api_key, timeout=timeout_seconds) if self._enabled else None
        )

    def _get_cache(self, key: str) -> dict[str, Any] | None:
        row = self._cache.get(key)
        if not row:
            return None
        ts, value = row
        if time.time() - ts > self.cache_seconds:
            self._cache.pop(key, None)
            return None
        return value

    def _set_cache(self, key: str, value: dict[str, Any]) -> dict[str, Any]:
        self._cache[key] = (time.time(), value)
        return value

    def _extract_json(self, text: str) -> dict[str, Any] | None:
        if not text.strip():
            return None
        start = text.find("{")
        end = text.rfind("}")
        if start < 0 or end < 0 or end <= start:
            return None
        snippet = text[start : end + 1]
        try:
            loaded = json.loads(snippet)
        except json.JSONDecodeError:
            return None
        return loaded if isinstance(loaded, dict) else None

    def _stream_chat(self, messages: list[dict[str, str]], max_tokens: int = 1400) -> str:
        if not self._client:
            return ""
        stream = self._client.chat.completions.create(
            model=self.model,
            messages=messages,
            temperature=0.45,
            top_p=0.95,
            max_tokens=max_tokens,
            extra_body={"chat_template_kwargs": {"thinking": True}},
            stream=True,
        )
        content_parts: list[str] = []
        for chunk in stream:
            if not getattr(chunk, "choices", None):
                continue
            delta = chunk.choices[0].delta
            content = getattr(delta, "content", None)
            if content:
                content_parts.append(content)
        return "".join(content_parts).strip()

    def _llm_or_fallback(
        self,
        cache_key: str,
        messages: list[dict[str, str]],
        fallback: dict[str, Any],
        normalizer: Callable[[dict[str, Any], dict[str, Any]], dict[str, Any]],
        max_tokens: int = 1400,
    ) -> dict[str, Any]:
        cached = self._get_cache(cache_key)
        if cached is not None:
            return cached
        if not self._enabled:
            return self._set_cache(cache_key, fallback)
        try:
            raw_text = self._stream_chat(messages, max_tokens=max_tokens)
            parsed = self._extract_json(raw_text)
            if not parsed:
                return self._set_cache(cache_key, fallback)
            return self._set_cache(cache_key, normalizer(parsed, fallback))
        except Exception:
            return self._set_cache(cache_key, fallback)

    def _dashboard_fallback(self, payload: dict[str, Any], reason: str = "rule_based") -> dict[str, Any]:
        market = str(payload.get("market") or "US")
        health_score = int(_f((payload.get("health") or {}).get("score"), 50))
        positions = payload.get("positions") or []
        mistakes = (payload.get("mistakes") or {}).get("mistakes") or []
        market_mood = payload.get("market_mood") or {}
        headlines = payload.get("news") or []

        if health_score >= 75:
            risk_label = "Low"
        elif health_score >= 55:
            risk_label = "Medium"
        else:
            risk_label = "High"

        first_mistake = str(mistakes[0]) if mistakes else "No major behavioral issues detected."
        if not positions:
            actions = [
                "Start with one small paper trade and write a one-line thesis.",
                "Track one US ticker and one India ticker before placing your next trade.",
                "Review the last 3 market headlines and map each headline to sector impact.",
            ]
        else:
            actions = [
                "Rebalance position sizes so no single holding dominates your paper portfolio.",
                "Write a clear exit rule for your weakest-performing holding.",
                "Place the next trade only after your checklist and thesis are complete.",
            ]

        news_watch: list[str] = []
        for item in headlines[:3]:
            title = str(item.get("title") or "").strip()
            source = str(item.get("source") or "").strip()
            if title:
                news_watch.append(f"{title} ({source or 'News'})")
        if not news_watch:
            mood_label = str(market_mood.get("classification") or "Neutral")
            news_watch = [f"Market mood is {mood_label}. Add risk slowly and stay disciplined."]

        summary = (
            f"{market} coach update: health score is {health_score}/100 with {len(positions)} active position(s). "
            f"Main improvement area: {first_mistake}"
        )
        return {
            "headline": f"{market} Paper Trading Coach",
            "summary": summary,
            "risk_level": risk_label,
            "actions": actions,
            "news_watch": news_watch,
            "disclaimer": "For education and paper trading only, not financial advice.",
            "source": reason,
            "generated_at": _now_iso(),
            "model": self.model if self._enabled else "rule-based",
        }

    def _normalize_dashboard(self, raw: dict[str, Any], fallback: dict[str, Any]) -> dict[str, Any]:
        actions = raw.get("actions")
        if not isinstance(actions, list) or not actions:
            actions = fallback["actions"]
        else:
            actions = [str(item).strip() for item in actions if str(item).strip()][:4] or fallback["actions"]

        news_watch = raw.get("news_watch")
        if not isinstance(news_watch, list):
            news_watch = fallback["news_watch"]
        else:
            news_watch = [str(item).strip() for item in news_watch if str(item).strip()][:4] or fallback["news_watch"]

        risk_level = str(raw.get("risk_level") or fallback["risk_level"]).strip().title()
        if risk_level not in {"Low", "Medium", "High"}:
            risk_level = fallback["risk_level"]

        return {
            "headline": str(raw.get("headline") or fallback["headline"]).strip(),
            "summary": str(raw.get("summary") or fallback["summary"]).strip(),
            "risk_level": risk_level,
            "actions": actions,
            "news_watch": news_watch,
            "disclaimer": str(raw.get("disclaimer") or fallback["disclaimer"]).strip(),
            "source": "nvidia_llm",
            "generated_at": _now_iso(),
            "model": self.model,
        }

    def dashboard_brief(self, uid: str, market: str, payload: dict[str, Any]) -> dict[str, Any]:
        prompt_payload = {
            "market": market,
            "dashboard": payload.get("dashboard") or {},
            "portfolio": payload.get("portfolio") or {},
            "health": payload.get("health") or {},
            "mistakes": payload.get("mistakes") or {},
            "weekly_summary": payload.get("weekly_summary") or {},
            "market_mood": payload.get("market_mood") or {},
            "news": payload.get("news") or [],
            "positions": payload.get("positions") or [],
            "top_positions": payload.get("top_positions") or [],
            "worst_positions": payload.get("worst_positions") or [],
        }
        fallback = self._dashboard_fallback({**payload, "market": market}, reason="rule_based")
        system = (
            "You are a calm, practical paper-trading coach for beginner investors. "
            "Respond in compact JSON only. No markdown and no prose outside JSON."
        )
        user = (
            "Analyze this paper-trading snapshot and return JSON with keys: "
            "headline (string), summary (string), risk_level (Low|Medium|High), "
            "actions (array of 3-4 concrete next steps), news_watch (array of 2-4 items), "
            "disclaimer (one sentence). Keep advice educational and specific.\n"
            f"Snapshot:\n{json.dumps(prompt_payload, ensure_ascii=True)}"
        )
        messages = [{"role": "system", "content": system}, {"role": "user", "content": user}]
        return self._llm_or_fallback(
            cache_key=f"dashboard:{uid}:{market}",
            messages=messages,
            fallback=fallback,
            normalizer=self._normalize_dashboard,
        )

    def _portfolio_fallback(self, payload: dict[str, Any], reason: str = "rule_based") -> dict[str, Any]:
        plain = str(payload.get("plain_english") or "").strip()
        if not plain:
            plain = "Think of your portfolio as a game team: cash is your bench and stocks are players on the field."
        return {
            "plain_english": plain,
            "analogy": "Cash is your safety helmet, and each stock is a player in your team.",
            "why_it_moved": "Prices move because of company news, market mood, and how much risk traders are taking.",
            "next_steps": [
                "Keep each position size reasonable so one bad day does not wreck your score.",
                "Write one sentence before each trade: why buy, where to exit, and what can go wrong.",
                "Review headlines once daily and connect each headline to one holding.",
            ],
            "source": reason,
            "generated_at": _now_iso(),
            "model": self.model if self._enabled else "rule-based",
        }

    def _normalize_portfolio(self, raw: dict[str, Any], fallback: dict[str, Any]) -> dict[str, Any]:
        steps = raw.get("next_steps")
        if not isinstance(steps, list):
            steps = fallback["next_steps"]
        else:
            steps = [str(item).strip() for item in steps if str(item).strip()][:4] or fallback["next_steps"]
        return {
            "plain_english": str(raw.get("plain_english") or fallback["plain_english"]).strip(),
            "analogy": str(raw.get("analogy") or fallback["analogy"]).strip(),
            "why_it_moved": str(raw.get("why_it_moved") or fallback["why_it_moved"]).strip(),
            "next_steps": steps,
            "source": "nvidia_llm",
            "generated_at": _now_iso(),
            "model": self.model,
        }

    def portfolio_explainer(self, uid: str, market: str, payload: dict[str, Any]) -> dict[str, Any]:
        fallback = self._portfolio_fallback(payload, reason="rule_based")
        system = (
            "You are an investing tutor for teenagers using a paper-trading app. "
            "Respond only with JSON and keep language simple."
        )
        user = (
            "Return JSON with keys: plain_english, analogy, why_it_moved, next_steps (3-4 bullets). "
            "Use easy words and no jargon.\n"
            f"Portfolio snapshot:\n{json.dumps(payload, ensure_ascii=True)}"
        )
        messages = [{"role": "system", "content": system}, {"role": "user", "content": user}]
        return self._llm_or_fallback(
            cache_key=f"portfolio:{uid}:{market}",
            messages=messages,
            fallback=fallback,
            normalizer=self._normalize_portfolio,
            max_tokens=900,
        )

    def _forecast_fallback(self, symbol: str, payload: dict[str, Any], reason: str = "rule_based") -> dict[str, Any]:
        direction = str(payload.get("direction") or "Sideways")
        confidence = int(_f(payload.get("confidence"), 0.5) * 100)
        return {
            "quick_take": f"{symbol}: {direction} bias with {confidence}% confidence from trend signals.",
            "explain_like_15": (
                "This is like checking if a football team has momentum. "
                "If recent games are better than older games, trend looks stronger."
            ),
            "portfolio_link": "Use this forecast as one clue only; combine it with risk size and headline checks.",
            "next_steps": [
                "Check one supporting news headline before taking any paper trade.",
                "Decide your stop level before entering.",
                "Keep position size small when confidence is below 70%.",
            ],
            "source": reason,
            "generated_at": _now_iso(),
            "model": self.model if self._enabled else "rule-based",
        }

    def _normalize_forecast(self, raw: dict[str, Any], fallback: dict[str, Any]) -> dict[str, Any]:
        steps = raw.get("next_steps")
        if not isinstance(steps, list):
            steps = fallback["next_steps"]
        else:
            steps = [str(item).strip() for item in steps if str(item).strip()][:4] or fallback["next_steps"]
        return {
            "quick_take": str(raw.get("quick_take") or fallback["quick_take"]).strip(),
            "explain_like_15": str(raw.get("explain_like_15") or fallback["explain_like_15"]).strip(),
            "portfolio_link": str(raw.get("portfolio_link") or fallback["portfolio_link"]).strip(),
            "next_steps": steps,
            "source": "nvidia_llm",
            "generated_at": _now_iso(),
            "model": self.model,
        }

    def forecast_explainer(self, uid: str, market: str, symbol: str, payload: dict[str, Any]) -> dict[str, Any]:
        fallback = self._forecast_fallback(symbol=symbol, payload=payload, reason="rule_based")
        system = (
            "You are a paper-trading coach. Respond as strict JSON only. "
            "Keep explanations clear for a 15-year-old."
        )
        user = (
            "Return JSON with keys: quick_take, explain_like_15, portfolio_link, next_steps (3-4 bullets). "
            f"Symbol: {symbol}. Snapshot:\n{json.dumps(payload, ensure_ascii=True)}"
        )
        messages = [{"role": "system", "content": system}, {"role": "user", "content": user}]
        return self._llm_or_fallback(
            cache_key=f"forecast:{uid}:{market}:{symbol}",
            messages=messages,
            fallback=fallback,
            normalizer=self._normalize_forecast,
            max_tokens=900,
        )

    def _quote_signal_fallback(
        self,
        symbol: str,
        market: str,
        payload: dict[str, Any],
        reason: str = "rule_based",
    ) -> dict[str, Any]:
        quote = payload.get("quote") or {}
        forecast = payload.get("forecast") or {}
        risk = payload.get("risk") or {}
        market_mood = payload.get("market_mood") or {}
        news = payload.get("news") or []
        close_prices_raw = payload.get("close_prices") or []

        change_pct = _f(quote.get("change_pct"))
        forecast_direction = str(forecast.get("direction") or "Sideways").strip().title()
        forecast_conf_raw = _f(forecast.get("confidence"), 0.55)
        forecast_conf = int(round(forecast_conf_raw * 100)) if forecast_conf_raw <= 1 else int(round(forecast_conf_raw))
        forecast_conf = _score_1_to_100(forecast_conf, default=55)
        risk_score = _score_1_to_100(risk.get("risk_score"), default=50)
        mood_score = _score_1_to_100(market_mood.get("score"), default=50)

        close_prices: list[float] = []
        if isinstance(close_prices_raw, list):
            for value in close_prices_raw:
                try:
                    close_prices.append(float(value))
                except (TypeError, ValueError):
                    continue

        momentum_pct = 0.0
        if len(close_prices) >= 21 and close_prices[-21] != 0:
            momentum_pct = ((close_prices[-1] - close_prices[-21]) / close_prices[-21]) * 100
        elif len(close_prices) >= 6 and close_prices[-6] != 0:
            momentum_pct = ((close_prices[-1] - close_prices[-6]) / close_prices[-6]) * 100
        elif change_pct:
            momentum_pct = change_pct * 2.0

        positive_terms = {
            "beat",
            "beats",
            "growth",
            "surge",
            "record",
            "strong",
            "upgrade",
            "buyback",
            "profit",
            "bullish",
            "outperform",
            "expands",
            "launch",
            "approval",
        }
        negative_terms = {
            "miss",
            "misses",
            "fall",
            "drop",
            "decline",
            "weak",
            "downgrade",
            "lawsuit",
            "probe",
            "recall",
            "layoff",
            "warning",
            "loss",
            "bearish",
        }
        titles: list[str] = []
        if isinstance(news, list):
            for row in news[:8]:
                if not isinstance(row, dict):
                    continue
                title = str(row.get("title") or "").strip()
                if title:
                    titles.append(title)
        sentiment_hits = 0
        for title in titles:
            lowered = title.lower()
            sentiment_hits += sum(1 for term in positive_terms if term in lowered)
            sentiment_hits -= sum(1 for term in negative_terms if term in lowered)
        news_component = _clamp(sentiment_hits * 3.0, -18.0, 18.0)
        if sentiment_hits >= 2:
            news_bias = "Positive"
        elif sentiment_hits <= -2:
            news_bias = "Negative"
        else:
            news_bias = "Neutral"

        if forecast_direction == "Up":
            forecast_component = _clamp((forecast_conf - 50) * 0.55 + 4.0, -20.0, 20.0)
        elif forecast_direction == "Down":
            forecast_component = _clamp(-((forecast_conf - 50) * 0.55 + 4.0), -20.0, 20.0)
        else:
            forecast_component = _clamp((forecast_conf - 50) * 0.08, -4.0, 4.0)

        risk_component = _clamp((risk_score - 50) * 0.30, -15.0, 15.0)
        mood_component = _clamp((mood_score - 50) * 0.20, -10.0, 10.0)
        momentum_component = _clamp(momentum_pct * 0.55, -14.0, 14.0)
        day_component = _clamp(change_pct * 0.70, -8.0, 8.0)

        buy_score = int(
            round(
                _clamp(
                    50.0
                    + forecast_component
                    + risk_component
                    + mood_component
                    + momentum_component
                    + day_component
                    + news_component,
                    1.0,
                    100.0,
                )
            )
        )
        if buy_score >= 67:
            action = "Buy"
        elif buy_score <= 38:
            action = "Sell"
        else:
            action = "Hold"

        confidence = int(round(_clamp(45 + abs(buy_score - 50) * 1.1 + min(len(titles), 6) * 2.5, 35, 97)))
        factors = [
            f"Trend signal: {forecast_direction} ({forecast_conf}/100 confidence).",
            f"Risk score: {risk_score}/100 and market mood: {mood_score}/100.",
            f"Headline tone: {news_bias.lower()} from recent news flow.",
            f"Price momentum: {momentum_pct:+.2f}% over recent sessions.",
        ]
        summary = (
            f"{action} bias for {symbol}. Buy score is {buy_score}/100 from trend, risk, market tone, "
            "and headline sentiment."
        )
        return {
            "action": action,
            "buy_score": buy_score,
            "confidence": confidence,
            "news_bias": news_bias,
            "summary": summary,
            "factors": factors,
            "disclaimer": "Educational signal for paper trading only, not financial advice.",
            "source": reason,
            "generated_at": _now_iso(),
            "model": self.model if self._enabled else "rule-based",
        }

    def _normalize_quote_signal(self, raw: dict[str, Any], fallback: dict[str, Any]) -> dict[str, Any]:
        action = str(raw.get("action") or raw.get("rating") or fallback["action"]).strip().title()
        if action not in {"Buy", "Hold", "Sell"}:
            action = fallback["action"]

        buy_score = _score_1_to_100(raw.get("buy_score") or raw.get("score"), default=int(fallback["buy_score"]))
        confidence = _score_1_to_100(raw.get("confidence"), default=int(fallback["confidence"]))
        news_bias = str(raw.get("news_bias") or fallback["news_bias"]).strip().title()
        if news_bias not in {"Positive", "Neutral", "Negative"}:
            news_bias = fallback["news_bias"]

        factors = raw.get("factors")
        if not isinstance(factors, list):
            factors = fallback["factors"]
        else:
            factors = [str(item).strip() for item in factors if str(item).strip()][:5] or fallback["factors"]

        summary = str(raw.get("summary") or fallback["summary"]).strip()
        if not summary:
            summary = fallback["summary"]

        return {
            "action": action,
            "buy_score": buy_score,
            "confidence": confidence,
            "news_bias": news_bias,
            "summary": summary,
            "factors": factors,
            "disclaimer": str(raw.get("disclaimer") or fallback["disclaimer"]).strip(),
            "source": "nvidia_llm",
            "generated_at": _now_iso(),
            "model": self.model,
        }

    def quote_signal(self, uid: str, market: str, symbol: str, payload: dict[str, Any]) -> dict[str, Any]:
        safe_news = []
        for row in (payload.get("news") or [])[:8]:
            if not isinstance(row, dict):
                continue
            safe_news.append(
                {
                    "title": str(row.get("title") or "")[:220],
                    "source": str(row.get("source") or "")[:80],
                    "published": str(row.get("published") or "")[:40],
                }
            )

        prompt_payload = {
            "symbol": symbol,
            "market": market,
            "quote": payload.get("quote") or {},
            "forecast": payload.get("forecast") or {},
            "risk": payload.get("risk") or {},
            "market_mood": payload.get("market_mood") or {},
            "close_prices": (payload.get("close_prices") or [])[-120:],
            "news": safe_news,
        }
        fallback = self._quote_signal_fallback(symbol=symbol, market=market, payload=prompt_payload, reason="rule_based")
        system = (
            "You are a disciplined paper-trading coach. "
            "Respond in strict JSON only with no markdown."
        )
        user = (
            "Return JSON with keys: action (Buy|Hold|Sell), buy_score (1-100), confidence (1-100), "
            "news_bias (Positive|Neutral|Negative), summary (one short sentence), "
            "factors (array of 3-5 short bullets), disclaimer (one sentence).\n"
            f"Snapshot:\n{json.dumps(prompt_payload, ensure_ascii=True)}"
        )
        messages = [{"role": "system", "content": system}, {"role": "user", "content": user}]
        return self._llm_or_fallback(
            cache_key=f"quote-signal:{uid}:{market}:{symbol}:{hash(json.dumps(prompt_payload, sort_keys=True, default=str))}",
            messages=messages,
            fallback=fallback,
            normalizer=self._normalize_quote_signal,
            max_tokens=800,
        )

    def _tool_tip_fallback(self, topic: str, payload: dict[str, Any], reason: str = "rule_based") -> dict[str, Any]:
        summary = json.dumps(payload, ensure_ascii=True)[:220]
        return {
            "title": f"{topic.title()} Coach Tip",
            "explain_like_15": "Treat this as a practice signal, not a guarantee. Learn from consistency over many trades.",
            "steps": [
                "Write your reason before acting.",
                "Set your risk first, then place the paper trade.",
                "Review outcome and journal what you learned.",
            ],
            "context": summary,
            "source": reason,
            "generated_at": _now_iso(),
            "model": self.model if self._enabled else "rule-based",
        }

    def _normalize_tool_tip(self, raw: dict[str, Any], fallback: dict[str, Any]) -> dict[str, Any]:
        steps = raw.get("steps")
        if not isinstance(steps, list):
            steps = fallback["steps"]
        else:
            steps = [str(item).strip() for item in steps if str(item).strip()][:4] or fallback["steps"]
        return {
            "title": str(raw.get("title") or fallback["title"]).strip(),
            "explain_like_15": str(raw.get("explain_like_15") or fallback["explain_like_15"]).strip(),
            "steps": steps,
            "context": str(raw.get("context") or fallback["context"]).strip(),
            "source": "nvidia_llm",
            "generated_at": _now_iso(),
            "model": self.model,
        }

    def tool_tip(self, uid: str, market: str, topic: str, payload: dict[str, Any]) -> dict[str, Any]:
        fallback = self._tool_tip_fallback(topic=topic, payload=payload, reason="rule_based")
        system = "You are a concise trading tutor. Respond only with JSON."
        user = (
            "Return JSON with keys: title, explain_like_15, steps (3 short bullets), context. "
            f"Topic: {topic}. Market: {market}. Data: {json.dumps(payload, ensure_ascii=True)}"
        )
        messages = [{"role": "system", "content": system}, {"role": "user", "content": user}]
        return self._llm_or_fallback(
            cache_key=f"tip:{uid}:{market}:{topic}:{hash(json.dumps(payload, sort_keys=True, default=str))}",
            messages=messages,
            fallback=fallback,
            normalizer=self._normalize_tool_tip,
            max_tokens=700,
        )

    def _chat_fallback(self, market: str, message: str) -> dict[str, Any]:
        prompt = message.strip() or "your last question"
        return {
            "reply": (
                f"I can help with {market} paper trading, risk, and portfolio learning. "
                f"For now, start with this: restate `{prompt}` as a simple plan with entry, stop, and exit rules."
            ),
            "source": "rule_based",
            "generated_at": _now_iso(),
            "model": self.model if self._enabled else "rule-based",
        }

    def chat_reply(
        self,
        uid: str,
        market: str,
        message: str,
        history: list[dict[str, Any]] | None = None,
        context: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        text = str(message or "").strip()
        if not text:
            return self._chat_fallback(market, "your question")

        if not self._enabled:
            return self._chat_fallback(market, text)

        context = context or {}
        safe_history = []
        for row in (history or [])[-12:]:
            role = str(row.get("role") or "")
            content = str(row.get("content") or "").strip()
            if role in {"user", "assistant"} and content:
                safe_history.append({"role": role, "content": content[:1200]})

        system = (
            "You are StockSight AI Coach. Be clear, practical, and friendly. "
            "Assume the user is a beginner and explain like they are 15 when needed. "
            "Focus on paper trading safety and learning, not financial guarantees."
        )
        primer = (
            "Context JSON for this user session:\n"
            f"{json.dumps(context, ensure_ascii=True)[:10000]}"
        )
        messages: list[dict[str, str]] = [
            {"role": "system", "content": system},
            {"role": "system", "content": primer},
        ]
        messages.extend(safe_history)
        messages.append({"role": "user", "content": text})
        try:
            reply = self._stream_chat(messages, max_tokens=1100)
            cleaned = reply.strip()
            if not cleaned:
                return self._chat_fallback(market, text)
            return {
                "reply": cleaned,
                "source": "nvidia_llm",
                "generated_at": _now_iso(),
                "model": self.model,
            }
        except Exception:
            return self._chat_fallback(market, text)
