"""Outgoing webhooks."""
import urllib.request

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from ..db import get_db
from ..models import User, Webhook
from ..security import get_current_user

router = APIRouter(prefix="/api/v1/webhooks", tags=["webhooks"])


class WebhookBody(BaseModel):
    url: str
    event: str = "transfer.completed"


@router.get("", include_in_schema=False)
def list_webhooks(user: User = Depends(get_current_user), db=Depends(get_db)):
    rows = db.query(Webhook).filter(Webhook.user_id == user.id).all()
    return [
        {"id": w.id, "url": w.url, "event": w.event, "last_status": w.last_status}
        for w in rows
    ]


@router.post("", include_in_schema=False)
def create_webhook(body: WebhookBody, user: User = Depends(get_current_user), db=Depends(get_db)):
    webhook = Webhook(user_id=user.id, url=body.url, event=body.event)
    db.add(webhook)
    db.commit()
    return {"id": webhook.id, "url": webhook.url, "event": webhook.event}


@router.post("/{webhook_id}/test", include_in_schema=False)
def test_webhook(webhook_id: int, user: User = Depends(get_current_user), db=Depends(get_db)):
    webhook = db.get(Webhook, webhook_id)
    if not webhook:
        raise HTTPException(status_code=404, detail="Webhook not found")
    try:
        req = urllib.request.Request(webhook.url, method="GET")
        with urllib.request.urlopen(req, timeout=5) as resp:
            status = resp.status
            ctype = resp.headers.get("content-type", "")
            body = resp.read(800).decode("utf-8", "replace")
    except urllib.error.HTTPError as exc:
        status = exc.code
        ctype = exc.headers.get("content-type", "")
        body = exc.read(800).decode("utf-8", "replace")
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Delivery failed: {exc}")
    webhook.last_status = status
    webhook.last_body = body[:400]
    db.commit()
    return {"status": status, "content_type": ctype, "body_preview": body}
