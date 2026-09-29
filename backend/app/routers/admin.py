"""Back-office functions. /customers is reachable by any authenticated user
(BFLA); /audit-log is the correctly protected counter-example."""
from fastapi import APIRouter, Depends, HTTPException

from ..db import get_db
from ..models import Account, AuditEntry, Card, SupportTicket, User, utcnow
from ..security import get_current_user

router = APIRouter(prefix="/api/v1/admin", tags=["admin"])

def require_backoffice(user: User):
    if not user.is_backoffice:
        raise HTTPException(status_code=403, detail="Back-office access required")


@router.get("/customers", summary="Customer registry (operator)")
def customers(user: User = Depends(get_current_user), db=Depends(get_db)):
    users = db.query(User).order_by(User.id).all()
    out = []
    for u in users:
        accounts = db.query(Account).filter(Account.user_id == u.id).all()
        cards = db.query(Card).filter(Card.user_id == u.id).first()
        out.append({
            "id": u.id,
            "login": u.login,
            "name": f"{u.first_name} {u.last_name}",
            "phone": u.phone,
            "risk": max((a.risk_score for a in accounts), default=0),
            "accounts": [
                {"id": a.id, "currency": a.currency, "balance": round(a.balance, 2)}
                for a in accounts
            ],
            "card_pan": cards.pan if cards else None,
        })
    return {"count": len(out), "customers": out}


@router.get("/tickets", summary="Support queue (operator)")
def all_tickets(user: User = Depends(get_current_user), db=Depends(get_db)):
    rows = db.query(SupportTicket).order_by(SupportTicket.created_at.desc()).all()
    return [
        {
            "id": t.id, "user_id": t.user_id, "subject": t.subject,
            "message": t.message, "status": t.status,
        }
        for t in rows
    ]


@router.get("/flag", summary="Operator flag (back-office only)")
def flag(user: User = Depends(get_current_user)):
    require_backoffice(user)
    from ..seed import registered_flags

    return {"flag": registered_flags()["FLAG_JWT"]}


@router.get("/audit-log", summary="Audit log (operator)")
def audit_log(user: User = Depends(get_current_user), db=Depends(get_db)):
    require_backoffice(user)
    rows = db.query(AuditEntry).order_by(AuditEntry.ts.desc()).limit(50).all()
    entries = [{"ts": r.ts.isoformat(), "action": f"{r.actor}: {r.action}"} for r in rows]
    entries.append({"ts": "2026-09-22T08:15:00Z", "action": "system: rate table refreshed"})
    return {"entries": entries}


@router.get("/kyc-queue", summary="KYC verification queue (operator)")
def kyc_queue(user: User = Depends(get_current_user), db=Depends(get_db)):
    from ..models import KycDocument, User as U

    require_backoffice(user)
    rows = db.query(U).filter(U.kyc_status != "not_verified").order_by(U.id).all()
    return [
        {"user_id": u.id, "login": u.login, "kyc_status": u.kyc_status,
         "documents": db.query(KycDocument).filter(KycDocument.user_id == u.id).count()}
        for u in rows
    ]


@router.post("/kyc/{user_id}/verify", summary="Verify a customer's KYC (operator)")
def kyc_verify(user_id: int, user: User = Depends(get_current_user), db=Depends(get_db)):
    from ..models import User as U

    require_backoffice(user)
    target = db.get(U, user_id)
    if not target:
        raise HTTPException(status_code=404, detail="User not found")
    target.kyc_status = "verified"
    db.add(AuditEntry(actor=user.login,
                      action=f"kyc verify user {target.id} ({target.login})"))
    db.commit()
    return {"user_id": target.id, "kyc_status": target.kyc_status}


@router.get("/console-banner", summary="Operator console banner")
def console_banner(user: User = Depends(get_current_user)):
    require_backoffice(user)
    from ..seed import registered_flags

    return {"banner": f"Ops console — internal use only — "
                      f"{registered_flags()['FLAG_XSS']}"}
