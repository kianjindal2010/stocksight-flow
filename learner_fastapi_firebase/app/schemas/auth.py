from __future__ import annotations

from pydantic import BaseModel, EmailStr, Field


class SignupRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=6)
    display_name: str = ""
    workspace_name: str = "Trading Workspace"


class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=6)


class GoogleLoginRequest(BaseModel):
    id_token: str


class ExternalGoogleLoginRequest(BaseModel):
    state: str
    id_token: str


class ExternalGoogleConsumeRequest(BaseModel):
    state: str


class PasswordResetRequest(BaseModel):
    email: EmailStr


class PasswordResetConfirmRequest(BaseModel):
    user_id: str = Field(min_length=1)
    secret: str = Field(min_length=1)
    password: str = Field(min_length=8)


class AuthResponse(BaseModel):
    uid: str
    email: str
    id_token: str | None = None
    refresh_token: str | None = None
    expires_in: int | None = None
