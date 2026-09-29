"""Debit/credit application with per-account-kind semantics (SPEC 12).

Balances always move with RELATIVE SQL updates (balance = balance ± x) so
concurrent operations stack instead of overwriting each other; credit-kind
debt tracking rides the same statements.
"""
from sqlalchemy import text


def apply_debit(db, account, amount: float) -> None:
    db.execute(
        text(
            "UPDATE accounts SET balance = balance - :x, "
            "debt = debt + (CASE WHEN kind = 'credit' THEN :x ELSE 0 END) "
            "WHERE id = :id"
        ),
        {"x": amount, "id": account.id},
    )


def apply_credit(db, account, amount: float) -> None:
    db.execute(
        text(
            "UPDATE accounts SET balance = balance + :x, "
            "debt = GREATEST(0, debt - (CASE WHEN kind = 'credit' THEN :x ELSE 0 END)) "
            "WHERE id = :id"
        ),
        {"x": amount, "id": account.id},
    )
