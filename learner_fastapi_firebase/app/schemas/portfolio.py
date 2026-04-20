from __future__ import annotations

from pydantic import BaseModel, Field


class TradeRequest(BaseModel):
    symbol: str
    quantity: int = Field(gt=0)
    order_type: str = "market"
    notes: str = ""
    checklist: dict | None = None


class TradeJournalUpdateRequest(BaseModel):
    thesis: str | None = None
    reason_for_entry: str | None = None
    reason_for_exit: str | None = None
    lessons_learned: str | None = None
    outcome_review: str | None = None

