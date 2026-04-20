from __future__ import annotations

from fastapi import APIRouter, Depends, Request

from ..dependencies import current_uid, get_repository
from ..schemas.alerts import AlertCreateRequest


router = APIRouter(prefix="/api/alerts", tags=["alerts"])


@router.get("")
def list_alerts(uid: str = Depends(current_uid), repo=Depends(get_repository)):
    return {"alerts": repo.list_alerts(uid), "notifications": repo.list_notifications(uid)}


@router.post("")
def create_alert(payload: AlertCreateRequest, request: Request, uid: str = Depends(current_uid), repo=Depends(get_repository)):
    row = repo.create_alert(uid, payload.model_dump())
    notification = repo.add_notification(
        uid,
        {
            "title": "Alert Created",
            "body": f"{row['type'].title()} alert for {row.get('symbol') or 'portfolio'} has been added.",
            "type": "alert",
        },
    )
    try:
        profile = repo.ensure_user(uid)
        notify_settings = profile.get("notifications", {})
        email = profile.get("email")
        if notify_settings.get("email_alerts") and email:
            request.app.state.email_service.send(
                email,
                "StockSight Learner Alert Created",
                f"Your alert is active.\n\nType: {row['type']}\nSymbol: {row.get('symbol','')}\nMessage: {row.get('message','')}",
            )
    except Exception:
        pass
    return {"alert": row, "notification": notification}


@router.delete("/{alert_id}")
def delete_alert(alert_id: str, uid: str = Depends(current_uid), repo=Depends(get_repository)):
    repo.delete_alert(uid, alert_id)
    return {"status": "ok"}
