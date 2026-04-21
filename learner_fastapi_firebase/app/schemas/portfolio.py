from __future__ import annotations

from pydantic import BaseModel, Field
from pydantic import model_validator


class TradeRequest(BaseModel):
    symbol: str
    quantity: int = Field(gt=0)
    order_type: str = "market"
    notes: str = ""
    checklist: dict | None = None
    stop_loss_price: float | None = Field(default=None, gt=0)
    trailing_stop_percent: float | None = Field(default=None, gt=0)
    trailing_stop_amount: float | None = Field(default=None, gt=0)

    @model_validator(mode="after")
    def validate_trailing_stop(self) -> "TradeRequest":
        if self.trailing_stop_percent is not None and self.trailing_stop_amount is not None:
            raise ValueError("Provide either trailing_stop_percent or trailing_stop_amount, not both")
        return self


class TradeJournalUpdateRequest(BaseModel):
    thesis: str | None = None
    reason_for_entry: str | None = None
    reason_for_exit: str | None = None
    lessons_learned: str | None = None
    outcome_review: str | None = None
