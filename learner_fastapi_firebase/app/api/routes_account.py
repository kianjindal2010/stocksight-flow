from __future__ import annotations

from fastapi import APIRouter, Depends

from ..dependencies import current_uid, get_repository
from ..schemas.account import NotificationUpdateRequest, PreferencesUpdateRequest, ProfileUpdateRequest


router = APIRouter(prefix="/api/account", tags=["account"])


@router.get("/profile")
def get_profile(uid: str = Depends(current_uid), repo=Depends(get_repository)):
    return repo.get_profile(uid)


@router.put("/profile")
def update_profile(payload: ProfileUpdateRequest, uid: str = Depends(current_uid), repo=Depends(get_repository)):
    return repo.update_profile(uid, payload.model_dump(exclude_none=True))


@router.get("/preferences")
def get_preferences(uid: str = Depends(current_uid), repo=Depends(get_repository)):
    return repo.get_preferences(uid)


@router.put("/preferences")
def update_preferences(payload: PreferencesUpdateRequest, uid: str = Depends(current_uid), repo=Depends(get_repository)):
    return repo.update_preferences(uid, payload.model_dump(exclude_none=True))


@router.put("/notifications")
def update_notifications(
    payload: NotificationUpdateRequest,
    uid: str = Depends(current_uid),
    repo=Depends(get_repository),
):
    return repo.update_notifications(uid, payload.model_dump(exclude_none=True))


@router.get("/saved-filters")
def get_saved_filters(uid: str = Depends(current_uid), repo=Depends(get_repository)):
    return {"saved_filters": repo.get_saved_filters(uid)}


@router.put("/saved-filters")
def update_saved_filters(payload: dict, uid: str = Depends(current_uid), repo=Depends(get_repository)):
    filters = payload.get("saved_filters") if isinstance(payload, dict) else None
    if not isinstance(filters, list):
        filters = []
    return {"saved_filters": repo.set_saved_filters(uid, filters)}
