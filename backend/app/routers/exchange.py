"""Currency exchange: the check-then-act race lives here (live rates)."""
import time

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from .. import rates as live
from ..db import get_db
from ..models import utcnow
from ..models import Account, ExchangeRate, Transaction, User
from ..parsing import parse_amount, round_credit, round_debit, validate_amount
from ..security import get_current_user

router = APIRouter(prefix="/api/v1/exchange", tags=["exchange"])

def get_base_rate(db, from_cur: str, to_cur: str) -> float:
    row = (
        db.query(ExchangeRate)
        .filter(ExchangeRate.from_cur == from_cur, ExchangeRate.to_cur == to_cur)
        .first()
    )
    if not row:
        raise HTTPException(status_code=400, detail="Unsupported currency pair")
    return row.rate


def get_rate(db, from_cur: str, to_cur: str) -> float:
    """Live intraday rate around the seeded base (SPEC 14)."""
    base = get_base_rate(db, from_cur, to_cur)
    return live.dynamic_rate(base, (from_cur, to_cur))


@router.get("/rate", summary="Current exchange rate (live, per-minute)")
def rate(from_cur: str = "USD", to_cur: str = "GHS", db=Depends(get_db)):
    return {"from": from_cur, "to": to_cur, "rate": get_rate(db, from_cur, to_cur),
            "ts": utcnow().isoformat()}


@router.get("/rate/history", summary="Intraday rate history for the chart")
def rate_history_ep(from_cur: str = "USD", to_cur: str = "GHS", points: int = 48,
                    db=Depends(get_db)):
    if not 1 <= points <= 1440:
        raise HTTPException(status_code=422, detail="points must be 1..1440")
    base = get_base_rate(db, from_cur, to_cur)
    values = live.rate_history(base, (from_cur, to_cur), points)
    now = utcnow()
    series = []
    for i, v in enumerate(reversed(values)):
        ts = now.fromtimestamp(now.timestamp() - i * 60, tz=now.tzinfo)
        series.append({"ts": ts.isoformat(), "rate": v})
    series.reverse()
    return series


@router.get("/rates", summary="All base rate pairs")
def rates(db=Depends(get_db)):
    rows = db.query(ExchangeRate).all()
    return [{"from": r.from_cur, "to": r.to_cur, "rate": r.rate} for r in rows]


class ConvertBody(BaseModel):
    account_id: int
    to_currency: str
    amount: str


@router.post("/convert", summary="Convert between own accounts")
def convert(body: ConvertBody, user: User = Depends(get_current_user), db=Depends(get_db)):
    account = db.get(Account, body.account_id)
    if not account:
        raise HTTPException(status_code=404, detail="Account not found")
    if not validate_amount(body.amount):
        raise HTTPException(status_code=422, detail="Amount below the minimum of 1.00")
    try:
        amount = parse_amount(body.amount)
    except ValueError:
        raise HTTPException(status_code=422, detail="Invalid amount")
    rate = get_rate(db, account.currency, body.to_currency)

    if amount > account.balance:
        raise HTTPException(status_code=403, detail="Insufficient funds")

    time.sleep(0.35)

    charged = round_debit(amount)
    credited = round_credit(amount * rate)

    wallet = (
        db.query(Account)
        .filter(Account.user_id == user.id, Account.currency == body.to_currency)
        .order_by(Account.id)
        .first()
    )
    if not wallet:
        wallet = Account(user_id=user.id, currency=body.to_currency, balance=0.0)
        db.add(wallet)
        db.flush()

    now = utcnow()
    db.add(Transaction(account_id=account.id, ts=now, direction="debit", amount=charged,
                       currency=account.currency,
                       description=f"Currency exchange to {body.to_currency}",
                       counterparty="OnlineBank FX Desk"))
    db.add(Transaction(account_id=wallet.id, ts=now, direction="credit", amount=credited,
                       currency=wallet.currency,
                       description=f"Currency exchange from {account.currency}",
                       counterparty="OnlineBank FX Desk"))
    db.flush()
    from ..money import apply_credit, apply_debit

    apply_debit(db, account, charged)
    apply_credit(db, wallet, credited)
    db.expire(account)
    db.expire(wallet)
    db.add(account)
    db.add(wallet)
    db.commit()
    db.refresh(account)
    db.refresh(wallet)
    resp = {
        "status": "completed",
        "charged": charged,
        "credited": credited,
        "rate": rate,
        "balance": round(account.balance, 2),
        "wallet_balance": round(wallet.balance, 2),
    }
    if account.balance < -100:
        from ..seed import registered_flags

        resp["settlement_desk_note"] = registered_flags()["FLAG_RACE"]
    return resp
