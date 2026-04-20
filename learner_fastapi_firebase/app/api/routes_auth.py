from __future__ import annotations

import hashlib

from fastapi import APIRouter, Depends, HTTPException, Request, Response

from ..dependencies import get_optional_user
from ..firebase import (
    FirebaseAuthError,
    identity_signin,
    identity_signup,
    send_reset_email,
    send_verification_email,
    verify_id_token,
)
from ..schemas.auth import AuthResponse, GoogleLoginRequest, LoginRequest, SignupRequest


router = APIRouter(prefix="/api/auth", tags=["auth"])


def _dev_uid(email: str) -> str:
    digest = hashlib.sha1(email.strip().lower().encode("utf-8")).hexdigest()[:16]
    return f"dev_{digest}"


def _dev_token(uid: str, email: str) -> str:
    return f"dev-token:{uid}:{email}"


def _auth_cookie(response: Response, token: str) -> None:
    response.set_cookie(
        key="ss_id_token",
        value=token,
        httponly=True,
        secure=False,
        samesite="lax",
        max_age=3600,
    )


@router.post("/signup", response_model=AuthResponse)
def signup(payload: SignupRequest, request: Request, response: Response):
    settings = request.app.state.settings
    repo = request.app.state.repo
    if settings.firebase_use_memory:
        uid = _dev_uid(str(payload.email))
        token = _dev_token(uid, str(payload.email))
        repo.ensure_user(uid, email=payload.email, display_name=payload.display_name)
        repo.update_profile(uid, {"workspace_name": payload.workspace_name})
        _auth_cookie(response, token)
        return AuthResponse(uid=uid, email=str(payload.email), id_token=token, refresh_token="dev-refresh", expires_in=3600)
    try:
        data = identity_signup(
            settings.firebase_web_api_key,
            payload.email,
            payload.password,
            display_name=payload.display_name,
        )
        uid = str(data.get("localId") or "")
        token = str(data.get("idToken") or "")
        if token:
            try:
                send_verification_email(settings.firebase_web_api_key, token)
            except FirebaseAuthError:
                pass
        repo.ensure_user(uid, email=payload.email, display_name=payload.display_name)
        repo.update_profile(uid, {"workspace_name": payload.workspace_name})
        _auth_cookie(response, token)
        return AuthResponse(
            uid=uid,
            email=payload.email,
            id_token=token,
            refresh_token=data.get("refreshToken"),
            expires_in=int(data.get("expiresIn", 3600)),
        )
    except FirebaseAuthError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/login", response_model=AuthResponse)
def login(payload: LoginRequest, request: Request, response: Response):
    settings = request.app.state.settings
    repo = request.app.state.repo
    if settings.firebase_use_memory:
        uid = _dev_uid(str(payload.email))
        token = _dev_token(uid, str(payload.email))
        repo.ensure_user(uid, email=payload.email)
        _auth_cookie(response, token)
        return AuthResponse(uid=uid, email=str(payload.email), id_token=token, refresh_token="dev-refresh", expires_in=3600)
    try:
        data = identity_signin(settings.firebase_web_api_key, payload.email, payload.password)
        uid = str(data.get("localId") or "")
        token = str(data.get("idToken") or "")
        repo.ensure_user(uid, email=payload.email)
        _auth_cookie(response, token)
        return AuthResponse(
            uid=uid,
            email=payload.email,
            id_token=token,
            refresh_token=data.get("refreshToken"),
            expires_in=int(data.get("expiresIn", 3600)),
        )
    except FirebaseAuthError as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc


@router.post("/google", response_model=AuthResponse)
def google_login(payload: GoogleLoginRequest, request: Request, response: Response):
    settings = request.app.state.settings
    repo = request.app.state.repo
    if settings.firebase_use_memory:
        email = "google-dev@example.com"
        uid = _dev_uid(email)
        token = _dev_token(uid, email)
        repo.ensure_user(uid, email=email, display_name="Google Dev User")
        _auth_cookie(response, token)
        return AuthResponse(uid=uid, email=email, id_token=token, refresh_token="dev-refresh", expires_in=3600)
    try:
        decoded = verify_id_token(payload.id_token)
    except Exception as exc:
        raise HTTPException(status_code=401, detail="Invalid Google/Firebase token") from exc
    uid = str(decoded.get("uid") or decoded.get("user_id") or "")
    email = str(decoded.get("email") or "")
    name = str(decoded.get("name") or "")
    repo.ensure_user(uid, email=email, display_name=name)
    _auth_cookie(response, payload.id_token)
    return AuthResponse(uid=uid, email=email, id_token=payload.id_token)


@router.post("/logout")
def logout(response: Response):
    response.delete_cookie("ss_id_token")
    return {"status": "ok"}


@router.get("/session")
def session(user=Depends(get_optional_user)):
    if not user:
        return {"authenticated": False}
    return {"authenticated": True, "uid": user.get("uid"), "email": user.get("email")}


@router.post("/password-reset")
def request_password_reset(email: str, request: Request):
    settings = request.app.state.settings
    try:
        send_reset_email(settings.firebase_web_api_key, email)
    except FirebaseAuthError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"status": "ok"}
