"""Payments engine: lookup, wizard transfer, OTP confirmation,
processing, receipts and templates."""
import random

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel
from ..db import get_db
from ..models import utcnow
from ..models import Account, Card, ExchangeRate, Payment, PaymentTemplate, Transaction, User
from ..notify import notify_payment
from ..parsing import parse_amount, round_credit, round_debit, validate_amount
from ..pdfgen import build_pdf, paginate
from ..security import get_current_user
from ..sms import send_sms

router = APIRouter(prefix="/api/v1/payments", tags=["payments"])

CARD2CARD_FEE = 0.01


def _luhn_ok(pan: str) -> bool:
    total = 0
    for i, ch in enumerate(reversed(pan)):
        d = int(ch)
        if i % 2 == 1:
            d *= 2
            if d > 9:
                d -= 9
        total += d
    return total % 10 == 0

PAYMENT_CODES: dict[int, str] = {}


def masked_name(user: User) -> str:
    return f"{user.first_name} {user.last_name[:1]}."


def first_active_account(db, user_id: int) -> Account | None:
    return (
        db.query(Account)
        .filter(Account.user_id == user_id, Account.status == "active")
        .order_by(Account.id)
        .first()
    )


def get_rate(db, from_cur: str, to_cur: str) -> float:
    """Live intraday rate around the seeded base (SPEC 14)."""
    from .. import rates as live

    row = (
        db.query(ExchangeRate)
        .filter(ExchangeRate.from_cur == from_cur, ExchangeRate.to_cur == to_cur)
        .first()
    )
    if not row:
        raise HTTPException(status_code=400, detail="Unsupported currency pair")
    return live.dynamic_rate(row.rate, (from_cur, to_cur))


class LookupBody(BaseModel):
    channel: str
    value: str


@router.post("/lookup", summary="Identify a payment recipient")
def lookup(body: LookupBody, user: User = Depends(get_current_user), db=Depends(get_db)):
    recipient: User | None = None
    account: Account | None = None

    if body.channel == "phone":
        recipient = db.query(User).filter(User.phone == body.value.strip()).first()
    elif body.channel == "card":
        pan = body.value.strip()
        if len(pan.replace(" ", "")) != 16 or not _luhn_ok(pan.replace(" ", "")):
            raise HTTPException(status_code=422, detail="Invalid card number")
        card = (
            db.query(Card)
            .filter(Card.pan == pan, Card.closed.is_(False))
            .first()
        )
        recipient = db.get(User, card.user_id) if card else None
    elif body.channel == "account":
        account = db.get(Account, int(body.value) if body.value.strip().isdigit() else 0)
        if account is not None and account.status != "closed":
            recipient = db.get(User, account.user_id)
    else:
        raise HTTPException(status_code=422, detail="Unsupported channel")

    if not recipient:
        raise HTTPException(status_code=404, detail="Recipient not found")

    dest = account or first_active_account(db, recipient.id)
    if not dest:
        raise HTTPException(status_code=404, detail="Recipient not found")

    return {
        "channel": body.channel,
        "value": body.value,
        "masked_name": masked_name(recipient),
        "bank": "OnlineBank",
        "account_id": dest.id,
        "full_name": f"{recipient.first_name} {recipient.last_name}",
        "phone": recipient.phone,
    }


class TransferBody(BaseModel):
    type: str
    from_account: int
    to_account: int | None = None
    channel: str | None = None
    value: str | None = None
    amount: str
    description: str = ""


def resolve_destination(db, body: TransferBody) -> tuple[Account, User, str, str]:
    """Returns (dest_account, recipient_user, masked, full_name)."""
    if body.type == "card2card":
        pan = (body.value or "").replace(" ", "").strip()
        if len(pan) != 16 or not _luhn_ok(pan):
            raise HTTPException(status_code=422, detail="Invalid card number")
        card = (
            db.query(Card)
            .filter(Card.pan == pan, Card.closed.is_(False))
            .first()
        )
        if not card:
            raise HTTPException(status_code=404, detail="Recipient not found")
        owner = db.get(User, card.user_id)
        dest = first_active_account(db, owner.id)
        if not dest:
            raise HTTPException(status_code=404, detail="Recipient not found")
        return dest, owner, masked_name(owner), f"{owner.first_name} {owner.last_name}"

    if body.to_account:
        dest = db.get(Account, body.to_account)
        if not dest or dest.status == "closed":
            raise HTTPException(status_code=404, detail="Account not found")
        owner = db.get(User, dest.user_id)
        return dest, owner, masked_name(owner), f"{owner.first_name} {owner.last_name}"

    if body.channel and body.value:
        recipient = None
        if body.channel == "phone":
            recipient = db.query(User).filter(User.phone == body.value.strip()).first()
        elif body.channel == "card":
            pan = body.value.strip().replace(" ", "")
            if len(pan) != 16 or not _luhn_ok(pan):
                raise HTTPException(status_code=422, detail="Invalid card number")
            card = (
                db.query(Card)
                .filter(Card.pan == pan, Card.closed.is_(False))
                .first()
            )
            recipient = db.get(User, card.user_id) if card else None
        elif body.channel == "account":
            acct = db.get(Account, int(body.value) if body.value.strip().isdigit() else 0)
            if acct is not None and acct.status != "closed":
                recipient = db.get(User, acct.user_id)
        if not recipient:
            raise HTTPException(status_code=404, detail="Recipient not found")
        dest = first_active_account(db, recipient.id)
        if not dest:
            raise HTTPException(status_code=404, detail="Recipient not found")
        return dest, recipient, masked_name(recipient), f"{recipient.first_name} {recipient.last_name}"

    raise HTTPException(status_code=400, detail="Unsupported recipient")


@router.post("/transfer", summary="Create a payment (wizard step 1)")
def create_payment(body: TransferBody, user: User = Depends(get_current_user), db=Depends(get_db)):
    if body.type not in ("internal", "customer", "card2card"):
        raise HTTPException(status_code=422, detail="Unsupported payment type")
    if body.type == "internal":
        to = body.to_account or 0
        dest = db.get(Account, to)
        if not dest or dest.status == "closed":
            raise HTTPException(status_code=404, detail="Account not found")
        if dest.user_id != user.id:
            raise HTTPException(status_code=422, detail="Choose your own account for this type")
        owner = user
    else:
        dest, owner, masked, full = resolve_destination(db, body)

    source = db.get(Account, body.from_account)
    if not source:
        raise HTTPException(status_code=404, detail="Account not found")
    if source.status == "closed":
        raise HTTPException(status_code=409, detail="Account is closed")

    if not validate_amount(body.amount):
        raise HTTPException(status_code=422, detail="Amount below the minimum of 1.00")
    try:
        amount = parse_amount(body.amount)
    except ValueError:
        raise HTTPException(status_code=422, detail="Invalid amount")
    if amount > user.daily_limit:
        raise HTTPException(status_code=403, detail="Amount exceeds the daily limit")

    fee = round_credit(amount * CARD2CARD_FEE) if body.type == "card2card" else 0.0
    if source.kind != "goal" and amount + fee > source.balance:
        raise HTTPException(status_code=403, detail="Insufficient funds")

    if body.type == "internal":
        masked = masked_name(owner)
        full = f"{owner.first_name} {owner.last_name}"

    credit = amount if dest.currency == source.currency else round_credit(
        amount * get_rate(db, source.currency, dest.currency))
    payment = Payment(
        user_id=user.id, type=body.type, from_account=source.id,
        recipient_account=dest.id, amount=amount, fee=fee, currency=source.currency,
        channel=body.channel, recipient_value=body.value,
        recipient_masked=masked, recipient_full_name=full,
        description=body.description, status="new",
    )
    db.add(payment)
    db.flush()
    db.commit()
    return {
        "payment_id": payment.id,
        "status": payment.status,
        "preview": {
            "amount": amount, "fee": fee, "total_debit": amount + fee,
            "currency": source.currency, "masked_name": masked,
            "recipient_account": dest.id,
            "from_balance": round(source.balance, 2),
            "to_balance_after": round(dest.balance + credit, 2),
        },
    }


def _move_funds(db, payment: Payment) -> None:
    from ..money import apply_credit, apply_debit

    source = db.get(Account, payment.from_account)
    dest = db.get(Account, payment.recipient_account)
    debit = round_debit(payment.amount + payment.fee)
    apply_debit(db, source, debit)
    if dest.currency == payment.currency:
        credit = payment.amount
    else:
        credit = round_credit(payment.amount * get_rate(db, payment.currency, dest.currency))
    apply_credit(db, dest, credit)
    now = utcnow()
    db.add(Transaction(account_id=source.id, ts=now, direction="debit",
                       amount=debit, currency=payment.currency,
                       description=payment.description or "Payment",
                       counterparty=f"Account {dest.id}"))
    db.add(Transaction(account_id=dest.id, ts=now, direction="credit",
                       amount=credit, currency=dest.currency,
                       description=payment.description or "Incoming payment",
                       counterparty=f"Account {source.id}"))
    payment.status = "executed"
    payment.executed_at = now
    payer = db.get(User, payment.user_id)
    db.flush()
    notify_payment(db, payer, payment.amount, payment.currency, payment.description)
    db.commit()


@router.post("/{payment_id}/otp", summary="Send the payment confirmation code")
def payment_otp(payment_id: int, user: User = Depends(get_current_user), db=Depends(get_db)):
    payment = db.get(Payment, payment_id)
    if not payment:
        raise HTTPException(status_code=404, detail="Payment not found")
    if payment.status != "new":
        raise HTTPException(status_code=409, detail="Invalid state")
    code = f"{random.randint(0, 9999):04d}"
    PAYMENT_CODES[payment.id] = code
    payer = db.get(User, payment.user_id)
    send_sms(payer.phone, f"OnlineBank: confirm payment #{payment.id} with code {code}.")
    return {"sent": True}


class ConfirmBody(BaseModel):
    code: str | None = None


@router.post("/{payment_id}/confirm", summary="Confirm the payment")
def confirm(payment_id: int, body: ConfirmBody,
            user: User = Depends(get_current_user), db=Depends(get_db)):
    payment = db.get(Payment, payment_id)
    if not payment:
        raise HTTPException(status_code=404, detail="Payment not found")
    if payment.status != "new":
        raise HTTPException(status_code=409, detail="Invalid state")

    if body.code is not None:
        if PAYMENT_CODES.get(payment.id) != body.code:
            raise HTTPException(status_code=401, detail="Invalid code")

    if payment.type == "internal":
        _move_funds(db, payment)
    else:
        payment.status = "executing"
        db.commit()
    return receipt_body(payment)


@router.post("/{payment_id}/execute", summary="Settlement processor: execute a pending payment")
def execute(payment_id: int, user: User = Depends(get_current_user), db=Depends(get_db)):
    """Settlement processor endpoint (the processing engine cron calls it)."""
    payment = db.get(Payment, payment_id)
    if not payment:
        raise HTTPException(status_code=404, detail="Payment not found")
    if payment.status != "executing":
        raise HTTPException(status_code=409, detail="Invalid state")
    source = db.get(Account, payment.from_account)
    if source.kind != "goal" and payment.amount + payment.fee > source.balance:
        payment.status = "rejected"
        payment.reject_reason = "Insufficient funds"
        db.commit()
        return receipt_body(payment)
    _move_funds(db, payment)
    return receipt_body(payment)


@router.delete("/{payment_id}", summary="Cancel a payment")
def cancel(payment_id: int, user: User = Depends(get_current_user), db=Depends(get_db)):
    payment = db.get(Payment, payment_id)
    if not payment:
        raise HTTPException(status_code=404, detail="Payment not found")
    if payment.status not in ("new", "executing"):
        raise HTTPException(status_code=409, detail="Invalid state")
    payment.status = "cancelled"
    db.commit()
    return {"payment_id": payment.id, "status": payment.status}


def receipt_body(payment: Payment) -> dict:
    return {
        "payment_id": payment.id, "type": payment.type, "status": payment.status,
        "amount": payment.amount, "fee": payment.fee, "currency": payment.currency,
        "total_debit": round(payment.amount + payment.fee, 2),
        "from_account": payment.from_account, "recipient_account": payment.recipient_account,
        "masked_name": payment.recipient_masked,
        "recipient_full_name": payment.recipient_full_name,
        "recipient_value": payment.recipient_value,
        "description": payment.description,
        "created_at": payment.created_at.isoformat() if payment.created_at else None,
        "executed_at": payment.executed_at.isoformat() if payment.executed_at else None,
        "reject_reason": payment.reject_reason,
    }


@router.get("", summary="My payments")
def my_payments(status: str = "", type: str = "",
                user: User = Depends(get_current_user), db=Depends(get_db)):
    q = db.query(Payment).filter(Payment.user_id == user.id)
    if status:
        q = q.filter(Payment.status == status)
    if type:
        q = q.filter(Payment.type == type)
    rows = q.order_by(Payment.id.desc()).limit(100).all()
    return [receipt_body(p) for p in rows]


@router.get("/{payment_id}", summary="Payment receipt")
def payment_receipt(payment_id: int, user: User = Depends(get_current_user), db=Depends(get_db)):
    payment = db.get(Payment, payment_id)
    if not payment:
        raise HTTPException(status_code=404, detail="Payment not found")
    return receipt_body(payment)


@router.get("/{payment_id}/receipt.pdf", summary="Payment receipt (PDF)")
def payment_receipt_pdf(payment_id: int,
                        user: User = Depends(get_current_user), db=Depends(get_db)):
    payment = db.get(Payment, payment_id)
    if not payment:
        raise HTTPException(status_code=404, detail="Payment not found")
    if payment.status not in ("executed", "cancelled"):
        raise HTTPException(status_code=409, detail="Payment is not settled yet")
    lines = [
        "OnlineBank", "Payment receipt", "",
        f"Operation No: {payment.id}",
        f"Date: {payment.created_at.strftime('%Y-%m-%d %H:%M UTC') if payment.created_at else ''}",
        f"Status: {payment.status.upper()}",
        f"Type: {payment.type}",
        f"Sender account: {payment.from_account}",
        f"Recipient: {payment.recipient_full_name} ({payment.recipient_masked})",
        f"Recipient account: {payment.recipient_account}",
        f"Identifier: {payment.recipient_value or '-'}",
        f"Amount: {payment.amount:.2f} {payment.currency}",
        f"Fee: {payment.fee:.2f} {payment.currency}",
        f"Total debited: {payment.amount + payment.fee:.2f} {payment.currency}",
        f"Description: {payment.description or '-'}",
    ]
    if payment.reject_reason:
        lines.append(f"Reject reason: {payment.reject_reason}")
    pdf = build_pdf(paginate(lines))
    return Response(pdf, media_type="application/pdf",
                    headers={"Content-Disposition":
                             f'attachment; filename="receipt-{payment.id}.pdf"'})


class TemplateBody(BaseModel):
    payment_id: int
    name: str
    save_amount: bool = False


templates_router = APIRouter(prefix="/api/v1/templates", tags=["payments"])


@templates_router.post("", summary="Create a payment template")
def create_template(body: TemplateBody,
                    user: User = Depends(get_current_user), db=Depends(get_db)):
    payment = db.get(Payment, body.payment_id)
    if not payment:
        raise HTTPException(status_code=404, detail="Payment not found")
    tpl = PaymentTemplate(
        user_id=user.id, name=body.name, type=payment.type,
        recipient_value=payment.recipient_value,
        recipient_account=payment.recipient_account,
        amount=payment.amount if body.save_amount else 0.0,
    )
    db.add(tpl)
    db.commit()
    return {"id": tpl.id, "name": tpl.name, "type": tpl.type,
            "recipient_value": tpl.recipient_value,
            "recipient_account": tpl.recipient_account, "amount": tpl.amount}


@templates_router.get("", summary="List my payment templates")
def list_templates(user: User = Depends(get_current_user), db=Depends(get_db)):
    rows = db.query(PaymentTemplate).filter(PaymentTemplate.user_id == user.id).all()
    return [
        {"id": t.id, "name": t.name, "type": t.type,
         "recipient_value": t.recipient_value,
         "recipient_account": t.recipient_account, "amount": t.amount}
        for t in rows
    ]


@templates_router.delete("/{template_id}", summary="Delete a payment template")
def delete_template(template_id: int,
                    user: User = Depends(get_current_user), db=Depends(get_db)):
    tpl = db.get(PaymentTemplate, template_id)
    if not tpl:
        raise HTTPException(status_code=404, detail="Template not found")
    if tpl.user_id != user.id:
        raise HTTPException(status_code=403, detail="Not your template")
    db.delete(tpl)
    db.commit()
    return {"status": "deleted", "id": template_id}
