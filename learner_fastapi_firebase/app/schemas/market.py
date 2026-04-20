from __future__ import annotations

from pydantic import BaseModel


class MarketSelectRequest(BaseModel):
    market: str


class SearchQuery(BaseModel):
    q: str
    limit: int = 12

