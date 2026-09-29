# NDBVB — not damn but vulnerable bank

**NDBVB** (not damn but vulnerable bank) is a training stand shaped like a real
retail bank: inside it is **OnlineBank**, a small bank (accounts, transfers,
currency exchange, cards, cashback, KYC, a back office for operators) where
**every feature is an API call** and the API carries the classic web
vulnerabilities that matter in banking.

> ⚠️ **This software is intentionally vulnerable.** Never expose it to the
> internet, never connect it to real data, never reuse its code. Training use
> only, on localhost.

![OnlineBank overview](docs/demo_screen.png)

## Quick start

```bash
docker compose up -d --build
```

Wait about 30 seconds (first boot seeds the database), then open:

| Service | URL |
|---|---|
| Web app (SPA + API behind nginx) | http://localhost:9080 |
| SMS gateway (open OTP inboxes) | http://localhost:9500 |

## Demo accounts

20 seeded users, all sharing the password `OnlineBank!123`. Login works by
email or by phone.

| Login | Phone | Password | Role / notes |
|---|---|---|---|
| `ama@onlinebank.app` | +233501234567 | `OnlineBank!123` | main demo user; one account of each kind (current/savings/goal/credit), 2 cards |
| `jdoe@onlinebank.app` | +233502345678 | `OnlineBank!123` | retail customer (USD + EUR accounts, card with processor metadata) |
| `cto@onlinebank.app` | +233503456789 | `OnlineBank!123` | high-value customer, OTP takeover target |
| `ops@onlinebank.app` | +233500000000 | `OnlineBank!123` | back-office operator (console, registry, KYC queue) |
| `akwasi@onlinebank.app` | +233504455661 | `OnlineBank!123` | retail customer |
| `abena@onlinebank.app` | +233504455662 | `OnlineBank!123` | retail, mixed products |
| `yaw@onlinebank.app` | +233504455663 | `OnlineBank!123` | retail, mixed products |
| `akosua@onlinebank.app` | +233504455664 | `OnlineBank!123` | retail, mixed products |
| `fatima@onlinebank.app` | +233504455665 | `OnlineBank!123` | retail, mixed products |
| `emeka@onlinebank.app` | +233504455666 | `OnlineBank!123` | retail, mixed products |
| `ngozi@onlinebank.app` | +233504455667 | `OnlineBank!123` | retail, mixed products |
| `chidi@onlinebank.app` | +233504455668 | `OnlineBank!123` | retail, mixed products |
| `esi@onlinebank.app` | +233505550601 | `OnlineBank!123` | savings account (USD) |
| `kofi@onlinebank.app` | +233505550602 | `OnlineBank!123` | goal account (GHS) |
| `amina@onlinebank.app` | +233505550603 | `OnlineBank!123` | credit line (USD) |
| `kojo@onlinebank.app` | +233505550604 | `OnlineBank!123` | current account (EUR) |
| `zainab@onlinebank.app` | +233505550605 | `OnlineBank!123` | current account (USD) |
| `kwabena@onlinebank.app` | +233505550606 | `OnlineBank!123` | savings account (GHS) |
| `afi@onlinebank.app` | +233505550607 | `OnlineBank!123` | goal account (USD) |
| `yaw2@onlinebank.app` | +233505550608 | `OnlineBank!123` | savings account (USD) |

Reset everything (database + demo data):

```bash
make reset          # wipe and reseed the demo data
```

## Services

| Service | Compose port | What it is |
|---|---|---|
| `web` | 9080 | nginx serving the built Vue 3 SPA and proxying `/api`, `/uploads` to the backend |
| `backend` | (internal 9000) | FastAPI + SQLAlchemy 2: all banking logic behind the SPA |
| `sms-gateway` | 9500 | FastAPI service the bank sends SMS through; web UI of per-phone inboxes |
| `metadata` | (internal 9801) | fake cloud IMDSv1 reachable as `169.254.169.254` via a compose `extra_hosts` entry (SSRF target) |
| `db` | (internal 5432) | PostgreSQL 16, seeded on first boot with 20 customers, accounts, cards, transactions, challenges |

## Requirements

- Docker with the compose plugin (any recent version; images are
  multi-arch amd64/arm64), or
- for host mode: Python 3.12+, Node.js 20+ and any PostgreSQL 16.

## Configuration

Everything is configured through environment variables. Defaults live in
`docker-compose.yml`; override them with a `.env` file next to it or plain
`VAR=value` assignments.

| Variable | Default | Affects |
|---|---|---|
| `FLAG_*` (12 vars) | stable literals | challenge flag values; see below |
| `DATABASE_URL` | `postgresql+psycopg2://bank:bank@localhost:5432/onlinebank` | backend database |
| `JWT_WEAK_SECRET` | `onlinebank-jwt-secret` | HMAC secret for issued tokens |
| `SMS_GATEWAY_URL` | `http://localhost:9500` | where the backend delivers SMS |
| `UPLOAD_DIR` | `/uploads` | storage for avatar and KYC files |
| `SECRETS_DIR` | `/app/secret` | local files the stand keeps server-side |
| `DEBUG` | `true` | verbose error bodies |
| `BACKEND_URL` | `http://localhost:9000` | used by the metadata service to pull its flag |
| `BANKNET_SUBNET`, `META_IP` | `172.31.0.0/24`, `172.31.0.10` | compose network subnet and the metadata address behind `169.254.169.254`; change both if the subnet is taken on a busy Docker host |

Flag lifecycle: precedence is environment variable, then the value already
stored in the database, then a random one generated on first seed. Flags
survive restarts and `make reset`; only `docker compose down -v` regenerates
them. The compose file pins stable values so a quick-start install is
reproducible; a host-run backend without `FLAG_*` gets random flags per
install.

## Running without Docker

The compose stack runs five services; for development you can run the three
Python services on the host and keep only PostgreSQL in a container:

```bash
# 1. database (the only container you need)
docker run -d --name ob-pg -p 9543:5432 \
  -e POSTGRES_USER=bank -e POSTGRES_PASSWORD=bank -e POSTGRES_DB=onlinebank \
  postgres:16-alpine

# 2. python services (each line runs in the foreground; use three terminals)
python3 -m venv .venv && .venv/bin/pip install -r backend/requirements.txt
export DATABASE_URL="postgresql+psycopg2://bank:bank@localhost:9543/onlinebank"
export SECRETS_DIR=/tmp/obsecret UPLOAD_DIR=/tmp/ob-uploads
mkdir -p $SECRETS_DIR $UPLOAD_DIR
(cd backend   && ../.venv/bin/uvicorn app.main:app --port 9000)
(cd sms-gateway && ../.venv/bin/uvicorn app:app --port 9500)
(cd metadata  && ../.venv/bin/uvicorn app:app --port 9801)

# 3. frontend dev server (proxies /api and /uploads to :9000)
cd frontend && npm install && npm run dev    # http://localhost:5173
```

Host-mode differences: there is no `169.254.169.254` alias (that trick needs
the compose network), so point SSRF payloads at `http://127.0.0.1:9801/...`
instead; the flag files live in `$SECRETS_DIR`, not `/app/secret`.

## License

MIT.
