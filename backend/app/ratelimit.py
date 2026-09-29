"""In-memory rate limiter."""
import time
from collections import defaultdict, deque

from fastapi import HTTPException, Request

HITS: dict[str, deque] = defaultdict(deque)


def client_key(request: Request) -> str:
    xff = request.headers.get("x-forwarded-for")
    if xff:
        ip = xff.split(",")[0].strip()
    else:
        ip = request.client.host if request.client else "?"
    url = request.url.path
    if request.url.query:
        url += "?" + request.url.query
    return f"{ip}|{url}"


def rate_limit(max_requests: int = 5, window: int = 60):
    def dependency(request: Request) -> None:
        key = client_key(request)
        now = time.time()
        bucket = HITS[key]
        while bucket and bucket[0] < now - window:
            bucket.popleft()
        if len(bucket) >= max_requests:
            raise HTTPException(status_code=429, detail="Too many requests")
        bucket.append(now)

    return dependency
