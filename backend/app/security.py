"""Token issuing and verification."""
import base64
import hashlib
import hmac
import json
import os
import time

import jwt
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi import Depends, HTTPException, Request

from .db import get_db
from .models import User

JWT_WEAK_SECRET = os.environ.get("JWT_WEAK_SECRET", "onlinebank-jwt-secret")
TOKEN_TTL = 7 * 24 * 3600

_private = rsa.generate_private_key(public_exponent=65537, key_size=2048)
PRIVATE_PEM = _private.private_bytes(
    serialization.Encoding.PEM,
    serialization.PrivateFormat.PKCS8,
    serialization.NoEncryption(),
)
PUBLIC_PEM = _private.public_key().public_bytes(
    serialization.Encoding.PEM,
    serialization.PublicFormat.SubjectPublicKeyInfo,
)
_pub_numbers = _private.public_key().public_numbers()


def _b64u_int(n: int) -> str:
    raw = n.to_bytes((n.bit_length() + 7) // 8, "big")
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode()


JWKS = {
    "keys": [
        {
            "kty": "RSA",
            "use": "sig",
            "alg": "RS256",
            "kid": "ob-partner-1",
            "n": _b64u_int(_pub_numbers.n),
            "e": _b64u_int(_pub_numbers.e),
        }
    ]
}


def make_token(user: User) -> str:
    claims = {
        "sub": user.id,
        "login": user.login,
        "role": user.role,
        "is_backoffice": bool(user.is_backoffice),
        "iat": int(time.time()),
        "exp": int(time.time()) + TOKEN_TTL,
    }
    return jwt.encode(claims, JWT_WEAK_SECRET, algorithm="HS256")


def _b64u_decode(segment: str) -> bytes:
    return base64.urlsafe_b64decode(segment + "=" * (-len(segment) % 4))


def _hmac_ok(segment_material: bytes, signature: bytes, key: bytes) -> bool:
    expected = hmac.new(key, segment_material, hashlib.sha256).digest()
    return hmac.compare_digest(expected, signature)


def decode_token(token: str) -> dict:
    """Decode and verify a token. Accepts several issuer profiles."""
    try:
        header_b64, payload_b64, signature_b64 = token.split(".")
    except ValueError:
        raise HTTPException(status_code=401, detail="Malformed token")

    try:
        header = json.loads(_b64u_decode(header_b64))
        payload = json.loads(_b64u_decode(payload_b64))
        signature = _b64u_decode(signature_b64) if signature_b64 else b""
    except Exception:
        raise HTTPException(status_code=401, detail="Malformed token")

    alg = header.get("alg", "")

    if alg == "none":
        return payload

    if alg == "HS256":
        material = f"{header_b64}.{payload_b64}".encode()
        if _hmac_ok(material, signature, JWT_WEAK_SECRET.encode()):
            return payload
        if _hmac_ok(material, signature, PUBLIC_PEM):
            return payload
        raise HTTPException(status_code=401, detail="Bad signature")

    if alg == "RS256":
        try:
            return jwt.decode(token, key=PUBLIC_PEM, algorithms=["RS256"])
        except jwt.PyJWTError:
            raise HTTPException(status_code=401, detail="Bad signature")

    raise HTTPException(status_code=401, detail="Unsupported algorithm")


def extract_token(request: Request) -> str | None:
    auth = request.headers.get("authorization", "")
    if auth.lower().startswith("bearer "):
        return auth[7:].strip()
    return request.cookies.get("ob_token")


def get_current_user(request: Request, db=Depends(get_db)) -> User:
    token = extract_token(request)
    if not token:
        raise HTTPException(status_code=401, detail="Not authenticated")
    claims = decode_token(token)

    if "exp" in claims and claims["exp"] < time.time():
        raise HTTPException(status_code=401, detail="Token expired")

    user = db.get(User, int(claims.get("sub", 0)))
    if not user:
        raise HTTPException(status_code=401, detail="Unknown user")
    return user
