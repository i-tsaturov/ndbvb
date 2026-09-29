"""Accounts, balances, statements."""

from datetime import date, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response
from pydantic import BaseModel
from sqlalchemy import text

from ..db import get_db
from ..parsing import round_credit
from ..pdfgen import build_pdf, paginate
from ..models import Account, Transaction, User, utcnow
from ..security import get_current_user

router = APIRouter(prefix="/api/v1/accounts", tags=["accounts"])


ACCOUNT_NAMES = {"USD": "Everyday account", "EUR": "Euro wallet", "GHS": "Cedi wallet"}


def account_body(a: Account) -> dict:
    name = ACCOUNT_NAMES.get(a.currency, a.currency)
    if a.kind != "current":
        name = f"{a.kind.capitalize()} {a.currency}"
    return {
        "id": a.id,
        "number": f"40817810{a.id:07d}",
        "name": name,
        "currency": a.currency,
        "kind": a.kind,
        "status": a.status,
        "balance": round(a.balance, 2),
        "apr": a.apr,
        "target_amount": a.target_amount,
        "credit_limit": a.credit_limit,
        "debt": round(a.debt, 2),
    }


@router.get("", summary="List my active accounts")
def my_accounts(user: User = Depends(get_current_user), db=Depends(get_db)):
    accounts = (
        db.query(Account)
        .filter(Account.user_id == user.id, Account.status == "active")
        .order_by(Account.id)
        .all()
    )
    return [account_body(a) for a in accounts]


class OpenAccountBody(BaseModel):
    currency: str
    kind: str = "current"
    apr: float | None = None
    target_amount: float | None = None
    credit_limit: float | None = None


@router.post("", status_code=200, summary="Open a new account (current/savings/goal/credit)")
def open_account(body: OpenAccountBody,
                 user: User = Depends(get_current_user), db=Depends(get_db)):
    if body.currency not in ("USD", "EUR", "GHS"):
        raise HTTPException(status_code=422, detail="Unsupported currency")
    if body.kind not in ("current", "savings", "goal", "credit"):
        raise HTTPException(status_code=422, detail="Unsupported account kind")
    apr = body.apr if body.apr is not None else (4.0 if body.kind == "savings" else 0.0)
    target = body.target_amount
    limit = body.credit_limit if body.credit_limit is not None else (1000.0 if body.kind == "credit" else 0.0)
    if body.kind == "goal" and not (target and target > 0):
        raise HTTPException(status_code=422, detail="Goals need a target amount")
    if body.kind == "credit" and limit <= 0:
        raise HTTPException(status_code=422, detail="Credit accounts need a positive limit")
    if apr < 0:
        raise HTTPException(status_code=422, detail="apr must be >= 0")
    balance = limit if body.kind == "credit" else 0.0
    account = Account(user_id=user.id, currency=body.currency, kind=body.kind,
                      balance=balance, status="active", apr=apr,
                      target_amount=target, credit_limit=limit)
    db.add(account)
    db.commit()
    return account_body(account)


@router.post("/interest", summary="Interest accrual job (savings, monthly rate)")
def interest_job(user: User = Depends(get_current_user), db=Depends(get_db)):
    payouts = []
    for account in db.query(Account).filter(Account.kind == "savings",
                                            Account.status == "active").all():
        if account.balance <= 0 or account.apr <= 0:
            continue
        bonus = round_credit(account.balance * account.apr / 100 / 12)
        account.balance += bonus
        db.add(Transaction(
            account_id=account.id, ts=utcnow(), direction="credit", amount=bonus,
            currency=account.currency, description="Interest capitalization",
            counterparty="OnlineBank",
        ))
        payouts.append({"account": account.id, "amount": bonus})
    db.commit()
    return {"status": "accrued", "payouts": payouts}


@router.post("/{account_id}/close", summary="Close an empty account")
def close_account(account_id: int,
                  user: User = Depends(get_current_user), db=Depends(get_db)):
    account = db.get(Account, account_id)
    if not account:
        raise HTTPException(status_code=404, detail="Account not found")
    if account.status == "closed":
        raise HTTPException(status_code=409, detail="Account is closed")
    if round(account.balance, 2) != 0.0:
        raise HTTPException(status_code=422, detail="Account must be empty before closing")
    account.status = "closed"
    db.commit()
    return {"id": account.id, "status": account.status}


@router.get("/{account_id}/requisites", summary="Transfer requisites")
def requisites(account_id: int,
               user: User = Depends(get_current_user), db=Depends(get_db)):
    account = db.get(Account, account_id)
    if not account:
        raise HTTPException(status_code=404, detail="Account not found")
    owner = db.get(User, account.user_id)
    return {
        "account_id": account.id,
        "owner_full_name": f"{owner.first_name} {owner.last_name}",
        "currency": account.currency,
        "bank": "OnlineBank Ltd.",
        "bic": "ONLNGHAC",
        "swift": "ONLNGHACXXX",
        "correspondent_account": "30101810400000000541",
    }


@router.get("/{account_id}", summary="Account details")
def account_details(account_id: int, user: User = Depends(get_current_user), db=Depends(get_db)):
    account = db.get(Account, account_id)
    if not account:
        raise HTTPException(status_code=404, detail="Account not found")
    owner = db.get(User, account.user_id)
    body = account_body(account)
    body.update({
        "risk_score": account.risk_score,
        "is_internal": account.is_internal,
        "opened_at": account.opened_at.isoformat(),
        "owner": {
            "login": owner.login,
            "first_name": owner.first_name,
            "last_name": owner.last_name,
            "phone": owner.phone,
        },
    })
    return body


@router.get("/{account_id}/balance", summary="Account balance")
def balance(account_id: int, user: User = Depends(get_current_user), db=Depends(get_db)):
    account = db.get(Account, account_id)
    if not account:
        raise HTTPException(status_code=404, detail="Account not found")
    return {"account_id": account.id, "currency": account.currency,
            "balance": round(account.balance, 2)}


@router.get("/{account_id}/transactions", summary="Transactions (search/sort)")
def transactions(
    account_id: int,
    search: str = "",
    sort: str = "",
    limit: int = 100,
    user: User = Depends(get_current_user),
    db=Depends(get_db),
):
    account = db.get(Account, account_id)
    if not account:
        raise HTTPException(status_code=404, detail="Account not found")
    limit = max(0, min(limit, 500))
    order = sort if sort else "ts DESC"
    sql = text(
        "SELECT id, ts, direction, amount, currency, description, counterparty, status "
        f"FROM transactions WHERE account_id = {account_id} "
        f"AND (description ILIKE '%{search}%' OR counterparty ILIKE '%{search}%') "
        f"ORDER BY {order} LIMIT {limit}"
    )
    rows = db.execute(sql).mappings().all()
    return {
        "account_id": account_id,
        "count": len(rows),
        "transactions": [
            {
                "id": r["id"],
                "ts": r["ts"].isoformat() if r["ts"] is not None else None,
                "direction": r["direction"],
                "amount": r["amount"],
                "currency": r["currency"],
                "description": r["description"],
                "counterparty": r["counterparty"],
                "status": r["status"],
            }
            for r in rows
        ],
    }


STATEMENT_FIELDS = ("date", "description", "counterparty", "amount", "status")


def _fields_param(fields: str) -> list[str]:
    if not fields:
        return list(STATEMENT_FIELDS)
    selected = [f.strip() for f in fields.split(",") if f.strip()]
    unknown = [f for f in selected if f not in STATEMENT_FIELDS]
    if unknown:
        raise HTTPException(status_code=422, detail=f"Unknown fields: {', '.join(unknown)}")
    return selected


def _statement_rows(db, account_id: int, from_d: date, to_d: date):
    sql = text(
        "SELECT ts, description, counterparty, direction, amount, currency, status "
        "FROM transactions WHERE account_id = :a AND ts >= :f AND ts < :t "
        "ORDER BY ts"
    )
    return db.execute(sql, {"a": account_id, "f": from_d, "t": to_d + timedelta(days=1)}).mappings().all()


def _net(rows) -> float:
    return sum(r["amount"] if r["direction"] == "credit" else -r["amount"] for r in rows)


def _money(v: float) -> str:
    return f"{v:,.2f}"


def _period(from_: str, to: str) -> tuple[date, date]:
    """Statement period with clean 422s for malformed dates (YYYY-MM-DD)."""
    try:
        to_d = date.fromisoformat(to) if to else date.today()
        from_d = date.fromisoformat(from_) if from_ else to_d - timedelta(days=30)
    except ValueError:
        raise HTTPException(status_code=422, detail="Invalid date, use YYYY-MM-DD")
    return from_d, to_d


@router.get("/{account_id}/statement.pdf", summary="Account statement PDF (selectable fields)")
def statement_pdf(account_id: int, from_: str = Query("", alias="from"), to: str = "",
                  fields: str = Query("", alias="fields"),
                  user: User = Depends(get_current_user), db=Depends(get_db)):
    selected = _fields_param(fields)
    account = db.get(Account, account_id)
    if not account:
        raise HTTPException(status_code=404, detail="Account not found")
    owner = db.get(User, account.user_id)
    from_d, to_d = _period(from_, to)
    rows = _statement_rows(db, account_id, from_d, to_d)

    later = db.execute(
        text("SELECT direction, amount FROM transactions WHERE account_id = :a AND ts >= :t"),
        {"a": account_id, "t": to_d + timedelta(days=1)},
    ).mappings().all()
    closing = account.balance - sum(
        r["amount"] if r["direction"] == "credit" else -r["amount"] for r in later)
    opening = closing - _net(rows)
    total_debit = sum(r["amount"] for r in rows if r["direction"] == "debit")
    total_credit = sum(r["amount"] for r in rows if r["direction"] == "credit")

    columns = {
        "date": lambda r: r["ts"].strftime("%Y-%m-%d"),
        "description": lambda r: str(r["description"])[:32],
        "counterparty": lambda r: str(r["counterparty"])[:24],
        "status": lambda r: r["status"],
    }

    def debit_cell(r):
        return _money(r["amount"]) if r["direction"] == "debit" else ""

    def credit_cell(r):
        return _money(r["amount"]) if r["direction"] == "credit" else ""

    headers, cell_fns = [], []
    for f in selected:
        if f == "amount":
            headers += ["Debit", "Credit"]
            cell_fns += [debit_cell, credit_cell]
        else:
            headers.append(f.capitalize())
            cell_fns.append(columns[f])
    header = "  ".join(f"{h:12}" for h in headers)
    lines = [
        "OnlineBank", "Account statement", "",
        f"Holder: {owner.first_name} {owner.last_name}",
        f"Account: {account.id} ({account.currency})",
        f"Period: {from_d.isoformat()} - {to_d.isoformat()}",
        f"Opening balance: {_money(opening)} {account.currency}",
        f"Closing balance: {_money(closing)} {account.currency}", "",
        header,
    ]
    for r in rows:
        cells = [fn(r) for fn in cell_fns]
        lines.append("  ".join(f"{c:12}" for c in cells))
    lines += ["", f"Total debited:  {_money(total_debit)} {account.currency}",
              f"Total credited: {_money(total_credit)} {account.currency}"]
    pdf = build_pdf(paginate(lines))
    return Response(pdf, media_type="application/pdf",
                    headers={"Content-Disposition":
                             f'attachment; filename="statement-{account.id}.pdf"'})


@router.get("/{account_id}/statement.csv", summary="Account statement CSV (selectable fields)")
def statement_csv(account_id: int, from_: str = Query("", alias="from"), to: str = "",
                  fields: str = Query("", alias="fields"),
                  user: User = Depends(get_current_user), db=Depends(get_db)):
    account = db.get(Account, account_id)
    if not account:
        raise HTTPException(status_code=404, detail="Account not found")
    selected = _fields_param(fields)
    from_d, to_d = _period(from_, to)
    rows = _statement_rows(db, account_id, from_d, to_d)
    out = [",".join(selected)]
    for r in rows:
        cells = {
            "date": r["ts"].strftime("%Y-%m-%d"),
            "description": f'"{str(r["description"]).replace(chr(34), chr(39))}"',
            "counterparty": f'"{str(r["counterparty"]).replace(chr(34), chr(39))}"',
            "amount": str(r["amount"]),
            "status": r["status"],
        }
        out.append(",".join(cells[f] for f in selected))
    return Response("\n".join(out) + "\n", media_type="text/csv",
                    headers={"Content-Disposition":
                             f'attachment; filename="statement-{account.id}.csv"'})
