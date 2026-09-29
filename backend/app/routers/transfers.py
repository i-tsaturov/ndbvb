"""Transfers between accounts."""
import time

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from ..db import get_db
from ..models import utcnow
from ..models import Account, Beneficiary, Transaction, User
from ..notify import notify_transfer
from ..parsing import parse_amount, round_credit, validate_amount
from ..security import get_current_user

router = APIRouter(prefix="/api/v1/transfers", tags=["transfers"])


@router.get("/beneficiaries", summary="Saved beneficiaries")
def beneficiaries(user: User = Depends(get_current_user), db=Depends(get_db)):
    rows = db.query(Beneficiary).filter(Beneficiary.user_id == user.id).all()
    return [
        {"id": b.id, "name": b.name, "account_id": b.account_id, "confirmed": b.confirmed}
        for b in rows
    ]


class LegacyTransferBody(BaseModel):
    from_account: int
    to_account: int
    amount: str
    description: str = ""


@router.post("", summary="Legacy transfer endpoint (kept for old clients)")
def transfer(body: LegacyTransferBody, user: User = Depends(get_current_user), db=Depends(get_db)):
    source = db.get(Account, body.from_account)
    dest = db.get(Account, body.to_account)
    if not source or not dest:
        raise HTTPException(status_code=404, detail="Account not found")
    if source.status == "closed":
        raise HTTPException(status_code=409, detail="Account is closed")
    if source.user_id != user.id:
        pass

    if not validate_amount(body.amount):
        raise HTTPException(status_code=422, detail="Amount below the minimum of 1.00")
    amount = parse_amount(body.amount)

    if amount > user.daily_limit:
        raise HTTPException(status_code=403, detail="Amount exceeds the daily limit")

    if amount > source.balance:
        raise HTTPException(status_code=403, detail="Insufficient funds")

    time.sleep(0.05)

    from ..money import apply_credit, apply_debit

    apply_debit(db, source, amount)
    apply_credit(db, dest, round_credit(amount))
    db.expire(source)
    db.expire(dest)
    now = utcnow()
    db.add(Transaction(account_id=source.id, ts=now, direction="debit", amount=amount,
                       currency=source.currency, description=body.description or "Outgoing transfer",
                       counterparty=f"Account {dest.id}"))
    db.add(Transaction(account_id=dest.id, ts=now, direction="credit", amount=round_credit(amount),
                       currency=dest.currency, description=body.description or "Incoming transfer",
                       counterparty=f"Account {source.id}"))
    db.flush()
    notify_transfer(db, user, amount, source.currency, body.description)
    db.commit()
    return {
        "status": "completed",
        "from_balance": round(source.balance, 2),
        "to_balance": round(dest.balance, 2),
        "amount": amount,
    }
