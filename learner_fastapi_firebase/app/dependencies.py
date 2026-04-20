from __future__ import annotations

from typing import Any

from fastapi import Depends, HTTPException, Request, status

from .services.firestore_repo import FirestoreRepository


def get_repository(request: Request) -> FirestoreRepository:
    repo = getattr(request.app.state, "repo", None)
    if repo is None:
        raise HTTPException(status_code=500, detail="Repository is not initialized")
    return repo


def get_optional_user(request: Request) -> dict[str, Any] | None:
    return getattr(request.state, "current_user", None)


def get_current_user(user: dict[str, Any] | None = Depends(get_optional_user)) -> dict[str, Any]:
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required",
        )
    return user


def current_uid(user: dict[str, Any] = Depends(get_current_user)) -> str:
    uid = user.get("uid")
    if not uid:
        raise HTTPException(status_code=401, detail="Invalid auth token")
    return uid
