from __future__ import annotations

from pydantic import BaseModel, Field


class ProfileUpdateRequest(BaseModel):
    display_name: str | None = None
    workspace_name: str | None = None
    language: str | None = None
    timezone: str | None = None


class PreferencesUpdateRequest(BaseModel):
    theme_mode: str | None = None
    theme_color: str | None = None
    layout_mode: str | None = None
    saved_filters: list[dict] | None = Field(default=None)


class NotificationUpdateRequest(BaseModel):
    email_alerts: bool | None = None
    in_app_alerts: bool | None = None
    learning_reminders: bool | None = None
