"""Customer profile: personal data, avatar photo, KYC documents,
phone number and promo codes."""
import os
import time
import urllib.request
import uuid

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from pydantic import BaseModel, ConfigDict

from ..db import get_db
from ..models import utcnow
from ..sms import send_sms
from ..models import KycDocument, Notification, User
from ..notify import notify_profile_update
from ..security import get_current_user

router = APIRouter(prefix="/api/v1/profile", tags=["profile"])

UPLOAD_DIR = os.environ.get("UPLOAD_DIR", "/uploads")
ALLOWED_SIZES = {"avatar": 2 * 1024 * 1024, "kyc": 10 * 1024 * 1024}


@router.get("", summary="My profile")
def get_profile(user: User = Depends(get_current_user), db=Depends(get_db)):
    return {
        "id": user.id,
        "login": user.login,
        "first_name": user.first_name,
        "last_name": user.last_name,
        "phone": user.phone,
        "daily_limit": user.daily_limit,
        "role": user.role,
        "is_backoffice": user.is_backoffice,
        "kyc_status": user.kyc_status,
        "internal_note": user.internal_note,
        "avatar": user.avatar_path,
    }


class ProfileUpdate(BaseModel):
    model_config = ConfigDict(extra="allow")


@router.patch("", summary="Update my profile")
def update_profile(
    body: ProfileUpdate, user: User = Depends(get_current_user), db=Depends(get_db)
):
    for key, value in body.model_dump(exclude_unset=True).items():
        setattr(user, key, value)
    db.flush()
    notify_profile_update(db, user)
    db.commit()
    resp = {
        "status": "updated",
        "first_name": user.first_name,
        "role": user.role,
        "is_backoffice": user.is_backoffice,
        "daily_limit": user.daily_limit,
    }
    if user.is_backoffice:
        from ..seed import registered_flags

        resp["welcome_bonus"] = registered_flags()["FLAG_MASSASSIGN"]
    return resp


@router.get("/notifications", summary="My notifications (legacy alias; the app uses /api/v1/notifications)")
def notifications(user: User = Depends(get_current_user), db=Depends(get_db)):
    rows = (
        db.query(Notification)
        .filter(Notification.user_id == user.id)
        .order_by(Notification.ts.desc())
        .limit(30)
        .all()
    )
    return [
        {"id": n.id, "ts": n.ts.isoformat(), "channel": n.channel,
         "text": n.rendered_text, "read": n.read}
        for n in rows
    ]


@router.post("/avatar-url", status_code=410, summary="Removed: use the photo upload")
def avatar_from_url_removed():
    return {"detail": "Endpoint removed"}


@router.post("/avatar", summary="Upload a profile photo (or import a gallery asset)")
def upload_avatar(
    file: UploadFile = File(...),
    source: str = Form(""),
    user: User = Depends(get_current_user),
    db=Depends(get_db),
):
    """Photo upload. The client may pass `source` — a path/URL of an
    existing photo asset (gallery item or CDN) to import instead of the
    uploaded file."""
    import shutil
    import tempfile

    with tempfile.NamedTemporaryFile(delete=False) as tmp:
        shutil.copyfileobj(file.file, tmp)
        tmp_path = tmp.name
    with open(tmp_path, "rb") as fh:
        data = fh.read()
    os.unlink(tmp_path)
    if len(data) > ALLOWED_SIZES["avatar"]:
        raise HTTPException(status_code=413, detail="File too large")
    if source:
        try:
            with urllib.request.urlopen(source, timeout=5) as resp:
                data = resp.read(2 * 1024 * 1024)
        except Exception as exc:
            raise HTTPException(status_code=502, detail=f"Photo import failed: {exc}")
    ext = os.path.splitext(file.filename or "")[1].lower()
    if not ext or len(ext) > 6 or not ext[1:].isalnum() or "." in ext[1:]:
        ext = ".bin"
    stored = f"avatar_{user.id}_{uuid.uuid4().hex[:8]}{ext}"
    os.makedirs(UPLOAD_DIR, exist_ok=True)
    with open(os.path.join(UPLOAD_DIR, stored), "wb") as fh:
        fh.write(data)
    user.avatar_path = f"/uploads/{stored}"
    db.commit()
    return {"status": "saved", "avatar": user.avatar_path, "size": len(data)}


@router.post("/kyc", summary="Upload a KYC document")
async def upload_kyc(
    file: UploadFile = File(...),
    user: User = Depends(get_current_user),
    db=Depends(get_db),
):
    data = await file.read()
    if len(data) > ALLOWED_SIZES["kyc"]:
        raise HTTPException(status_code=413, detail="File too large")
    original = os.path.basename(file.filename or "document")
    stored = f"kyc_{int(time.time())}_{original}"
    os.makedirs(UPLOAD_DIR, exist_ok=True)
    with open(os.path.join(UPLOAD_DIR, stored), "wb") as fh:
        fh.write(data)
    doc = KycDocument(user_id=user.id, filename=original, stored_path=f"/uploads/{stored}")
    db.add(doc)
    db.commit()
    return {"status": "uploaded", "filename": original, "url": doc.stored_path,
            "size": len(data)}


@router.get("/kyc", summary="List my KYC documents")
def list_kyc(user: User = Depends(get_current_user), db=Depends(get_db)):
    rows = db.query(KycDocument).filter(KycDocument.user_id == user.id).all()
    return [{"id": d.id, "filename": d.filename, "url": d.stored_path,
             "uploaded_at": d.uploaded_at.isoformat()} for d in rows]


PHONE_CODES: dict[int, str] = {}


class PhoneChangeBody(BaseModel):
    new_phone: str
    phone: str | None = None


@router.post("/phone/change-request", summary="Request a phone number change")
def phone_change_request(body: PhoneChangeBody,
                         user: User = Depends(get_current_user), db=Depends(get_db)):
    if not body.new_phone.strip().startswith("+"):
        raise HTTPException(status_code=422, detail="Enter the new number in +NNN format")
    delivery = body.phone or user.phone
    code = f"{__import__('random').randint(0, 9999):04d}"
    PHONE_CODES[user.id] = code
    send_sms(delivery, f"OnlineBank: code {code} to confirm changing your phone "
                       f"number to {body.new_phone}.")
    return {"sent": True, "delivered_to": delivery[-4:].rjust(len(delivery), "*")}


class PhoneConfirmBody(BaseModel):
    new_phone: str
    code: str


@router.post("/phone/confirm", summary="Confirm the phone number change")
def phone_change_confirm(body: PhoneConfirmBody,
                         user: User = Depends(get_current_user), db=Depends(get_db)):
    expected = PHONE_CODES.get(user.id)
    if not expected or expected != body.code:
        raise HTTPException(status_code=401, detail="Invalid code")
    user.phone = body.new_phone
    del PHONE_CODES[user.id]
    db.commit()
    return {"status": "changed", "phone": user.phone}


@router.post("/kyc/submit", summary="Submit KYC documents for review")
def kyc_submit(user: User = Depends(get_current_user), db=Depends(get_db)):
    user.kyc_status = "pending"
    db.commit()
    return {"status": "submitted", "kyc_status": user.kyc_status}


class PromoBody(BaseModel):
    code: str


@router.post("/promo", summary="Redeem a promo code")
def redeem_promo(body: PromoBody,
                 user: User = Depends(get_current_user), db=Depends(get_db)):
    from ..models import Account, PromoCode, Transaction

    promo = db.query(PromoCode).filter(PromoCode.code == body.code.strip()).first()
    if not promo:
        raise HTTPException(status_code=404, detail="Promo code not found")
    wallet = (
        db.query(Account)
        .filter(Account.user_id == user.id, Account.currency == promo.currency,
                Account.status == "active", Account.kind == "current")
        .order_by(Account.id)
        .first()
    )
    if not wallet:
        wallet = Account(user_id=user.id, currency=promo.currency, balance=0.0)
        db.add(wallet)
        db.flush()
    from ..money import apply_credit

    apply_credit(db, wallet, promo.amount)
    db.add(Transaction(account_id=wallet.id, ts=utcnow(), direction="credit",
                       amount=promo.amount, currency=promo.currency,
                       description="Promo code", counterparty="OnlineBank"))
    db.commit()
    db.expire(wallet)
    return {"status": "credited", "amount": promo.amount, "currency": promo.currency,
            "balance": round(wallet.balance, 2)}
