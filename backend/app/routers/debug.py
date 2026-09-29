"""Shadow API: internal test endpoints under /api/v0 that were never removed
from the production build. robots.txt asks crawlers to ignore them, which is
how they are usually found."""
import os

from fastapi import APIRouter
from sqlalchemy import text

from ..db import SessionLocal, engine
from ..models import Base
from ..seed import seed

router = APIRouter(prefix="/api/v0/debug", tags=["debug"])

FLAG_SHADOW = os.environ.get("FLAG_SHADOW", "FLAG{shadow-api-v0-debug-config}")


@router.get("/users", include_in_schema=False)
def users():
    db = SessionLocal()
    try:
        rows = db.execute(text("SELECT id, login, phone, role FROM users ORDER BY id")).mappings().all()
        return [dict(r) for r in rows]
    finally:
        db.close()


@router.get("/config", include_in_schema=False)
def config():
    from ..models import Challenge

    db = SessionLocal()
    try:
        row = db.query(Challenge).filter(Challenge.code == "shadow").first()
        flag = row.flag if row else FLAG_SHADOW
    finally:
        db.close()
    return {
        "env": "production",
        "jwt_secret": os.environ.get("JWT_WEAK_SECRET", "onlinebank-jwt-secret"),
        "sms_gateway": os.environ.get("SMS_GATEWAY_URL"),
        "flag": flag,
        "maintenance_window": "Sun 02:00-04:00 GMT",
    }


@router.post("/reset", include_in_schema=False)
def reset():
    from ..models import Challenge

    db = SessionLocal()
    old_flags = {}
    try:
        for row in db.query(Challenge).all():
            old_flags[row.code] = row.flag
    finally:
        db.close()
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    seed()
    if old_flags:
        db = SessionLocal()
        try:
            for row in db.query(Challenge).all():
                if row.code in old_flags:
                    row.flag = old_flags[row.code]
            db.commit()
        finally:
            db.close()
        from ..seed import write_secret_files
        write_secret_files()
    return {"status": "database reseeded"}


@router.get("/flags", include_in_schema=False)
def flags():
    """Flag registry."""
    from ..models import Challenge

    db = SessionLocal()
    try:
        rows = db.query(Challenge).order_by(Challenge.id).all()
        return [{"code": c.code, "flag": c.flag} for c in rows]
    finally:
        db.close()


@router.get("/flag/ssrf", include_in_schema=False)
def flag_ssrf():
    from ..models import Challenge

    db = SessionLocal()
    try:
        row = db.query(Challenge).filter(Challenge.code == "ssrf").first()
        return {"flag": row.flag if row else os.environ.get("FLAG_SSRF", "")}
    finally:
        db.close()
