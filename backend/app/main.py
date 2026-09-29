import os
import traceback

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, FileResponse
from fastapi.staticfiles import StaticFiles

from .db import Base, engine
from .routers import (
    accounts,
    admin,
    auth,
    cards,
    cashback,
    core,
    debug,
    exchange,
    graphql_api,
    profile,
    progress,
    statements,
    support,
    notifications,
    payments,
    transfers,
    webhooks,
)
from .seed import seed, write_secret_files

DEBUG = os.environ.get("DEBUG", "true").lower() == "true"

app = FastAPI(
    title="OnlineBank API",
    version="2.0.0",
    description=(
        "Retail banking API: payments, accounts, cards, exchange, statements.\n\n"
        "Every customer action in the web/mobile clients maps to the endpoints "
        "below (the mobile app additionally uses the GraphQL gateway at "
        "/api/v1/graphql).\n\n"
        "Internal QA surfaces (/api/v0/*) and the payment callback API are "
        "intentionally NOT part of this schema."
    ),
    docs_url="/api/v1/docs",
    redoc_url=None,
    openapi_url="/api/v1/openapi.json",
)

app.add_middleware(
    CORSMiddleware,
    allow_origin_regex=".*",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def powered_by(request: Request, call_next):
    response = await call_next(request)
    response.headers["X-Powered-By"] = "OnlineBank/FastAPI"
    return response


@app.exception_handler(Exception)
async def verbose_errors(request: Request, exc: Exception):
    tb = traceback.format_exc() if DEBUG else ""
    return JSONResponse(
        status_code=500,
        content={"error": str(exc), "traceback": tb, "path": request.url.path},
    )


app.include_router(core.router)
app.include_router(auth.router)
app.include_router(accounts.router)
app.include_router(transfers.router)
app.include_router(notifications.router)
app.include_router(payments.router)
app.include_router(payments.templates_router)
app.include_router(exchange.router)
app.include_router(cards.router)
app.include_router(statements.router)
app.include_router(cashback.router)
app.include_router(profile.router)
app.include_router(webhooks.router)
app.include_router(support.router)
app.include_router(admin.router)
app.include_router(graphql_api.router)
app.include_router(progress.router)
app.include_router(debug.router)


@app.get("/robots.txt", include_in_schema=False)
def robots():
    import os
    path = os.path.join(os.path.dirname(__file__), "static", "robots.txt")
    return FileResponse(path, media_type="text/plain")


@app.get("/old-api-spec.json", include_in_schema=False)
def old_spec():
    import os
    path = os.path.join(os.path.dirname(__file__), "static", "old-api-spec.json")
    return FileResponse(path, media_type="application/json")


@app.get("/api/v1/vault/{path:path}", summary="Restricted vault access")
def vault(path: str):
    return JSONResponse(status_code=403, content={"error": "Access to the vault is denied"})


UPLOAD_DIR = os.environ.get("UPLOAD_DIR", "/uploads")
try:
    os.makedirs(UPLOAD_DIR, exist_ok=True)
    app.mount("/uploads", StaticFiles(directory=UPLOAD_DIR), name="uploads")
except OSError:
    pass


@app.on_event("startup")
def startup():
    Base.metadata.create_all(bind=engine)
    write_secret_files()
    seed()
