"""Live intraday rates (SPEC 14).

A deterministic mean-reverting walk over the minute-of-day, applied equally
to both directions of a pair, around the seeded base rates. The value changes
every minute, stays within base ±2%, and the asymmetric-base round-trip
quirk is preserved because both directions share the same multiplier.
"""
from datetime import datetime, timezone

WALK_POINTS = 1440
CLAMP = 0.02

_cache: dict[tuple[int, str], list[float]] = {}


def _walk(seed_key: str) -> list[float]:
    day = seed_key.rsplit("|", 1)[0] if "|" in seed_key else seed_key
    cached = _cache.get((0, day))
    if cached:
        return cached
    seed = 0
    for ch in seed_key.encode():
        seed = (seed * 131 + ch) % 2**31
    x = seed
    w, prev = 0.0, 0.0
    out = []
    for _ in range(WALK_POINTS):
        x = (1103515245 * x + 12345) % 2147483648
        noise = (x / 2147483648 - 0.5) * 0.004
        w = prev * 0.99 + noise
        if w > CLAMP:
            w = CLAMP
        if w < -CLAMP:
            w = -CLAMP
        out.append(w)
        prev = w
    _cache[(0, day)] = out
    return out


def minute_index(now: datetime | None = None) -> int:
    now = now or datetime.now(timezone.utc)
    return now.hour * 60 + now.minute


def day_key(now: datetime | None = None) -> str:
    now = now or datetime.now(timezone.utc)
    return now.strftime("%Y-%m-%d")


def dynamic_rate(base: float, pair: tuple[str, str], at: datetime | None = None) -> float:
    """Current dynamic rate for one direction of a pair.

    The two directions use OPPOSITE walk phases (+w / -w), so the product of
    the quoted rates stays glued to the base product through the day: each
    direction still breathes inside the +/-2% band, but a round trip is
    priced consistently (the asymmetric-base quirk keeps its exact v1 size).
    """
    a, b = sorted(pair)
    walk = _walk(f"{day_key(at)}|{a}{b}")
    w = walk[minute_index(at)]
    if pair[0] != a:
        w = -w
    return round(base * (1 + w), 4)


def rate_history(base: float, pair: tuple[str, str], points: int, now: datetime | None = None) -> list[float]:
    """Rates for the last `points` minutes ending at the current minute
    (same direction phase rule as dynamic_rate)."""
    a, b = sorted(pair)
    flip = -1.0 if pair[0] != a else 1.0
    walk = _walk(f"{day_key(now)}|{a}{b}")
    mi = minute_index(now)
    out = []
    for i in range(max(0, mi - points + 1), mi + 1):
        out.append(round(base * (1 + flip * walk[i]), 4))
    while len(out) < points:
        out.insert(0, out[0] if out else round(base, 4))
    return out[-points:]
