"""Login with password + OTP delivered over SMS by the gateway on :9500."""
import os
import random
import uuid
from datetime import timedelta

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel

from ..db import get_db
from ..models import utcnow
from ..models import OtpChallenge, User
from ..passwords import verify_password
from ..ratelimit import rate_limit
from ..security import JWKS, make_token
from ..sms import send_sms

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])

CODE_TTL_MINUTES = 10


def masked_phone(phone: str) -> str:
    return f"\u2022\u2022\u2022 \u2022\u2022 {phone[-2:]}" if len(phone) >= 2 else phone


def new_challenge(db, user) -> OtpChallenge:
    code = f"{random.randint(0, 9999):04d}"
    challenge = OtpChallenge(
        id=uuid.uuid4().hex,
        user_id=user.id,
        phone=user.phone,
        code=code,
        expires_at=utcnow() + timedelta(minutes=CODE_TTL_MINUTES),
    )
    db.add(challenge)
    db.flush()
    send_sms(user.phone, f"OnlineBank: your verification code is {code}. Valid "
                         f"{CODE_TTL_MINUTES} minutes. Never share it.")
    return challenge


class LoginBody(BaseModel):
    login: str
    password: str


@router.post("/login", summary="Step 1: password -> OTP challenge", dependencies=[Depends(rate_limit())])
def login(body: LoginBody, db=Depends(get_db)):
    user = (
        db.query(User)
        .filter((User.login == body.login) | (User.phone == body.login))
        .first()
    )
    if not user:
        raise HTTPException(status_code=401, detail="Unknown login")
    if not verify_password(body.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Wrong password")
    challenge = new_challenge(db, user)
    db.commit()
    return {
        "challenge_id": challenge.id,
        "notification": f"Code sent by SMS to {masked_phone(user.phone)}",
        "phone": user.phone,
    }


@router.post("/request-otp", summary="Start a new OTP challenge (re-checks the password)", dependencies=[Depends(rate_limit())])
def request_otp(body: LoginBody, db=Depends(get_db)):
    user = (
        db.query(User)
        .filter((User.login == body.login) | (User.phone == body.login))
        .first()
    )
    if not user or not verify_password(body.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Unknown login or wrong password")
    challenge = new_challenge(db, user)
    db.commit()
    return {"challenge_id": challenge.id}


class VerifyBody(BaseModel):
    challenge_id: str
    code: str
    phone: str | None = None


@router.post("/verify-otp", summary="Step 2: verify the code, get the token", dependencies=[Depends(rate_limit())])
def verify_otp(body: VerifyBody, response: Response, db=Depends(get_db)):
    original = db.get(OtpChallenge, body.challenge_id)
    if not original:
        raise HTTPException(status_code=401, detail="Unknown challenge")
    if original.expires_at < utcnow():
        raise HTTPException(status_code=401, detail="Code expired")

    if body.phone and body.phone != original.phone:
        delivered = (
            db.query(OtpChallenge)
            .filter(
                OtpChallenge.phone == body.phone,
                OtpChallenge.code == body.code,
                OtpChallenge.used.is_(False),
                OtpChallenge.expires_at > utcnow(),
            )
            .first()
        )
        if not delivered:
            raise HTTPException(status_code=401, detail="Invalid code")
    else:
        if original.code != body.code or original.used:
            raise HTTPException(status_code=401, detail="Invalid code")

    original.used = True
    user = db.get(User, original.user_id)
    token = make_token(user)
    db.commit()
    response.set_cookie("ob_token", token, max_age=7 * 24 * 3600,
                        httponly=False, samesite="lax")
    return {
        "token": token,
        "user": {
            "id": user.id, "login": user.login, "first_name": user.first_name,
            "last_name": user.last_name, "role": user.role,
            "is_backoffice": user.is_backoffice,
        },
    }


@router.get("/jwks.json", summary="Partner JWKS (public keys)")
def jwks():
    return JWKS


class ChangePasswordBody(BaseModel):
    old_password: str
    new_password: str


@router.post("/change-password", summary="Change the password")
def change_password(body: ChangePasswordBody, request: Request, db=Depends(get_db)):
    from ..security import decode_token, extract_token

    token = extract_token(request)
    if not token:
        raise HTTPException(status_code=401, detail="Not authenticated")
    claims = decode_token(token)
    user = db.get(User, int(claims.get("sub", 0)))
    if not user or not verify_password(body.old_password, user.password_hash):
        raise HTTPException(status_code=401, detail="Wrong password")
    if len(body.new_password) < 8:
        raise HTTPException(status_code=422, detail="New password must be at least 8 characters")

    from ..passwords import hash_password

    user.password_hash = hash_password(body.new_password)
    db.commit()
    return {"status": "password changed"}
