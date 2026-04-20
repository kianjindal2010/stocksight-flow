from __future__ import annotations

from pydantic import BaseModel


class ChecklistRequest(BaseModel):
    thesis: str = ""
    risk_level: str = "medium"
    stop_loss_awareness: bool = False
    time_horizon: str = ""
    buy_reason: str = ""
    trade_type: str = "speculative"


class ScenarioRequest(BaseModel):
    market_move_pct: float = 0.0
    add_cash: float = 0.0


class SipRequest(BaseModel):
    monthly_investment: float
    years: int
    annual_return_pct: float = 12.0
    inflation_pct: float = 5.0

