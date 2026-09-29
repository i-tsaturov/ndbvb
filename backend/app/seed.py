"""Demo data. Runs on every boot when the database is empty."""
import os
from datetime import timedelta

from .db import SessionLocal, engine
from .models import utcnow
from .models import (
    Account,
    Beneficiary,
    Card,
    CashbackCampaign,
    Challenge,
    ExchangeRate,
    Notification,
    SupportTicket,
    Transaction,
    User,
    Webhook,
)
from .passwords import hash_password

HINTS = {
    "jwt": "What algorithms does the token verifier accept?",
    "idor": "Account ids are small integers; swap one in a request the app already makes.",
    "massassign": "The profile PATCH echoes back everything it stored — try fields the edit form never shows.",
    "race": "A conversion takes a third of a second — what happens between the check and the write?",
    "sqli": "The statement search box becomes part of a SQL query.",
    "xss": "Somebody renders rich text from other people — who reads it in their console?",
    "xxe": "The statement import accepts XML 'for legacy corporate clients'.",
    "rce": "Two legacy import formats are accepted; one of them is not XML.",
    "ssrf": "The bank calls URLs you control — twice.",
    "shadow": "robots.txt tells crawlers what to avoid — so visit exactly that.",
    "graphql": "There is a second API style on the same host, and it loves to describe itself.",
}

def _random_flag() -> str:
    import secrets

    return "FLAG{" + secrets.token_hex(8) + "}"


def _initial_flags() -> dict:
    """Per-installation flags (SPEC 16): env override wins (docker-compose
    pins stable literals for reproducibility); otherwise random on first
    init and persisted in the challenges table forever after."""
    keys = ("FLAG_IDOR", "FLAG_SQLI", "FLAG_XXE", "FLAG_RCE", "FLAG_SSRF",
            "FLAG_JWT", "FLAG_SHADOW", "FLAG_RACE", "FLAG_XSS",
            "FLAG_MASSASSIGN", "FLAG_GRAPHQL")
    flags = {}
    for key in keys:
        env = os.environ.get(key)
        if env:
            flags[key] = env
            continue
        try:
            from .db import SessionLocal
            from .models import Challenge

            db = SessionLocal()
            try:
                code_map = {"JWT": "jwt", "IDOR": "idor",
                            "MASSASSIGN": "massassign", "RACE": "race",
                            "SQLI": "sqli", "XSS": "xss", "XXE": "xxe",
                            "RCE": "rce", "SSRF": "ssrf", "SHADOW": "shadow",
                            "GRAPHQL": "graphql"}
                row = db.query(Challenge).filter(
                    Challenge.code == code_map[key.replace("FLAG_", "")]).first()
                if row:
                    flags[key] = row.flag
                    continue
            finally:
                db.close()
        except Exception:
            pass
        flags[key] = _random_flag()
    return flags


FLAGS = _initial_flags()

DEMO_PASSWORD = "OnlineBank!123"


def registered_flags() -> dict:
    """flag_key -> value as stored in the challenges table (falls back to
    the process FLAGS when the table is not seeded yet)."""
    from .db import SessionLocal
    from .models import Challenge

    code_to_key = {"jwt": "JWT", "idor": "IDOR",
                   "massassign": "MASSASSIGN", "race": "RACE", "sqli": "SQLI",
                   "xss": "XSS", "xxe": "XXE", "rce": "RCE", "ssrf": "SSRF",
                   "shadow": "SHADOW", "graphql": "GRAPHQL"}
    out = dict(FLAGS)
    try:
        db = SessionLocal()
        try:
            for row in db.query(Challenge).all():
                key = code_to_key.get(row.code)
                if key:
                    out[f"FLAG_{key}"] = row.flag
        finally:
            db.close()
    except Exception:
        pass
    return out


def write_secret_files() -> None:
    """Local secret files for the stand."""
    secret_dir = os.environ.get("SECRETS_DIR", "/app/secret")
    os.makedirs(secret_dir, exist_ok=True)
    stored = registered_flags()
    for name in ("XXE", "RCE"):
        with open(os.path.join(secret_dir, f"flag_{name.lower()}.txt"), "w") as fh:
            fh.write(stored[f"FLAG_{name}"] + "\n")


def migrate() -> None:
    """Lightweight column additions for databases created before the hint
    field existed (create_all never alters existing tables)."""
    from sqlalchemy import text

    with engine.begin() as conn:
        conn.execute(text("ALTER TABLE challenges ADD COLUMN IF NOT EXISTS hint TEXT"))
        conn.execute(text("ALTER TABLE cards ADD COLUMN IF NOT EXISTS kind VARCHAR(10) DEFAULT 'debit'"))
        conn.execute(text("ALTER TABLE cards ADD COLUMN IF NOT EXISTS virtual BOOLEAN DEFAULT TRUE"))
        conn.execute(text("ALTER TABLE cards ADD COLUMN IF NOT EXISTS closed BOOLEAN DEFAULT FALSE"))
        conn.execute(text("ALTER TABLE accounts ADD COLUMN IF NOT EXISTS kind VARCHAR(12) DEFAULT 'current'"))
        conn.execute(text("ALTER TABLE accounts ADD COLUMN IF NOT EXISTS status VARCHAR(12) DEFAULT 'active'"))
        conn.execute(text("ALTER TABLE users ADD COLUMN IF NOT EXISTS kyc_status VARCHAR(12) DEFAULT 'not_verified'"))
        conn.execute(text("ALTER TABLE user_cashbacks ADD COLUMN IF NOT EXISTS card_id INTEGER REFERENCES cards(id)"))
        conn.execute(text("ALTER TABLE notifications ADD COLUMN IF NOT EXISTS read BOOLEAN DEFAULT FALSE"))
        for code, hint in HINTS.items():
            conn.execute(
                text("UPDATE challenges SET hint = :h WHERE code = :c AND hint IS NULL"),
                {"h": hint, "c": code},
            )


def seed() -> None:
    migrate()
    db = SessionLocal()
    if db.query(User).count() > 0:
        db.close()
        return
    try:
        pwd = hash_password(DEMO_PASSWORD)
        now = utcnow()

        def user(login, first, last, phone, **kw):
            u = User(
                login=login, password_hash=pwd, first_name=first, last_name=last,
                phone=phone, **kw,
            )
            db.add(u)
            db.flush()
            return u

        ama = user("ama@onlinebank.app", "Amara", "Mensah", "+233501234567", daily_limit=5000)
        jdoe = user("jdoe@onlinebank.app", "John", "Doe", "+233502345678", daily_limit=3000)
        cto = user("cto@onlinebank.app", "Kwame", "Boateng", "+233503456789",
                   daily_limit=100000,
                   internal_note="VIP: concierge banking, fee waivers pre-approved")
        ops = user("ops@onlinebank.app", "Ops", "Console", "+233500000000",
                   role="backoffice", is_backoffice=True, daily_limit=0)
        filler = [
            ("akwasi@onlinebank.app", "Akwasi", "Osei", "+233504455661", FLAGS["FLAG_GRAPHQL"]),
            ("abena@onlinebank.app", "Abena", "Asante", "+233504455662", None),
            ("yaw@onlinebank.app", "Yaw", "Darko", "+233504455663", None),
            ("akosua@onlinebank.app", "Akosua", "Nkrumah", "+233504455664", None),
            ("fatima@onlinebank.app", "Fatima", "Yakubu", "+233504455665", None),
            ("emeka@onlinebank.app", "Emeka", "Okoro", "+233504455666", None),
            ("ngozi@onlinebank.app", "Ngozi", "Eze", "+233504455667", None),
            ("chidi@onlinebank.app", "Chidi", "Balogun", "+233504455668", None),
        ]
        others = [user(*row[:4], secret_note=row[4]) for row in filler]

        def account(owner, currency, balance, risk=1, internal=False):
            a = Account(user_id=owner.id, currency=currency, balance=balance,
                        risk_score=risk, is_internal=internal,
                        opened_at=now - timedelta(days=400))
            db.add(a)
            db.flush()
            return a

        a1001 = account(ama, "USD", 5430.20)
        a1002 = account(ama, "GHS", 12500.00, risk=2)
        a1003 = account(jdoe, "EUR", 310.55)
        a1004 = account(cto, "USD", 98211.00)
        a1005 = account(jdoe, "USD", 1200.00)
        a1006 = account(ops, "USD", 500.00)
        filler_accounts = [
            account(u, "USD", round(800 + 610 * i, 2), risk=(i % 5) + 1)
            for i, u in enumerate(others)
        ]

        def tx(acc, direction, amount, cur, desc, counterparty, days, status="completed"):
            db.add(Transaction(
                account_id=acc.id, ts=now - timedelta(days=days), direction=direction,
                amount=amount, currency=cur, description=desc,
                counterparty=counterparty, status=status,
            ))

        tx(a1001, "credit", 3200.00, "USD", "Salary - August", "Payroll Ghana Ltd", 35)
        tx(a1001, "debit", 48.20, "USD", "Coffee House - Accra Mall", "Coffee House", 32)
        tx(a1001, "debit", 129.99, "USD", "Supermarket weekly basket", "Mart Plus", 30)
        tx(a1001, "credit", 500.00, "USD", "Incoming transfer", "J. Doe", 27)
        tx(a1001, "debit", 15.00, "USD", "Streaming subscription", "StreamCo", 25)
        tx(a1001, "debit", 60.00, "USD", "Fuel - Shell Osu", "Shell", 21)
        tx(a1001, "debit", 220.00, "USD", "Flight ACC-LOS-ACC", "Air Ghana", 18)
        tx(a1001, "credit", 3200.00, "USD", "Salary - September", "Payroll Ghana Ltd", 5)
        tx(a1001, "debit", 12.50, "USD", "Coffee House - Airport City", "Coffee House", 3)
        tx(a1002, "debit", 400.00, "GHS", "Utilities - ECG", "ECG", 20)
        tx(a1002, "credit", 6000.00, "GHS", "Mobile money top-up", "MTN MoMo", 15)
        tx(a1003, "debit", 89.45, "EUR", "Amazon.de order", "Amazon", 22)
        tx(a1003, "credit", 400.00, "EUR", "Freelance invoice #221", "EU Client GmbH", 10)
        tx(a1004, "debit", 25000.00, "USD", "Board dividend distribution — ref " + FLAGS["FLAG_IDOR"],
           "Corporate Treasury", 8)
        tx(a1004, "credit", 100000.00, "USD", "Term deposit maturity", "Treasury Ops", 60)
        tx(a1005, "debit", 25.00, "USD", "Pharmacy", "CarePlus", 12)
        tx(a1005, "credit", 75.00, "USD", "Refund — double charge", "Mart Plus", 6, status="cancelled")
        tx(a1005, "debit", 45.00, "USD", "Restaurant - Cantonments", "Bistro 5", 2)

        for i, fa in enumerate(filler_accounts):
            tx(fa, "credit", round(1200 + 130 * i, 2), "USD", "Salary — monthly", "Payroll Ghana Ltd", 24 - i)
            tx(fa, "debit", round(46.10 + 9 * i, 2), "USD", "Supermarket weekly basket", "Mart Plus", 15 - i % 8)
            tx(fa, "debit", 14.50, "USD", "Pharmacy", "CarePlus", 8 - i % 6)
            tx(fa, "credit", round(60.00 + 25 * i, 2), "USD", "Incoming transfer", "OnlineBank customer", 4 - i % 3)
        tx(a1006, "credit", 500.00, "USD", "Platform fee settlement", "OnlineBank Processing", 9)
        tx(a1006, "debit", 120.00, "USD", "Sandbox service costs", "Cloud vendor", 3)

        db.add(Card(user_id=ama.id, pan="4111111111111111", cvv="123", expiry="09/28",
                    holder="AMARA MENSAH", account_id=a1001.id))
        db.add(Card(user_id=ama.id, pan="5555555555554444", cvv="456", expiry="03/27",
                    holder="AMARA MENSAH", account_id=a1001.id))
        db.add(Card(user_id=jdoe.id, pan="4242424242424242", cvv="789", expiry="12/26",
                    holder="JOHN DOE", note=FLAGS["FLAG_SQLI"], account_id=a1005.id))
        db.add(Card(user_id=cto.id, pan="5500005555555559", cvv="321", expiry="05/29",
                    holder="KWAME BOATENG", account_id=a1004.id))

        for pair, rate in [
            (("USD", "GHS"), 15.25),
            (("GHS", "USD"), 0.0660),
            (("USD", "EUR"), 0.92),
            (("EUR", "USD"), 1.09),
            (("EUR", "GHS"), 16.60),
            (("GHS", "EUR"), 0.0605),
        ]:
            db.add(ExchangeRate(from_cur=pair[0], to_cur=pair[1], rate=rate))

        db.add(CashbackCampaign(title="Coffee lovers", category="coffee", percent=3.0))
        db.add(CashbackCampaign(title="Fuel cashback", category="fuel", percent=5.0))
        db.add(CashbackCampaign(title="Travel premium", category="travel", percent=10.0,
                                personalized=True, owner_id=ama.id))
        db.add(CashbackCampaign(title="Private banking select", category="private", percent=15.0,
                                personalized=True, owner_id=cto.id))
        db.add(CashbackCampaign(title="Groceries", category="groceries", percent=2.0))
        db.add(CashbackCampaign(title="Streaming 1%", category="streaming", percent=1.0,
                                active=False))

        db.add(Beneficiary(user_id=ama.id, name="John Doe", account_id=a1005.id, confirmed=True))
        db.add(Beneficiary(user_id=ama.id, name="Kwame Boateng", account_id=a1004.id, confirmed=False))

        db.add(Webhook(user_id=ama.id, url="https://example.com/onlinebank-hook",
                       event="transfer.completed"))

        db.add(SupportTicket(user_id=jdoe.id, subject="Card charged twice",
                             message="Coffee House charged my card twice on the same day. "
                                     "Please review the duplicate debit."))
        db.add(SupportTicket(user_id=ama.id, subject="Statement August",
                             message="Please re-send the August statement for account 1001."))

        from .models import PromoCode
        db.add(PromoCode(code="WELCOME10", amount=10.0, currency="USD"))
        db.add(PromoCode(code="GHSLIFE", amount=25.0, currency="GHS"))
        db.add(PromoCode(code="VIP100", amount=100.0, currency="USD"))

        db.add(Notification(user_id=ama.id, channel="sms", phone=ama.phone,
                            rendered_text="Dear Amara, your OnlineBank profile was updated. "
                                          "If this was not you, call +233 30 000 0000."))
        db.add(Notification(user_id=ama.id, channel="push",
                            rendered_text="Your salary 3200.00 USD was credited to account 1001.",
                            ts=now - timedelta(days=5)))
        db.add(Notification(user_id=ama.id, channel="push",
                            rendered_text="New login: Chrome on macOS, Accra. "
                                          "If this was not you, call +233 30 000 0000.",
                            ts=now - timedelta(days=2)))
        db.add(Notification(user_id=jdoe.id, channel="push",
                            rendered_text="Your card ending 4242 was charged twice at Coffee House. "
                                          "The refund is on its way.",
                            ts=now - timedelta(days=4)))

        savings_acc = Account(user_id=ama.id, currency="USD", kind="savings", balance=8200.00, apr=4.5)
        db.add(savings_acc)
        goal = Account(user_id=ama.id, currency="GHS", kind="goal", balance=1500.0,
                       target_amount=5000.0)
        db.add(goal)
        db.flush()
        db.add(Transaction(account_id=goal.id, ts=now - timedelta(days=10), direction="credit",
                           amount=1500.0, currency="GHS", description="Goal deposit: Japan trip",
                           counterparty="Amara Mensah"))
        credit_acc = Account(user_id=ama.id, currency="USD", kind="credit", balance=1000.0,
                             credit_limit=1000.0)
        db.add(credit_acc)
        db.flush()
        tx(savings_acc, "credit", 8000.00, "USD", "Opening deposit", "Amara Mensah", 95)
        for m in range(3, 0, -1):
            tx(savings_acc, "credit", round(8200 * 4.5 / 100 / 12, 2), "USD",
               "Interest capitalization", "OnlineBank", m * 28 + 2)
        tx(credit_acc, "debit", 210.00, "USD", "Card purchase - Electronics", "TechHub", 40)
        tx(credit_acc, "debit", 85.30, "USD", "Card purchase - Restaurant", "Bistro 5", 33)
        tx(credit_acc, "credit", 200.00, "USD", "Card repayment", "Amara Mensah", 27)
        tx(credit_acc, "debit", round(295.30 * 18 / 100 / 12, 2), "USD",
           "Credit interest charge", "OnlineBank", 20)

        extra = [
            ("esi@onlinebank.app", "Esi", "Quartey", "+233505550601", "USD", "savings", 3400.0),
            ("kofi@onlinebank.app", "Kofi", "Asante", "+233505550602", "GHS", "goal", 700.0),
            ("amina@onlinebank.app", "Amina", "Suleiman", "+233505550603", "USD", "credit", 500.0),
            ("kojo@onlinebank.app", "Kojo", "Amankwah", "+233505550604", "EUR", "current", 950.0),
            ("zainab@onlinebank.app", "Zainab", "Musah", "+233505550605", "USD", "current", 2210.0),
            ("kwabena@onlinebank.app", "Kwabena", "Owusu", "+233505550606", "GHS", "savings", 6100.0),
            ("afi@onlinebank.app", "Afi", "Dogbe", "+233505550607", "USD", "goal", 240.0),
            ("yaw2@onlinebank.app", "Yaw", "Boateng", "+233505550608", "USD", "savings", 15800.0),
        ]
        for i, (login_, first, last, phone, cur, kind, bal) in enumerate(extra):
            u = user(login_, first, last, phone)
            kw = {}
            if kind == "savings":
                kw["apr"] = 3.5 + (i % 3)
            if kind == "goal":
                kw["target_amount"] = bal * 4
            if kind == "credit":
                kw["credit_limit"] = 500.0
            acc = Account(user_id=u.id, currency=cur, kind=kind, balance=bal, **kw)
            db.add(acc)
            db.flush()
            for d in range(1, 5):
                db.add(Transaction(
                    account_id=acc.id, ts=now - timedelta(days=d * 9),
                    direction="debit", amount=round(15 + d * 7.5, 2), currency=cur,
                    description="POS purchase", counterparty="Mart Plus"))
            db.add(Transaction(
                account_id=acc.id, ts=now - timedelta(days=2), direction="credit",
                amount=round(bal / 3, 2), currency=cur, description="Incoming transfer",
                counterparty="Account 1005"))

        for code, title, cat, pts, flag_key in [
                ("jwt", "Forge a back-office token", "Cryptography", 300, "JWT"),
            ("idor", "Read another customer's statement", "Access Control", 150, "IDOR"),
            ("massassign", "Escalate your own role", "Access Control", 250, "MASSASSIGN"),
            ("race", "Drive an account balance below zero", "Business Logic", 300, "RACE"),
            ("sqli", "Dump the card vault through search", "Injection", 200, "SQLI"),
            ("xss", "Steal the operator console flag", "Injection", 250, "XSS"),
            ("xxe", "Read a server file through XML import", "Injection", 250, "XXE"),
            ("rce", "Execute code through the legacy import", "Injection", 350, "RCE"),
            ("ssrf", "Fetch the instance credentials", "Server-Side Request", 250, "SSRF"),
            ("shadow", "Find the forgotten debug API", "Configuration", 150, "SHADOW"),
            ("graphql", "Read a secret through GraphQL", "Configuration", 150, "GRAPHQL"),
        ]:
            db.add(Challenge(code=code, title=title, category=cat, points=pts,
                             flag=FLAGS["FLAG_" + flag_key], hint=HINTS[code]))

        db.commit()
        print("[seed] demo data created")
    finally:
        db.close()
