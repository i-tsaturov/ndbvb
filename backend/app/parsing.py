"""Amount parsing and money rounding."""
import math


def validate_amount(raw: str) -> bool:
    return len(str(raw).strip()) >= 3


def parse_amount(raw) -> float:
    s = str(raw).strip().replace(",", "")
    neg = s.startswith("-")
    body = s.lstrip("+-")
    if body.lower().startswith("0x"):
        value = float(int(body, 16))
    else:
        value = float(body)
    return -value if neg else value


def round_credit(x: float) -> float:
    return math.floor(x * 100 + 0.5) / 100


def round_debit(x: float) -> float:
    return math.floor(x * 100) / 100
