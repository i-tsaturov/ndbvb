"""Fake cloud instance metadata service (IMDSv1).

Reachable from the backend under the classic address 169.254.169.254 via the
compose extra_hosts entry. No token header required — just like IMDSv1,
which is the point of the SSRF demonstration.
"""
import os

import requests
from fastapi import FastAPI
from fastapi.responses import JSONResponse, PlainTextResponse

app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)

def _current_flag() -> str:
    """Lazily fetch the per-installation SSRF flag from the bank API on each
    credentials read (falls back to the env value)."""
    if os.environ.get("FLAG_SSRF"):
        return os.environ["FLAG_SSRF"]
    backend = os.environ.get("BACKEND_URL", "http://localhost:9000")
    try:
        r = requests.get(f"{backend}/api/v0/debug/flag/ssrf", timeout=5)
        if r.ok and r.json().get("flag", "").startswith("FLAG{"):
            return r.json()["flag"]
    except requests.RequestException:
        pass
    return "FLAG{ssrf-imds-credentials}"

CREDENTIALS = {
    "Code": "Success",
    "AccessKeyId": "AKIA48CRMOSPQIXAMPLE",
    "SecretAccessKey": "wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY",
    "Token": "FwoGZXIvYXdzEBYaDGEXAMPLETOKEN9j0MvW",
    "Expiration": "2026-12-31T23:59:59Z",
}


@app.get("/", response_class=PlainTextResponse)
def root():
    return "latest/"


@app.get("/latest/", response_class=PlainTextResponse)
def latest():
    return "meta-data/\n"


@app.get("/latest/meta-data/", response_class=PlainTextResponse)
def meta():
    return "instance-id/\niam/\n"


@app.get("/latest/meta-data/instance-id", response_class=PlainTextResponse)
def instance_id():
    return "i-0a1b2c3d4e5f67890"


@app.get("/latest/meta-data/iam/", response_class=PlainTextResponse)
def iam():
    return "security-credentials/\n"


@app.get("/latest/meta-data/iam/security-credentials/", response_class=PlainTextResponse)
def creds_list():
    return "onlinebank-prod-role\n"


@app.get("/latest/meta-data/iam/security-credentials/onlinebank-prod-role",
         response_class=JSONResponse)
def creds():
    return {**CREDENTIALS, "flag": _current_flag()}
