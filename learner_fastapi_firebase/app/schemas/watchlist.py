from __future__ import annotations

from pydantic import BaseModel, Field


class WatchlistCreateRequest(BaseModel):
    name: str = "My Watchlist"
    symbols: list[str] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)
    notes: str = ""
    group: str = "default"


class WatchlistUpdateRequest(BaseModel):
    name: str | None = None
    symbols: list[str] | None = None
    tags: list[str] | None = None
    notes: str | None = None
    group: str | None = None
