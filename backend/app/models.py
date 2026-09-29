from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Identity, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .db import Base


def utcnow():
    return datetime.now(timezone.utc)


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    login: Mapped[str] = mapped_column(String(120), unique=True)
    password_hash: Mapped[str] = mapped_column(String(200))
    first_name: Mapped[str] = mapped_column(String(80))
    last_name: Mapped[str] = mapped_column(String(80))
    phone: Mapped[str] = mapped_column(String(32))
    role: Mapped[str] = mapped_column(String(32), default="customer")
    is_backoffice: Mapped[bool] = mapped_column(Boolean, default=False)
    daily_limit: Mapped[float] = mapped_column(Float, default=5000.0)
    token_version: Mapped[int] = mapped_column(Integer, default=1)
    avatar_path: Mapped[str | None] = mapped_column(String(255), default=None)
    internal_note: Mapped[str | None] = mapped_column(Text, default=None)
    secret_note: Mapped[str | None] = mapped_column(Text, default=None)
    kyc_status: Mapped[str] = mapped_column(String(12), default="not_verified")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    accounts: Mapped[list["Account"]] = relationship(back_populates="owner")


class Account(Base):
    __tablename__ = "accounts"

    id: Mapped[int] = mapped_column(Integer, Identity(start=1001, increment=1), primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    currency: Mapped[str] = mapped_column(String(3))
    balance: Mapped[float] = mapped_column(Float, default=0.0)
    risk_score: Mapped[int] = mapped_column(Integer, default=1)
    opened_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    is_internal: Mapped[bool] = mapped_column(Boolean, default=False)
    kind: Mapped[str] = mapped_column(String(12), default="current")
    status: Mapped[str] = mapped_column(String(12), default="active")
    apr: Mapped[float] = mapped_column(Float, default=0.0)
    target_amount: Mapped[float | None] = mapped_column(Float, default=None)
    credit_limit: Mapped[float] = mapped_column(Float, default=0.0)
    debt: Mapped[float] = mapped_column(Float, default=0.0)

    owner: Mapped[User] = relationship(back_populates="accounts")


class Transaction(Base):
    __tablename__ = "transactions"

    id: Mapped[int] = mapped_column(primary_key=True)
    account_id: Mapped[int] = mapped_column(ForeignKey("accounts.id"))
    ts: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    direction: Mapped[str] = mapped_column(String(8))
    amount: Mapped[float] = mapped_column(Float)
    currency: Mapped[str] = mapped_column(String(3))
    description: Mapped[str] = mapped_column(Text, default="")
    counterparty: Mapped[str] = mapped_column(String(120), default="")
    status: Mapped[str] = mapped_column(String(16), default="completed")


class Card(Base):
    __tablename__ = "cards"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    pan: Mapped[str] = mapped_column(String(19))
    cvv: Mapped[str] = mapped_column(String(4))
    expiry: Mapped[str] = mapped_column(String(7))
    holder: Mapped[str] = mapped_column(String(120))
    kind: Mapped[str] = mapped_column(String(10), default="debit")
    virtual: Mapped[bool] = mapped_column(Boolean, default=True)
    account_id: Mapped[int | None] = mapped_column(ForeignKey("accounts.id"), default=None)
    frozen: Mapped[bool] = mapped_column(Boolean, default=False)
    closed: Mapped[bool] = mapped_column(Boolean, default=False)
    note: Mapped[str | None] = mapped_column(Text, default=None)
    account: Mapped["Account | None"] = relationship()

    @property
    def status(self) -> str:
        return "closed" if self.closed else ("blocked" if self.frozen else "active")


class OtpChallenge(Base):
    __tablename__ = "otp_challenges"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    phone: Mapped[str] = mapped_column(String(32))
    code: Mapped[str] = mapped_column(String(6))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    used: Mapped[bool] = mapped_column(Boolean, default=False)
    attempts: Mapped[int] = mapped_column(Integer, default=0)


class CashbackCampaign(Base):
    __tablename__ = "cashback_campaigns"

    id: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[str] = mapped_column(String(120))
    category: Mapped[str] = mapped_column(String(40))
    percent: Mapped[float] = mapped_column(Float)
    personalized: Mapped[bool] = mapped_column(Boolean, default=False)
    owner_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), default=None)
    active: Mapped[bool] = mapped_column(Boolean, default=True)


class UserCashback(Base):
    __tablename__ = "user_cashbacks"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    campaign_id: Mapped[int] = mapped_column(ForeignKey("cashback_campaigns.id"))
    card_id: Mapped[int | None] = mapped_column(ForeignKey("cards.id"), default=None)
    activated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Beneficiary(Base):
    __tablename__ = "beneficiaries"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    name: Mapped[str] = mapped_column(String(120))
    account_id: Mapped[int] = mapped_column(Integer)
    confirmed: Mapped[bool] = mapped_column(Boolean, default=False)


class Webhook(Base):
    __tablename__ = "webhooks"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    url: Mapped[str] = mapped_column(String(500))
    event: Mapped[str] = mapped_column(String(60), default="transfer.completed")
    last_status: Mapped[int | None] = mapped_column(Integer, default=None)
    last_body: Mapped[str | None] = mapped_column(Text, default=None)


class KycDocument(Base):
    __tablename__ = "kyc_documents"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    filename: Mapped[str] = mapped_column(String(255))
    stored_path: Mapped[str] = mapped_column(String(255))
    uploaded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Notification(Base):
    __tablename__ = "notifications"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    channel: Mapped[str] = mapped_column(String(10))
    phone: Mapped[str] = mapped_column(String(32), default="")
    rendered_text: Mapped[str] = mapped_column(Text)
    read: Mapped[bool] = mapped_column(Boolean, default=False)
    ts: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class SupportTicket(Base):
    __tablename__ = "support_tickets"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    subject: Mapped[str] = mapped_column(String(160))
    message: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(16), default="open")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    closed_by: Mapped[int | None] = mapped_column(Integer, default=None)


class ExchangeRate(Base):
    __tablename__ = "exchange_rates"

    id: Mapped[int] = mapped_column(primary_key=True)
    from_cur: Mapped[str] = mapped_column(String(3))
    to_cur: Mapped[str] = mapped_column(String(3))
    rate: Mapped[float] = mapped_column(Float)


class Payment(Base):
    __tablename__ = "payments"

    id: Mapped[int] = mapped_column(Integer, Identity(start=5001, increment=1), primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    type: Mapped[str] = mapped_column(String(12))
    from_account: Mapped[int] = mapped_column(Integer)
    recipient_account: Mapped[int] = mapped_column(Integer)
    amount: Mapped[float] = mapped_column(Float)
    fee: Mapped[float] = mapped_column(Float, default=0.0)
    currency: Mapped[str] = mapped_column(String(3))
    channel: Mapped[str | None] = mapped_column(String(12), default=None)
    recipient_value: Mapped[str | None] = mapped_column(String(64), default=None)
    recipient_masked: Mapped[str] = mapped_column(String(80), default="")
    recipient_full_name: Mapped[str] = mapped_column(String(160), default="")
    description: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String(12), default="new")
    reject_reason: Mapped[str | None] = mapped_column(Text, default=None)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    executed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)


class PaymentTemplate(Base):
    __tablename__ = "payment_templates"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    name: Mapped[str] = mapped_column(String(120))
    type: Mapped[str] = mapped_column(String(12))
    recipient_value: Mapped[str | None] = mapped_column(String(64), default=None)
    recipient_account: Mapped[int | None] = mapped_column(Integer, default=None)
    amount: Mapped[float] = mapped_column(Float, default=0.0)


class PromoCode(Base):
    __tablename__ = "promo_codes"

    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(40), unique=True)
    amount: Mapped[float] = mapped_column(Float)
    currency: Mapped[str] = mapped_column(String(3))


class Challenge(Base):
    __tablename__ = "challenges"

    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(40), unique=True)
    title: Mapped[str] = mapped_column(String(160))
    category: Mapped[str] = mapped_column(String(40))
    points: Mapped[int] = mapped_column(Integer)
    flag: Mapped[str] = mapped_column(String(200))
    hint: Mapped[str | None] = mapped_column(Text, default=None)


class Solve(Base):
    __tablename__ = "solves"

    id: Mapped[int] = mapped_column(primary_key=True)
    nickname: Mapped[str] = mapped_column(String(60))
    challenge_id: Mapped[int] = mapped_column(ForeignKey("challenges.id"))
    ts: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class AuditEntry(Base):
    __tablename__ = "audit_entries"

    id: Mapped[int] = mapped_column(primary_key=True)
    ts: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    actor: Mapped[str] = mapped_column(String(160))
    action: Mapped[str] = mapped_column(String(400))
