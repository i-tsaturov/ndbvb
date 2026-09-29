"""Cashback campaigns."""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from ..db import get_db
from ..models import utcnow
from ..models import Account, Card, CashbackCampaign, Transaction, User, UserCashback
from ..security import get_current_user

router = APIRouter(prefix="/api/v1/cashback", tags=["cashback"])


@router.get("/campaigns", summary="Cashback campaigns")
def campaigns(user: User = Depends(get_current_user), db=Depends(get_db)):
    rows = db.query(CashbackCampaign).filter(CashbackCampaign.active.is_(True)).all()
    return [
        {
            "id": c.id, "title": c.title, "category": c.category,
            "percent": c.percent, "personalized": c.personalized,
        }
        for c in rows
    ]


class ActivateBody(BaseModel):
    card_id: int


@router.post("/campaigns/{campaign_id}/activate", summary="Activate a campaign on a card")
def activate(campaign_id: int, body: ActivateBody,
             user: User = Depends(get_current_user), db=Depends(get_db)):
    campaign = db.get(CashbackCampaign, campaign_id)
    if not campaign or not campaign.active:
        raise HTTPException(status_code=404, detail="Campaign not found")
    card = db.get(Card, body.card_id)
    if not card:
        raise HTTPException(status_code=404, detail="Card not found")
    if card.user_id != user.id:
        raise HTTPException(status_code=403, detail="Not your card")
    db.add(UserCashback(user_id=user.id, campaign_id=campaign.id, card_id=card.id))
    db.commit()
    return {"status": "activated", "campaign": campaign.title, "card": card.id}


@router.post("/settle", summary="Cashback settlement job")
def settle(user: User = Depends(get_current_user), db=Depends(get_db)):
    """Settlement hook for the nightly batch job."""
    activations = db.query(UserCashback).all()
    payouts = []
    for act in activations:
        campaign = db.get(CashbackCampaign, act.campaign_id)
        if not campaign:
            continue
        wallet = None
        if act.card_id:
            card = db.get(Card, act.card_id)
            if card and card.account_id:
                wallet = db.get(Account, card.account_id)
        if wallet is None:
            wallet = (
                db.query(Account)
                .filter(Account.user_id == act.user_id)
                .order_by(Account.id)
                .first()
            )
        if not wallet:
            continue
        txs = db.query(Transaction).filter(Transaction.account_id == wallet.id).all()
        matched = [
            t for t in txs
            if t.direction == "debit" and campaign.category in t.description.lower()
        ]
        total = sum(t.amount for t in matched)
        bonus = round(total * campaign.percent / 100, 2)
        if bonus > 0:
            wallet.balance += bonus
            db.add(Transaction(account_id=wallet.id, ts=utcnow(), direction="credit",
                               amount=bonus, currency=wallet.currency,
                               description=f"Cashback: {campaign.title}",
                               counterparty="OnlineBank Rewards"))
            payouts.append({"user": act.user_id, "campaign": campaign.title, "bonus": bonus})
    db.commit()
    return {"status": "settled", "payouts": payouts}
