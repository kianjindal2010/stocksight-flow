from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from .firestore_repo import FirestoreRepository
from .market_data import MarketDataService


def _now_day() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def _f(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


class LearningEngine:
    def __init__(self, repo: FirestoreRepository, market_data: MarketDataService) -> None:
        self.repo = repo
        self.market_data = market_data

    def _refresh_portfolio_prices(self, uid: str, market: str) -> dict[str, Any]:
        portfolio = self.repo.get_portfolio(uid, market)
        positions = portfolio.get("positions", [])
        if not positions:
            return portfolio
        symbols = [str(pos.get("symbol") or "").upper().strip() for pos in positions]
        symbols = [symbol for symbol in symbols if symbol]
        latest_prices: dict[str, float] = {}
        # For small portfolios, direct quotes stay accurate and simple.
        if len(symbols) <= 5:
            for symbol in symbols:
                try:
                    quote = self.market_data.quote(symbol, market)
                except Exception:
                    continue
                last_price = _f(quote.get("price"), 0.0)
                if last_price > 0:
                    latest_prices[symbol] = last_price
        else:
            latest_prices = self.market_data.batch_last_prices(symbols, market)
            if len(latest_prices) < len(symbols):
                for symbol in symbols:
                    if symbol in latest_prices:
                        continue
                    try:
                        quote = self.market_data.quote(symbol, market)
                    except Exception:
                        continue
                    last_price = _f(quote.get("price"), 0.0)
                    if last_price > 0:
                        latest_prices[symbol] = last_price
        if not latest_prices:
            return portfolio
        return self.repo.refresh_position_prices(uid, market, latest_prices)

    def dashboard(self, uid: str, market: str) -> dict[str, Any]:
        portfolio = self._refresh_portfolio_prices(uid, market)
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
            {
                "id": "market_basics",
                "title": "Market Basics",
                "duration": "45 min",
                "summary": "Understand how markets function and what ownership means.",
                "topics": ["what a stock is", "primary vs secondary market", "how exchanges match buyers and sellers"],
                "practice": "Track one stock and explain why its price changed today in plain language.",
            },
            {
                "id": "risk_return",
                "title": "Risk and Return",
                "duration": "40 min",
                "summary": "Learn why return potential and uncertainty move together.",
                "topics": ["volatility", "drawdown", "expected return", "risk-adjusted thinking"],
                "practice": "Compare two assets and note which has higher potential return and why.",
            },
            {
                "id": "diversification",
                "title": "Diversification",
                "duration": "45 min",
                "summary": "Reduce concentration risk by spreading exposure.",
                "topics": ["asset mix", "sector spread", "position correlation", "single-position risk"],
                "practice": "Review your portfolio and identify your top concentration risk.",
            },
            {
                "id": "order_types",
                "title": "Order Types",
                "duration": "35 min",
                "summary": "Use the right order type for execution and protection.",
                "topics": ["market order", "limit order", "stop-loss", "trailing stop basics"],
                "practice": "Draft one limit buy and one stop-loss plan for a paper trade.",
            },
            {
                "id": "position_sizing",
                "title": "Position Sizing",
                "duration": "40 min",
                "summary": "Control downside by choosing smart trade size.",
                "topics": ["risk per trade", "capital allocation", "max loss rules", "sizing formulas"],
                "practice": "Set a max risk-per-trade percentage and calculate position size for one symbol.",
            },
            {
                "id": "technical_basics",
                "title": "Technical Basics",
                "duration": "50 min",
                "summary": "Read simple chart structure without overcomplication.",
                "topics": ["trend direction", "support/resistance", "volume context", "price structure"],
                "practice": "Mark trend and key levels on one chart and write a one-line thesis.",
            },
            {
                "id": "fundamental_basics",
                "title": "Fundamental Basics",
                "duration": "55 min",
                "summary": "Evaluate business quality with beginner-friendly fundamentals.",
                "topics": ["revenue and earnings", "profit margins", "debt basics", "valuation awareness"],
                "practice": "Pick one company and summarize its latest earnings story.",
            },
            {
                "id": "portfolio_construction",
                "title": "Portfolio Construction",
                "duration": "50 min",
                "summary": "Build a balanced portfolio aligned with your risk profile.",
                "topics": ["core-satellite structure", "cash allocation", "rebalancing", "exposure limits"],
                "practice": "Create a target portfolio mix and compare it with your current holdings.",
            },
            {
                "id": "behavioral_finance",
                "title": "Behavioral Finance",
                "duration": "40 min",
                "summary": "Recognize emotional biases that hurt performance.",
                "topics": ["panic selling", "FOMO", "revenge trading", "confirmation bias"],
                "practice": "Review your last 3 trades and note one emotional trigger to avoid.",
            },
            {
                "id": "trading_plan",
                "title": "Trading Plan",
                "duration": "45 min",
                "summary": "Define entry, risk, and exit before clicking buy.",
                "topics": ["entry criteria", "exit criteria", "invalidations", "trade checklist discipline"],
                "practice": "Write a complete mini trading plan for one setup.",
            },
            {
                "id": "trade_journaling",
                "title": "Trade Journaling",
                "duration": "35 min",
                "summary": "Turn each trade into a learning loop.",
                "topics": ["pre-trade thesis", "post-trade review", "mistake tagging", "pattern tracking"],
                "practice": "Complete a full journal entry for your latest paper trade.",
            },
            {
                "id": "performance_review",
                "title": "Performance Review",
                "duration": "45 min",
                "summary": "Measure what matters and improve systematically.",
                "topics": ["win rate vs expectancy", "average gain/loss", "drawdown control", "process metrics"],
                "practice": "Review your last 10 trades and identify one repeatable improvement.",
            },
            {
                "id": "etf_and_funds",
                "title": "ETFs and Funds",
                "duration": "40 min",
                "summary": "Use diversified funds intelligently in portfolio design.",
                "topics": ["index ETFs", "expense ratio", "tracking difference", "fund selection basics"],
                "practice": "Compare two ETFs and justify which one better fits your goal.",
            },
            {
                "id": "macro_and_rates",
                "title": "Macro and Interest Rates",
                "duration": "50 min",
                "summary": "See how inflation and rates influence asset prices.",
                "topics": ["inflation impact", "interest rate cycles", "liquidity", "risk-on vs risk-off"],
                "practice": "Write how today's macro trend could affect one holding.",
            },
            {
                "id": "earnings_and_news",
                "title": "Earnings and News Reactions",
                "duration": "50 min",
                "summary": "Interpret market reactions to company events.",
                "topics": ["earnings beats/misses", "guidance changes", "event volatility", "headline quality"],
                "practice": "Analyze one earnings move: what happened and what mattered most.",
            },
            {
                "id": "sector_rotation",
                "title": "Sector Rotation",
                "duration": "40 min",
                "summary": "Understand why leadership shifts across sectors.",
                "topics": ["cyclical vs defensive sectors", "market regimes", "relative strength", "allocation tilt"],
                "practice": "Identify one strong and one weak sector this week and why.",
            },
            {
                "id": "risk_lab_practice",
                "title": "Risk Lab Practice",
                "duration": "35 min",
                "summary": "Use volatility and drawdown tools to stress-test decisions.",
                "topics": ["risk score interpretation", "scenario checks", "downside planning", "exposure control"],
                "practice": "Run a downside scenario for one position and document your response plan.",
            },
            {
                "id": "scenario_simulation",
                "title": "Scenario Simulation",
                "duration": "35 min",
                "summary": "Test portfolio resilience under different market moves.",
                "topics": ["market shock modeling", "cash buffer logic", "recovery assumptions", "decision trees"],
                "practice": "Simulate a -5% market move and list your top two adjustments.",
            },
            {
                "id": "long_term_investing",
                "title": "Long-Term Investing",
                "duration": "45 min",
                "summary": "Build sustainable wealth habits beyond short-term trades.",
                "topics": ["compounding", "SIP discipline", "inflation-adjusted goals", "time horizon planning"],
                "practice": "Create a simple monthly investing routine and stick to it for 4 weeks.",
            },
            {
                "id": "capstone_review",
                "title": "Capstone Review",
                "duration": "60 min",
                "summary": "Combine all modules into one coherent investing process.",
                "topics": ["portfolio audit", "rulebook refinement", "risk checklist", "next 30-day action plan"],
                "practice": "Submit your personal investing playbook: rules, goals, and risk limits.",
            },
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
