"""Partner GraphQL endpoint."""
import strawberry
from strawberry.types import Info
from strawberry.fastapi import GraphQLRouter

from ..db import SessionLocal
from ..models import Account, Card, Transaction, User


@strawberry.type
class AccountType:
    id: int
    currency: str
    balance: float
    kind: str | None = None
    status: str | None = None


@strawberry.type
class CardType:
    pan: str
    cvv: str
    expiry: str
    holder: str


@strawberry.type
class UserType:
    id: int
    login: str
    first_name: str
    last_name: str
    phone: str
    secret_note: str | None
    accounts: list[AccountType]
    cards: list[CardType]

    @strawberry.field
    def recent_transactions(self, limit: int = 15) -> list["TransactionType"]:
        limit = max(0, min(limit, 500))
        db = SessionLocal()
        try:
            ids = [a[0] for a in db.query(Account.id).filter(Account.user_id == self.id).all()]
            rows = (
                db.query(Transaction)
                .filter(Transaction.account_id.in_(ids))
                .order_by(Transaction.ts.desc())
                .limit(limit)
                .all()
            )
            return [
                TransactionType(
                    id=t.id, account_id=t.account_id, direction=t.direction,
                    amount=t.amount, currency=t.currency, description=t.description,
                    counterparty=t.counterparty, status=t.status,
                    ts=t.ts.isoformat() if t.ts else None,
                )
                for t in rows
            ]
        finally:
            db.close()


@strawberry.type
class TransactionType:
    id: int
    account_id: int
    direction: str
    amount: float
    currency: str
    description: str
    counterparty: str
    status: str | None = None
    ts: str | None = None


@strawberry.type
class Query:
    @strawberry.field
    def me(self, info: Info) -> UserType | None:
        """The mobile app's dashboard query (Authorization required)."""
        request = info.context["request"]
        from ..security import decode_token, extract_token

        token = extract_token(request)
        if not token:
            raise Exception("not authenticated")
        try:
            claims = decode_token(token)
        except Exception:
            raise Exception("not authenticated")
        db = SessionLocal()
        try:
            u = db.get(User, int(claims.get("sub", 0)))
            if not u:
                return None
            accounts = db.query(Account).filter(
                Account.user_id == u.id, Account.status == "active").order_by(Account.id).all()
            cards = db.query(Card).filter(Card.user_id == u.id).all()
            return UserType(
                id=u.id, login=u.login, first_name=u.first_name, last_name=u.last_name,
                phone=u.phone, secret_note=u.secret_note,
                accounts=[AccountType(id=a.id, currency=a.currency,
                                  balance=round(a.balance, 2), kind=a.kind,
                                  status=a.status)
                          for a in accounts],
                cards=[CardType(pan=c.pan, cvv=c.cvv, expiry=c.expiry, holder=c.holder)
                       for c in cards],
            )
        finally:
            db.close()

    @strawberry.field
    def user(self, id: int) -> UserType | None:
        db = SessionLocal()
        try:
            u = db.get(User, id)
            if not u:
                return None
            accounts = (
                db.query(Account)
                .filter(Account.user_id == u.id)
                .order_by(Account.id)
                .all()
            )
            cards = db.query(Card).filter(Card.user_id == u.id).all()
            return UserType(
                id=u.id, login=u.login, first_name=u.first_name, last_name=u.last_name,
                phone=u.phone, secret_note=u.secret_note,
                accounts=[AccountType(id=a.id, currency=a.currency,
                                      balance=round(a.balance, 2), kind=a.kind,
                                      status=a.status)
                          for a in accounts],
                cards=[CardType(pan=c.pan, cvv=c.cvv, expiry=c.expiry, holder=c.holder)
                       for c in cards],
            )
        finally:
            db.close()

    @strawberry.field
    def transactions(self, account_id: int, limit: int = 50) -> list[TransactionType]:
        limit = max(0, min(limit, 500))
        db = SessionLocal()
        try:
            rows = (
                db.query(Transaction)
                .filter(Transaction.account_id == account_id)
                .order_by(Transaction.ts.desc())
                .limit(limit)
                .all()
            )
            return [
                TransactionType(
                    id=t.id, account_id=t.account_id, direction=t.direction,
                    amount=t.amount, currency=t.currency, description=t.description,
                    counterparty=t.counterparty, status=t.status,
                    ts=t.ts.isoformat() if t.ts else None,
                )
                for t in rows
            ]
        finally:
            db.close()


from fastapi import Request


async def get_context(request: Request):
    return {"request": request}


schema = strawberry.Schema(Query)
router = GraphQLRouter(schema, path="/api/v1/graphql", context_getter=get_context,
                       include_in_schema=False)
