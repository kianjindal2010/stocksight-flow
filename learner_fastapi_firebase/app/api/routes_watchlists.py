from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from ..dependencies import current_uid, get_repository
from ..schemas.watchlist import WatchlistCreateRequest, WatchlistUpdateRequest


router = APIRouter(prefix="/api/watchlists", tags=["watchlists"])


@router.get("")
def list_watchlists(uid: str = Depends(current_uid), repo=Depends(get_repository)):
    return {"watchlists": repo.list_watchlists(uid)}


@router.post("")
def create_watchlist(payload: WatchlistCreateRequest, uid: str = Depends(current_uid), repo=Depends(get_repository)):
    return repo.create_watchlist(uid, payload.model_dump())


@router.put("/{watchlist_id}")
def update_watchlist(
    watchlist_id: str,
    payload: WatchlistUpdateRequest,
    uid: str = Depends(current_uid),
    repo=Depends(get_repository),
):
    return repo.update_watchlist(uid, watchlist_id, payload.model_dump(exclude_none=True))


@router.delete("/{watchlist_id}")
def delete_watchlist(watchlist_id: str, uid: str = Depends(current_uid), repo=Depends(get_repository)):
    repo.delete_watchlist(uid, watchlist_id)
    return {"status": "ok"}


@router.get("/share/{watchlist_id}")
def shared_watchlist(watchlist_id: str, repo=Depends(get_repository)):
    row = repo.get_shared_watchlist(watchlist_id)
    if not row:
        raise HTTPException(status_code=404, detail="Watchlist not found")
    return {"watchlist": row}
