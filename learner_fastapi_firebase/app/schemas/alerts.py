from __future__ import annotations

from pydantic import BaseModel


class AlertCreateRequest(BaseModel):
    type: str = "price"
    symbol: str = ""
    direction: str = "above"
    target: float | None = None
    message: str = ""

