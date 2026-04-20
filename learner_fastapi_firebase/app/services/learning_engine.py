from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from .firestore_repo import FirestoreRepository
from .market_data import MarketDataService


def _now_day() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


class LearningEngine:
    def __init__(self, repo: FirestoreRepository, market_data: MarketDataService) -> None:
        self.repo = repo
        self.market_data = market_data

    def dashboard(self, uid: str, market: str) -> dict[str, Any]:
        portfolio = self.repo.get_portfolio(uid, market)
        perf = self.repo.get_portfolio_performance(uid, market)
        progress = self.repo.get_learning_doc(uid, "progress", default={"completed_modules": 0, "total_modules": 20})
        completed = int(progress.get("completed_modules", 0))
        total = max(1, int(progress.get("total_modules", 20)))
        ratio = int((completed / total) * 100)
        next_step = progress.get("next_step") or "Complete your next concept check."
        return {
            "portfolio_value": portfolio["total_value"],
            "simple_return_pct": perf["return_total_pct"],
            "changed_today_pct": perf["return_today_pct"],
            "learning_progress_pct": ratio,
            "next_step": next_step,
        }

    def curriculum(self) -> list[dict[str, Any]]:
        return [
            {"id": "market_basics", "title": "Market Basics", "topics": ["what a stock is", "how exchanges work"]},
            {"id": "risk_return", "title": "Risk and Return", "topics": ["volatility", "drawdown", "expected return"]},
            {"id": "diversification", "title": "Diversification", "topics": ["concentration", "asset mix", "sector spread"]},
            {"id": "order_types", "title": "Order Types", "topics": ["market order", "limit order", "execution impact"]},
            {"id": "technical_basics", "title": "Technical Basics", "topics": ["trend", "support/resistance", "volume"]},
            {"id": "long_term", "title": "Long-Term Investing", "topics": ["compounding", "SIP", "inflation"]},
            {"id": "behavioral", "title": "Behavioral Finance", "topics": ["panic selling", "overtrading", "discipline"]},
            {"id": "funds_intro", "title": "ETFs and Mutual Funds", "topics": ["index funds", "expense ratio", "risk fit"]},
        ]

    def save_checklist(self, uid: str, payload: dict[str, Any]) -> dict[str, Any]:
        checklist = {
            "thesis": payload.get("thesis", ""),
            "risk_level": payload.get("risk_level", "medium"),
            "stop_loss_awareness": bool(payload.get("stop_loss_awareness", False)),
            "time_horizon": payload.get("time_horizon", ""),
            "buy_reason": payload.get("buy_reason", ""),
            "trade_type": payload.get("trade_type", "speculative"),
            "updated_at": _now_day(),
        }
        return self.repo.set_learning_doc(uid, "before_trade_checklist", checklist, merge=False)

    def weekly_summary(self, uid: str, market: str) -> dict[str, Any]:
        trades = self.repo.list_trades(uid, market=market)[:30]
        wins = [t for t in trades if float(t.get("realized_pnl", 0.0)) > 0]
        losses = [t for t in trades if float(t.get("realized_pnl", 0.0)) < 0]
        top_win = wins[0]["symbol"] if wins else "None yet"
        top_loss = losses[0]["symbol"] if losses else "None yet"
        concept = "Diversification and position sizing" if losses else "Consistency and trade journaling"
        return {
            "what_happened": f"{len(trades)} trades recorded this week.",
            "mistakes": [f"Large loss observed in {top_loss}" if losses else "No major mistake detected", "Review entries without clear thesis"],
            "good_decisions": [f"Disciplined exits in {top_win}" if wins else "Maintained paper-trading consistency"],
            "next_concept": concept,
        }

    def health_score(self, uid: str, market: str) -> dict[str, Any]:
        portfolio = self.repo.get_portfolio(uid, market)
        positions = portfolio.get("positions", [])
        total = float(portfolio.get("total_value", 0.0))
        concentration = 0.0
        if total > 0 and positions:
            concentration = max((float(p.get("market_value", 0.0)) / total) * 100 for p in positions)
        trades = self.repo.list_trades(uid, market=market)
        overtrading_flag = len(trades) > 15
        diversification = max(0, 100 - int(concentration))
        discipline = 55 if overtrading_flag else 80
        consistency = min(100, len(trades) * 5)
        risk = 70 if concentration < 40 else 45
        score = int((diversification + discipline + consistency + risk) / 4)
        return {
            "score": score,
            "components": {
                "diversification": diversification,
                "discipline": discipline,
                "consistency": consistency,
                "concentration": max(0, 100 - int(concentration)),
                "risk": risk,
            },
        }

    def explain_portfolio(self, uid: str, market: str) -> dict[str, Any]:
        p = self.repo.get_portfolio(uid, market)
        text = (
            f"Your portfolio is worth {p['total_value']:.2f}. "
            f"You have {p['cash']:.2f} in cash and {p['market_value']:.2f} invested. "
            f"Realized P&L is {p['realized_pnl']:.2f} and unrealized P&L is {p['unrealized_pnl']:.2f}. "
            "Think of this like your scorecard in a practice game: cash is your reserve, and holdings are your active plays."
        )
        return {"plain_english": text}

    def portfolio_move_why(self, uid: str, market: str) -> dict[str, Any]:
        mood = self.market_data.market_mood(market)
        news = self.market_data.market_news(market, limit=3)
        p = self.repo.get_portfolio(uid, market)
        points = [
            f"Market mood is {mood['classification']} with score {mood['score']}.",
            f"Portfolio has {len(p.get('positions', []))} active positions.",
            "Recent headlines can influence sector-level movement and portfolio valuation."
        ]
        return {"drivers": points, "headlines": news}

    def mistake_detection(self, uid: str, market: str) -> dict[str, Any]:
        trades = self.repo.list_trades(uid, market=market)
        mistakes = []
        if len(trades) > 20:
            mistakes.append("Overtrading: many trades in a short window.")
        if trades and sum(1 for t in trades if not t.get("notes")) > max(2, len(trades) // 2):
            mistakes.append("Lack of thesis: many trades have no reasoning note.")
        losses = [t for t in trades if float(t.get("realized_pnl", 0.0)) < 0]
        if len(losses) > len(trades) * 0.6 and trades:
            mistakes.append("Poor timing: loss ratio is high; reduce position size and improve entry criteria.")
        if not mistakes:
            mistakes.append("No major behavioral red flags detected.")
        return {"mistakes": mistakes}

