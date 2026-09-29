"""Notification center (the sidebar bell)."""
from fastapi import APIRouter, Depends

from ..db import get_db
from ..models import Notification, User
from ..security import get_current_user

router = APIRouter(prefix="/api/v1/notifications", tags=["profile"])


@router.get("", summary="My notifications (bell)")
def my_notifications(user: User = Depends(get_current_user), db=Depends(get_db)):
    rows = (
        db.query(Notification)
        .filter(Notification.user_id == user.id)
        .order_by(Notification.ts.desc())
        .limit(20)
        .all()
    )
    return [
        {"id": n.id, "ts": n.ts.isoformat(), "text": n.rendered_text,
         "read": n.read}
        for n in rows
    ]


@router.post("/read", summary="Mark my notifications as read")
def mark_read(user: User = Depends(get_current_user), db=Depends(get_db)):
    updated = (
        db.query(Notification)
        .filter(Notification.user_id == user.id, Notification.read.is_(False))
        .update({Notification.read: True})
    )
    db.commit()
    return {"read": updated}
