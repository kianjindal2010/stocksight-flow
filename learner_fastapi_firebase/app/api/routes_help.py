from __future__ import annotations

from fastapi import APIRouter, Depends

from ..dependencies import current_uid, get_repository


router = APIRouter(prefix="/api/help", tags=["help"])


@router.get("/onboarding")
def onboarding_steps():
    return {
        "steps": [
            {"id": "what_is_stock", "title": "What a stock is", "summary": "A stock is a small ownership share in a company."},
            {"id": "risk_basics", "title": "What risk means", "summary": "Risk is uncertainty in outcomes, including losses."},
            {"id": "diversification", "title": "Diversification", "summary": "Spreading investments reduces concentration risk."},
            {"id": "trade_flow", "title": "How a trade works", "summary": "Orders enter the market and execute at available prices."},
            {"id": "chart_basics", "title": "Reading basic charts", "summary": "Price and volume reveal trend and activity."},
            {"id": "paper_trading", "title": "Paper trading", "summary": "Practice with virtual cash before real-world decisions."},
        ]
    }


@router.get("/glossary")
def glossary():
    return {
        "terms": {
            "pnl": "Profit and loss: the money gained or lost from trades.",
            "volatility": "How much prices move up and down over time.",
            "beta": "How strongly a stock tends to move relative to the market.",
            "drawdown": "The drop from a recent peak to a later low.",
            "market_order": "An order to buy or sell immediately at current market price.",
            "limit_order": "An order that executes only at your selected price or better.",
            "diversification": "Spreading risk across multiple assets and sectors.",
        }
    }


@router.get("/tooltips")
def tooltips():
    return {
        "tooltips": [
            {"key": "portfolio_value", "text": "Your total account value: cash + holdings."},
            {"key": "realized_pnl", "text": "Profit/loss from closed trades only."},
            {"key": "unrealized_pnl", "text": "Profit/loss from open positions at current prices."},
            {"key": "risk_score", "text": "Simplified risk estimate from volatility and concentration."},
            {"key": "health_score", "text": "Beginner score for diversification, discipline, and consistency."},
        ]
    }


@router.get("/support")
def support(uid: str = Depends(current_uid), repo=Depends(get_repository)):
    profile = repo.ensure_user(uid)
    return {
        "support_center": "help@stocksight.example",
        "workspace": profile.get("profile", {}).get("workspace_name", "Trading Workspace"),
        "resources": [
            {"name": "Getting Started", "url": "/instructions"},
            {"name": "Learning Center", "url": "/api/learning/center"},
            {"name": "Glossary", "url": "/api/help/glossary"},
        ],
    }
