"""SMS gateway for OnlineBank: an internal delivery service on its own port,
with a web UI of per-phone inboxes.
"""
import os
from collections import defaultdict
from datetime import datetime, timezone
from urllib.parse import quote

from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import BaseModel

app = FastAPI(title="OnlineBank SMS Gateway", docs_url=None, redoc_url=None, openapi_url=None)

MESSAGES: dict[str, list[dict]] = defaultdict(list)
MAX_PER_INBOX = 1000
_SEQ = 0


class SendBody(BaseModel):
    phone: str
    text: str


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%H:%M:%S")


def _next_seq() -> int:
    global _SEQ
    _SEQ += 1
    return _SEQ


def _resolve_inbox(phone: str) -> str | None:
    """Find an inbox by phone. Tolerates a '+' that arrived percent-decoded
    as a space in a query string, and bare-digit lookups."""
    raw = (phone or "").strip()
    if not raw:
        return None
    for key in MESSAGES:
        if key == raw or key.lstrip("+") == raw.lstrip("+"):
            return key
    return None


@app.post("/send")
def send(body: SendBody):
    inbox = MESSAGES[body.phone]
    inbox.insert(0, {"ts": _now(), "text": body.text, "seq": _next_seq()})
    del inbox[MAX_PER_INBOX:]
    return {"status": "delivered", "phone": body.phone}


@app.get("/inbox")
def inboxes():
    return [
        {"phone": phone, "count": len(msgs), "last": msgs[0]["text"] if msgs else ""}
        for phone, msgs in sorted(MESSAGES.items())
    ]


@app.get("/inbox/{phone}")
def inbox(phone: str):
    key = _resolve_inbox(phone)
    return {"phone": key or phone, "messages": MESSAGES.get(key, []) if key else []}


@app.get("/messages")
def messages(limit: int = 100):
    flat = [
        {"phone": phone, **m}
        for phone, msgs in MESSAGES.items()
        for m in msgs
    ]
    flat.sort(key=lambda m: m["seq"], reverse=True)
    return {"count": len(flat), "messages": flat[:limit]}


@app.get("/clear", response_class=JSONResponse)
def clear():
    MESSAGES.clear()
    return {"status": "cleared"}


PAGE = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>OnlineBank SMS Gateway</title>
<meta http-equiv="refresh" content="5">
<style>
  :root {{
    --bg:#F4F5F7; --ink:#14161B; --muted:#80828C; --line:#DBDFE6; --red:#FF0000;
    --card:#FFFFFF; --mono:'JetBrains Mono','PT Mono',ui-monospace,monospace;
  }}
  * {{ box-sizing:border-box; margin:0; }}
  body {{ background:var(--bg); color:var(--ink);
         font:15px/1.5 'Golos Text',Inter,'Segoe UI',Arial,sans-serif; padding:28px; }}
  header {{ display:flex; align-items:center; gap:14px; margin-bottom:22px; }}
  .mark {{ width:40px; height:8px; background:var(--red); }}
  h1 {{ font-size:22px; font-weight:700; }}
  .sub {{ color:var(--muted); font-size:13px; }}
  .wrap {{ display:grid; grid-template-columns:300px 1fr; gap:20px; max-width:1200px; }}
  .card {{ background:var(--card); border:1px solid var(--line); border-radius:12px; }}
  .inbox {{ padding:6px; }}
  .inbox a {{ display:flex; justify-content:space-between; gap:8px; padding:10px 12px;
             border-radius:8px; text-decoration:none; color:var(--ink); }}
  .inbox a:hover {{ background:var(--bg); }}
  .phone {{ font-family:var(--mono); font-size:13px; }}
  .cnt {{ color:var(--muted); font-size:12px; }}
  .feed {{ padding:18px 20px; min-height:300px; }}
  .msg {{ border:1px solid var(--line); border-radius:8px; padding:10px 14px; margin-bottom:10px; }}
  .msg .ts {{ color:var(--muted); font-size:12px; font-family:var(--mono); }}
  .msg .txt {{ margin-top:4px; font-family:var(--mono); font-size:13px; white-space:pre-wrap; }}
  .empty {{ color:var(--muted); }}
  a.active {{ outline:2px solid var(--red); }}
</style>
</head>
<body>
<header>
  <div class="mark"></div>
  <div>
    <h1>OnlineBank SMS Gateway</h1>
    <div class="sub">internal delivery service &middot; no authentication &middot; auto-refresh 5s</div>
  </div>
</header>
<div class="wrap">
  <div class="card inbox">
    <div style="padding:10px 12px;color:var(--muted);font-size:12px;text-transform:uppercase;letter-spacing:.08em">Inboxes</div>
    {inbox_links}
  </div>
  <div class="card feed">
    {feed}
  </div>
</div>
</body>
</html>"""


@app.get("/", response_class=HTMLResponse)
def home(phone: str | None = None):
    selected = _resolve_inbox(phone) if phone else None
    links = []
    for entry in inboxes():
        active = ' class="active"' if selected == entry["phone"] else ""
        links.append(
            f'<a href="/?phone={quote(entry["phone"])}"{active}>'
            f'<span class="phone">{entry["phone"]}</span>'
            f'<span class="cnt">{entry["count"]} msgs</span></a>'
        )
    if not links:
        links.append('<div style="padding:10px 12px" class="empty">No messages yet</div>')

    if selected:
        data = inbox(selected)
        items = [
            f'<div class="msg"><div class="ts">{m["ts"]} UTC</div>'
            f'<div class="txt">{m["text"]}</div></div>'
            for m in data["messages"]
        ] or ['<div class="empty">Inbox is empty</div>']
        feed = (
            f'<div style="font-family:var(--mono);font-size:13px;margin-bottom:14px">{selected}</div>'
            + "".join(items)
        )
    else:
        feed = '<div class="empty">Select an inbox on the left.</div>'
    return HTMLResponse(PAGE.format(inbox_links="".join(links), feed=feed))
