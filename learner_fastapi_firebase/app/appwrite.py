from __future__ import annotations

import uuid
from typing import Any

import requests

from .config import Settings


class AppwriteAuthError(RuntimeError):
    pass


class AppwriteReadOnlyError(AppwriteAuthError):
    pass


def _headers(settings: Settings, session: str = "") -> dict[str, str]:
    headers = {"X-Appwrite-Project": settings.appwrite_project_id, "Content-Type": "application/json"}
    if session:
        headers["X-Appwrite-Session"] = session
        # The Cloud endpoint accepts the session both through the server-SDK
        # header and its standard browser cookie. Supplying both keeps the
        # local desktop server compatible with either Appwrite transport.
        headers["Cookie"] = f"a_session_{settings.appwrite_project_id}={session}"
    return headers


def _error(response: requests.Response) -> AppwriteAuthError:
    try:
        payload = response.json()
    except ValueError:
        payload = {}
    error_type = str(payload.get("type") or "")
    detail = str(payload.get("message") or error_type or response.text or "")
    if error_type == "team_read_only":
        return AppwriteReadOnlyError(
            "StockSight accounts are temporarily unavailable because Appwrite has put the project in read-only mode."
        )

    # Appwrite deliberately uses the same response for an unknown address and
    # a wrong password. Keep that privacy property while giving people who
    # moved from Firebase a useful, safe next step.
    if error_type == "user_invalid_credentials":
        detail = (
            "The email or password is incorrect. If you used StockSight before "
            "the Appwrite move, reset your StockSight password below—old Firebase "
            "passwords were not transferred."
        )
    elif error_type == "user_password_pwned":
        detail = "Choose a different password. This password appears in a known data breach."
    return AppwriteAuthError(detail or "Appwrite could not complete the request.")


def create_account(settings: Settings, email: str, password: str, name: str = "") -> dict[str, Any]:
    response = requests.post(
        f"{settings.appwrite_endpoint}/account",
        headers=_headers(settings),
        json={"userId": uuid.uuid4().hex, "email": email, "password": password, "name": name},
        timeout=15,
    )
    if response.status_code >= 400:
        raise _error(response)
    return response.json()


def create_email_session(settings: Settings, email: str, password: str) -> tuple[dict[str, Any], str]:
    response = requests.post(
        f"{settings.appwrite_endpoint}/account/sessions/email",
        headers=_headers(settings),
        json={"email": email, "password": password},
        timeout=15,
    )
    if response.status_code >= 400:
        raise _error(response)
    payload = response.json()
    token = payload.get("secret", "")
    if not token:
        token = response.cookies.get(f"a_session_{settings.appwrite_project_id}", "")
    if not token:
        raise AppwriteAuthError("Appwrite did not return a usable session. Please try again.")
    return payload, token


def create_password_recovery(settings: Settings, email: str, url: str) -> None:
    response = requests.post(
        f"{settings.appwrite_endpoint}/account/recovery",
        headers=_headers(settings),
        json={"email": email, "url": url},
        timeout=15,
    )
    if response.status_code >= 400:
        raise _error(response)


def complete_password_recovery(settings: Settings, user_id: str, secret: str, password: str) -> None:
    response = requests.patch(
        f"{settings.appwrite_endpoint}/account/recovery",
        headers=_headers(settings),
        json={"userId": user_id, "secret": secret, "password": password},
        timeout=15,
    )
    if response.status_code >= 400:
        raise _error(response)


def get_account(settings: Settings, session: str) -> dict[str, Any]:
    response = requests.get(f"{settings.appwrite_endpoint}/account", headers=_headers(settings, session), timeout=15)
    if response.status_code >= 400:
        raise _error(response)
    account = response.json()
    return {"uid": account.get("$id", ""), "email": account.get("email", ""), "name": account.get("name", "")}


def create_oauth_token_url(settings: Settings, provider: str, success: str, failure: str) -> str:
    """Return Appwrite's provider URL while keeping project configuration local."""
    response = requests.get(
        f"{settings.appwrite_endpoint}/account/tokens/oauth2/{provider}",
        headers=_headers(settings),
        params={"success": success, "failure": failure},
        timeout=15,
        allow_redirects=False,
    )
    if response.status_code not in {301, 302, 303, 307, 308}:
        raise _error(response)
    url = response.headers.get("Location", "")
    if not url:
        raise AppwriteAuthError("Appwrite did not return a Google sign-in URL.")
    return url


def create_session_from_token(settings: Settings, user_id: str, secret: str) -> tuple[dict[str, Any], str]:
    response = requests.post(
        f"{settings.appwrite_endpoint}/account/sessions/token",
        headers=_headers(settings),
        json={"userId": user_id, "secret": secret},
        timeout=15,
    )
    if response.status_code >= 400:
        raise _error(response)
    payload = response.json()
    # Appwrite returns the usable browser session in Set-Cookie. The OAuth
    # token secret supplied to this endpoint is *not* the session credential,
    # so prefer the response cookie over any JSON field.
    session = str(response.cookies.get(f"a_session_{settings.appwrite_project_id}", "") or payload.get("secret") or "")
    if not session:
        raise AppwriteAuthError("Appwrite did not return a usable Google session.")
    return payload, session
