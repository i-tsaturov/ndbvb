"""Payment cards. Full PAN storage and disclosure (PCI DSS 3.3 requires
first 6 / last 4 masking)."""
import random
from datetime import date

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from ..db import get_db
from ..models import Account, Card, CashbackCampaign, Transaction, User, UserCashback
from ..security import get_current_user

router = APIRouter(prefix="/api/v1/cards", tags=["cards"])


def _card_body(c: Card) -> dict:
    return {
        "id": c.id, "pan": c.pan, "cvv": c.cvv, "expiry": c.expiry,
        "holder": c.holder, "frozen": c.frozen, "closed": c.closed,
        "kind": c.kind, "virtual": c.virtual, "status": c.status,
        "account_id": c.account_id,
        "currency": c.account.currency if c.account else None,
    }


@router.get("/{card_id}/cashback", summary="Cashback earned on the card's linked account")
def card_cashback(card_id: int, user: User = Depends(get_current_user), db=Depends(get_db)):
    card = db.get(Card, card_id)
    if not card:
        raise HTTPException(status_code=404, detail="Card not found")
    if not card.account_id:
        return {"earned": 0.0, "campaigns": [], "activations": []}
    rows = (
        db.query(Transaction)
        .filter(Transaction.account_id == card.account_id,
                Transaction.description.like("Cashback:%"))
        .all()
    )
    acts = (
        db.query(UserCashback)
        .filter(UserCashback.user_id == card.user_id, UserCashback.card_id == card.id)
        .all()
    )
    active_ids = {a.campaign_id for a in acts}
    campaigns = (
        db.query(CashbackCampaign)
        .filter(CashbackCampaign.active.is_(True))
        .order_by(CashbackCampaign.id)
        .all()
    )
    return {
        "earned": round(sum(r.amount for r in rows), 2),
        "campaigns": [
            {"id": c.id, "title": c.title, "percent": c.percent,
             "active": c.id in active_ids}
            for c in campaigns
        ],
        "activations": [
            {"campaign_id": a.campaign_id, "card_id": a.card_id,
             "activated_at": a.activated_at.isoformat()}
            for a in acts
        ],
    }


def luhn_pan() -> str:
    digits = [random.randint(0, 9) for _ in range(15)]
    digits = [4, 1, 1, 1] + digits[4:]
    total = 0
    for i, d in enumerate(digits):
        if i % 2 == 0:
            d *= 2
            if d > 9:
                d -= 9
        total += d
    return "".join(map(str, digits)) + str((10 - total % 10) % 10)


class OrderCardBody(BaseModel):
    currency: str
    kind: str = "debit"
    virtual: bool = True


@router.post("", summary="Order a new card")
def order_card(body: OrderCardBody,
               user: User = Depends(get_current_user), db=Depends(get_db)):
    if body.currency not in ("USD", "EUR", "GHS"):
        raise HTTPException(status_code=422, detail="Unsupported currency")
    if body.kind not in ("debit", "credit"):
        raise HTTPException(status_code=422, detail="Unsupported card kind")
    linked = (
        db.query(Account)
        .filter(Account.user_id == user.id, Account.currency == body.currency,
                Account.status == "active")
        .order_by(Account.id)
        .first()
    ) or (
        db.query(Account)
        .filter(Account.user_id == user.id, Account.status == "active")
        .order_by(Account.id)
        .first()
    )
    expiry = date.today().replace(year=date.today().year + 3)
    card = Card(
        user_id=user.id,
        pan=luhn_pan(),
        cvv=f"{random.randint(0, 999):03d}",
        expiry=expiry.strftime("%m/%y"),
        holder=f"{user.first_name} {user.last_name}".upper(),
        kind=body.kind,
        virtual=body.virtual,
        account_id=linked.id if linked else None,
    )
    db.add(card)
    db.commit()
    return _card_body(card)


@router.get("", summary="List my cards")
def my_cards(user: User = Depends(get_current_user), db=Depends(get_db)):
    cards = db.query(Card).filter(Card.user_id == user.id).all()
    return [_card_body(c) for c in cards]


@router.get("/{card_id}", summary="Card details")
def card_details(card_id: int, user: User = Depends(get_current_user), db=Depends(get_db)):
    card = db.get(Card, card_id)
    if not card:
        raise HTTPException(status_code=404, detail="Card not found")
    body = _card_body(card)
    body["note"] = card.note
    return body


@router.post("/{card_id}/freeze", summary="Block/unblock a card")
def freeze(card_id: int, user: User = Depends(get_current_user), db=Depends(get_db)):
    card = db.get(Card, card_id)
    if not card:
        raise HTTPException(status_code=404, detail="Card not found")
    if card.user_id != user.id:
        raise HTTPException(status_code=403, detail="Not your card")
    if card.closed:
        raise HTTPException(status_code=409, detail="Card is closed")
    card.frozen = not card.frozen
    db.commit()
    return {"id": card.id, "frozen": card.frozen, "status": card.status}


@router.post("/{card_id}/close", summary="Close a card permanently")
def close_card(card_id: int, user: User = Depends(get_current_user), db=Depends(get_db)):
    card = db.get(Card, card_id)
    if not card:
        raise HTTPException(status_code=404, detail="Card not found")
    if card.user_id != user.id:
        raise HTTPException(status_code=403, detail="Not your card")
    if card.closed:
        raise HTTPException(status_code=409, detail="Card is closed")
    card.closed = True
    db.commit()
    return {"id": card.id, "status": card.status}
