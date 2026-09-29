# OnlineBank — architecture

```
                        host ports
:9080 ──► web (nginx + Vue 3 SPA)          :9500 ──► sms-gateway (open inboxes)
              │  /api/* , /uploads/                      ▲
              ▼  (internal)                              │ POST /send
        backend (FastAPI :9000) ─────────────────────────┘
              │                │
              ▼                ▼  http://169.254.169.254  (extra_hosts entry)
        db (PostgreSQL)   metadata (fake IMDSv1, static ip 172.28.0.10)
```

## Services

| Service | Tech | Role |
|---|---|---|
| `web` | nginx:1.27 + Vue 3/Vite bundle | static SPA, reverse proxy for `/api` and `/uploads`; appends `X-Forwarded-For` (the leftmost value is client-controlled — see RATE-1) |
| `backend` | FastAPI, SQLAlchemy 2, sync endpoints (threadpool → real parallelism for the race) | the banking API `/api/v1/*`, shadow `/api/v0/*`, GraphQL `/api/v1/graphql`, docs at `/api/v1/docs` |
| `db` | PostgreSQL 16 | all state; seeded on first boot (`backend/app/seed.py`) |
| `sms-gateway` | FastAPI, in-memory store | OTP delivery; per-phone inboxes; no auth by design |
| `metadata` | FastAPI on :80 inside the compose network | IMDSv1 emulation; reachable as `169.254.169.254` via the static-IP + `extra_hosts` trick |

## Why PostgreSQL

SQLite cannot demonstrate the race honestly (database-level locking and no
concurrent writers). PostgreSQL gives real concurrent transactions, so the
check-then-act flaw in `exchange/convert` produces a genuine negative balance.

## Data model (main tables)

- `users` — login, pbkdf2 password hash, phone, `role`, `is_backoffice`,
  `daily_limit`, `token_version`, `internal_note` (profile CRM note),
  `secret_note` (GraphQL-only field).
- `accounts` — ids from 1001 (Identity seed), currency (USD/EUR/GHS),
  balance (float — the parsing flaws need sub-cent values), `risk_score`,
  `is_internal`.
- `transactions` — direction, amount, description (XSS sink, rendered with
  `v-html`), counterparty, status (`completed`/`cancelled` — the cashback bug).
- `cards` — full PAN, CVV, expiry, `note` (holds the SQLi flag row).
- `otp_challenges` — challenge id, user, phone, 4-digit code, expiry, used.
- `cashback_campaigns` / `user_cashbacks` — public and personalized (owner)
  campaigns; settlement hook counts cancelled transactions.
- `webhooks` — user-controlled URLs (SSRF sink with body preview).
- `kyc_documents`, `notifications` (rendered SMS texts — SSTI sink),
  `support_tickets` (stored XSS into the operator console), `beneficiaries`,
  `exchange_rates` (deliberately inconsistent one-way pairs).
- `challenges` (title, category, points, flag, hint) / `solves` — the
  progress panel: per-nickname accepted flags (persisted in the DB).

## Flags

Seeded from environment variables (see `docker-compose.yml`); defaults are
stable strings like `FLAG{race-negative-balance}`. Server-side-only files
(`SECRETS_DIR`, default `/app/secret`) hold the XXE and RCE flags; the
metadata service holds the SSRF flag; the rest live in the database and are
revealed only through the corresponding vulnerability.

## Extending the stand

- Add a vulnerability: new router or weak decision, a row in
  `seed.py` challenges, a section in VULNERABILITIES/SOLUTIONS, optionally a
  check in `scripts/smoke.sh`.
