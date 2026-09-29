# OnlineBank — challenges and hints

Submit flags on the `/progress` page (nickname + flag); hints there are
spoiler-level one-liners, deeper hints below. Full spoilers live in
[SOLUTIONS.md](SOLUTIONS.md); root causes in [VULNERABILITIES.md](VULNERABILITIES.md).
Rule of the lab: every flag must be earned through the vulnerability, not by
reading the source (the source is there to explain *afterwards*).

| # | Challenge | Category | Points |
|---|---|---|---|
| 1 | Take over an account through the SMS gateway | Authentication | 200 |
| 2 | Forge a back-office token | Cryptography | 300 |
| 3 | Read another customer's statement | Access Control | 150 |
| 4 | Escalate your own role | Access Control | 250 |
| 5 | Drive an account balance below zero | Business Logic | 300 |
| 6 | Dump the card vault through search | Injection | 200 |
| 7 | Steal the operator console flag | Injection | 250 |
| 8 | Read a server file through XML import | Injection | 250 |
| 9 | Execute code through the legacy import | Injection | 350 |
| 10 | Fetch the instance credentials | Server-Side Request | 250 |
| 11 | Find the forgotten debug API | Configuration | 150 |
| 12 | Read a secret through GraphQL | Configuration | 150 |

## Hints (three levels per challenge)

**1 JWT.** (a) What algorithms does the API accept? (b) `GET /api/v1/auth/jwks.json`
publishes a key — what happens if you use it for HMAC? (c) The secret is
crackable offline; the shadow API also prints it.

**2 IDOR.** (a) Account ids are small integers. (b) Swap the id in a request
the app already makes. (c) The CTO's dividend transaction contains the flag.

**3 Mass assignment.** (a) The profile PATCH echoes back what it stored.
(b) The User model has fields the edit form never shows. (c) `role`,
`is_backoffice`, `daily_limit` — the response congratulates new operators.

**4 Race.** (a) Conversion takes a third of a second — why? (b) Balance is
checked long before it is written. (c) Ten parallel identical requests beat
one 5 430.20 balance with 600.00 each.

**5 SQLi.** (a) The statement search box becomes a query fragment.
(b) The injection sits inside `AND (... ILIKE '%...%')` — close the bracket,
mind the column count and types. (c) `cards.note` of John Doe's card.

**6 XSS.** (a) Somebody renders rich text — who? (b) An operator reads
customer messages in their console. (c) The exfiltration can ride the SMS
gateway itself: `fetch('http://localhost:9500/send', ...)`.

**7 XXE.** (a) The import accepts XML "for legacy corporate clients".
(b) Entities can point at files and URLs. (c) `/app/secret/flag_xxe.txt`.

**8 RCE.** (a) Two legacy formats are accepted; one is not XML.
(b) `.bnk` files were pickled by a desktop tool. (c) `pickle` payloads run
`__reduce__` — return `subprocess.check_output`.

**9 SSRF.** (a) The bank calls URLs you control — twice.
(b) A test delivery shows the response body. (c) The cloud metadata address
works from the server, `169.254.169.254`, IMDSv1 path.

**10 Shadow.** (a) `robots.txt` tells you what to avoid — so visit it.
(b) `/api/v0/` exists, and old build artifacts leak specs. (c) `/api/v0/debug/config`.

**11 GraphQL.** (a) There is a second API style on the same host.
(b) Introspection is your schema map. (c) User 5 has a field the REST API
never returns.

## Dead ends (do not burn time)

Card freeze, beneficiary approval, `/api/v1/vault/*`, `GET /api/v1/admin/audit-log`
(without a proper operator token), the statement PDF. They are correct on
purpose — recognizing solid code is part of the job.
