from __future__ import annotations

import hashlib
import logging
import secrets
import time

from fastapi import APIRouter, Depends, HTTPException, Request, Response

from ..dependencies import get_optional_user
from ..firebase import (
    FirebaseAuthError,
    identity_signin,
    identity_signup,
    send_reset_email,
    send_verification_email,
    verify_id_token,
    verify_id_token_with_api_key,
)
from ..schemas.auth import (
    AuthResponse,
    ExternalGoogleConsumeRequest,
    ExternalGoogleLoginRequest,
    GoogleLoginRequest,
    LoginRequest,
    PasswordResetConfirmRequest,
    PasswordResetRequest,
    SignupRequest,
)
from ..appwrite import (
    AppwriteAuthError,
    complete_password_recovery as appwrite_complete_password_recovery,
    create_account as appwrite_create_account,
    create_email_session as appwrite_create_email_session,
    create_password_recovery as appwrite_create_password_recovery,
)


router = APIRouter(prefix="/api/auth", tags=["auth"])
EXTERNAL_AUTH_TTL_SECONDS = 300
logger = logging.getLogger(__name__)


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
        max_age=60 * 60 * 24 * 30,
    )


def _remember_appwrite_session(request: Request, token: str) -> None:
    if request.app.state.settings.appwrite_project_id and token:
        request.app.state.desktop_session_store.save(token)


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
    if settings.appwrite_project_id:
        try:
            created = appwrite_create_account(settings, payload.email, payload.password, payload.display_name)
            _, session = appwrite_create_email_session(settings, payload.email, payload.password)
            uid = str(created.get("$id") or "")
            repo.set_session(uid, session)
            repo.ensure_user(uid, email=payload.email, display_name=payload.display_name)
            repo.update_profile(uid, {"workspace_name": payload.workspace_name})
            _auth_cookie(response, session)
            _remember_appwrite_session(request, session)
            return AuthResponse(uid=uid, email=payload.email, id_token=session, expires_in=3600)
        except AppwriteAuthError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
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
    if settings.appwrite_project_id:
        try:
            session_data, session = appwrite_create_email_session(settings, payload.email, payload.password)
            uid = str(session_data.get("userId") or "")
            if not uid:
                raise AppwriteAuthError("Appwrite did not return an account for this session. Please try again.")
            repo.set_session(uid, session)
            repo.ensure_user(uid, email=payload.email)
            _auth_cookie(response, session)
            _remember_appwrite_session(request, session)
            return AuthResponse(uid=uid, email=payload.email, id_token=session, expires_in=3600)
        except AppwriteAuthError as exc:
            raise HTTPException(status_code=401, detail=str(exc)) from exc
        except Exception as exc:
            logger.exception("Email/password sign-in could not finish")
            raise HTTPException(
                status_code=503,
                detail="StockSight could not finish setting up this session. Please try again.",
            ) from exc
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
        try:
            decoded = verify_id_token(payload.id_token)
        except Exception:
            decoded = verify_id_token_with_api_key(payload.id_token, settings.firebase_web_api_key)
    except Exception as exc:
        raise HTTPException(status_code=401, detail=f"Invalid Google/Firebase token: {exc}") from exc
    uid = str(decoded.get("uid") or decoded.get("user_id") or "")
    email = str(decoded.get("email") or "")
    name = str(decoded.get("name") or "")
    repo.ensure_user(uid, email=email, display_name=name)
    _auth_cookie(response, payload.id_token)
    return AuthResponse(uid=uid, email=email, id_token=payload.id_token)


@router.post("/external/start")
def start_external_google(request: Request):
    state = secrets.token_urlsafe(32)
    request.app.state.external_google_sessions[state] = {
        "created_at": time.monotonic(),
        "status": "pending",
    }
    return {"state": state}


@router.post("/external/complete")
def complete_external_google(payload: ExternalGoogleLoginRequest, request: Request):
    session = request.app.state.external_google_sessions.get(payload.state)
    if not session or time.monotonic() - session["created_at"] > EXTERNAL_AUTH_TTL_SECONDS:
        request.app.state.external_google_sessions.pop(payload.state, None)
        raise HTTPException(status_code=400, detail="This Google sign-in request has expired.")
    if request.app.state.settings.firebase_use_memory:
        session["id_token"] = _dev_token(_dev_uid("google-dev@example.com"), "google-dev@example.com")
    else:
        try:
            try:
                verify_id_token(payload.id_token)
            except Exception:
                verify_id_token_with_api_key(payload.id_token, request.app.state.settings.firebase_web_api_key)
        except Exception as exc:
            session["status"] = "error"
            session["error"] = f"Invalid Google/Firebase token: {exc}"
            raise HTTPException(status_code=401, detail=session["error"]) from exc
        session["id_token"] = payload.id_token
    session["status"] = "ready"
    return {"status": "ready"}


@router.get("/external/status")
def external_google_status(state: str, request: Request):
    session = request.app.state.external_google_sessions.get(state)
    if not session or time.monotonic() - session["created_at"] > EXTERNAL_AUTH_TTL_SECONDS:
        request.app.state.external_google_sessions.pop(state, None)
        return {"status": "expired"}
    return {"status": session["status"], "error": session.get("error", "")}


@router.post("/external/consume")
def consume_external_google(payload: ExternalGoogleConsumeRequest, request: Request, response: Response):
    session = request.app.state.external_google_sessions.get(payload.state)
    if not session or session.get("status") != "ready":
        raise HTTPException(status_code=409, detail="Google sign-in is not ready yet.")
    settings = request.app.state.settings
    if settings.appwrite_project_id:
        token = str(session.get("appwrite_session") or "")
        account = session.get("account") or {}
        if not token or not account.get("uid"):
            raise HTTPException(status_code=409, detail="Google sign-in is not ready yet.")
        request.app.state.external_google_sessions.pop(payload.state, None)
        uid = str(account["uid"])
        email = str(account.get("email") or "")
        name = str(account.get("name") or "")
        request.app.state.repo.set_session(uid, token)
        request.app.state.repo.ensure_user(uid, email=email, display_name=name)
        _auth_cookie(response, token)
        _remember_appwrite_session(request, token)
        return AuthResponse(uid=uid, email=email, id_token=token, expires_in=3600)
    token = str(session.get("id_token") or "")
    request.app.state.external_google_sessions.pop(payload.state, None)
    return google_login(GoogleLoginRequest(id_token=token), request, response)


@router.post("/logout")
def logout(request: Request, response: Response):
    request.app.state.desktop_session_store.clear()
    response.delete_cookie("ss_id_token")
    return {"status": "ok"}


@router.get("/session")
def session(user=Depends(get_optional_user)):
    if not user:
        return {"authenticated": False}
    return {"authenticated": True, "uid": user.get("uid"), "email": user.get("email")}


@router.post("/password-reset")
def request_password_reset(payload: PasswordResetRequest, request: Request):
    settings = request.app.state.settings
    if settings.appwrite_project_id:
        reset_url = f"http://{settings.app_host}:{settings.app_port}/auth/password-reset"
        try:
            appwrite_create_password_recovery(settings, str(payload.email), reset_url)
        except AppwriteAuthError as exc:
            # Return a deliberately generic response to avoid confirming which
            # accounts exist, while logging the provider failure for support.
            logger.warning("Password recovery request rejected by Appwrite: %s", exc)
        return {"status": "ok", "message": "If that email has a StockSight password, a reset link is on its way."}
    try:
        send_reset_email(settings.firebase_web_api_key, str(payload.email))
    except FirebaseAuthError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"status": "ok"}


@router.post("/password-reset/confirm")
def confirm_password_reset(payload: PasswordResetConfirmRequest, request: Request):
    settings = request.app.state.settings
    if not settings.appwrite_project_id:
        raise HTTPException(status_code=400, detail="Password reset is not available in this configuration.")
    try:
        appwrite_complete_password_recovery(settings, payload.user_id, payload.secret, payload.password)
    except AppwriteAuthError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"status": "ok"}
