from __future__ import annotations

import base64
import json
import logging
from typing import Any

import firebase_admin
import requests
from firebase_admin import auth, credentials, firestore

from .config import Settings


logger = logging.getLogger(__name__)


class FirebaseAuthError(RuntimeError):
    pass


def initialize_firebase(settings: Settings) -> None:
    if settings.firebase_use_memory:
        logger.info("Firebase memory mode enabled; skipping Admin SDK initialization.")
        return

    if firebase_admin._apps:
        return

    if settings.firebase_credentials_path:
        cred = credentials.Certificate(settings.firebase_credentials_path)
        firebase_admin.initialize_app(cred, {"projectId": settings.firebase_project_id or None})
        return

    if settings.firebase_service_account_json_b64:
        payload = base64.b64decode(settings.firebase_service_account_json_b64).decode("utf-8")
        cert_data = json.loads(payload)
        cred = credentials.Certificate(cert_data)
        firebase_admin.initialize_app(cred, {"projectId": settings.firebase_project_id or None})
        return

    if settings.firebase_service_account_json:
        cert_data = json.loads(settings.firebase_service_account_json)
        cred = credentials.Certificate(cert_data)
        firebase_admin.initialize_app(cred, {"projectId": settings.firebase_project_id or None})
        return

    firebase_admin.initialize_app(options={"projectId": settings.firebase_project_id or None})


def get_firestore_client(settings: Settings):
    if settings.firebase_use_memory:
        return None
    try:
        return firestore.client()
    except Exception as exc:
        logger.warning(
            "Firestore client initialization failed; falling back to in-memory repository. "
            "Configure FIREBASE_CREDENTIALS_PATH, FIREBASE_SERVICE_ACCOUNT_JSON_B64, "
            "or GOOGLE_APPLICATION_CREDENTIALS for real Firestore. "
            "error=%s",
            exc,
        )
        return None


def verify_id_token(id_token: str) -> dict[str, Any]:
    return auth.verify_id_token(id_token, check_revoked=False)


def _identity_toolkit_url(path: str, api_key: str) -> str:
    return f"https://identitytoolkit.googleapis.com/v1/{path}?key={api_key}"


def identity_signup(api_key: str, email: str, password: str, display_name: str | None = None) -> dict[str, Any]:
    if not api_key:
        raise FirebaseAuthError("Firebase web API key is not configured.")
    payload: dict[str, Any] = {
        "email": email,
        "password": password,
        "returnSecureToken": True,
    }
    if display_name:
        payload["displayName"] = display_name
    resp = requests.post(_identity_toolkit_url("accounts:signUp", api_key), json=payload, timeout=12)
    data = resp.json()
    if resp.status_code >= 400:
        raise FirebaseAuthError(data.get("error", {}).get("message", "Signup failed"))
    return data


def identity_signin(api_key: str, email: str, password: str) -> dict[str, Any]:
    if not api_key:
        raise FirebaseAuthError("Firebase web API key is not configured.")
    payload = {"email": email, "password": password, "returnSecureToken": True}
    resp = requests.post(
        _identity_toolkit_url("accounts:signInWithPassword", api_key),
        json=payload,
        timeout=12,
    )
    data = resp.json()
    if resp.status_code >= 400:
        raise FirebaseAuthError(data.get("error", {}).get("message", "Login failed"))
    return data


def send_reset_email(api_key: str, email: str) -> dict[str, Any]:
    if not api_key:
        raise FirebaseAuthError("Firebase web API key is not configured.")
    payload = {"requestType": "PASSWORD_RESET", "email": email}
    resp = requests.post(_identity_toolkit_url("accounts:sendOobCode", api_key), json=payload, timeout=12)
    data = resp.json()
    if resp.status_code >= 400:
        raise FirebaseAuthError(data.get("error", {}).get("message", "Password reset request failed"))
    return data


def send_verification_email(api_key: str, id_token: str) -> dict[str, Any]:
    if not api_key:
        raise FirebaseAuthError("Firebase web API key is not configured.")
    payload = {"requestType": "VERIFY_EMAIL", "idToken": id_token}
    resp = requests.post(_identity_toolkit_url("accounts:sendOobCode", api_key), json=payload, timeout=12)
    data = resp.json()
    if resp.status_code >= 400:
        raise FirebaseAuthError(data.get("error", {}).get("message", "Verification request failed"))
    return data
