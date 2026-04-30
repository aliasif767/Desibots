"""
PakOrderBot — Auth Module
JWT token creation & verification + bcrypt password hashing.
Place this at: agent/auth.py
"""
import os
import hmac
import hashlib
import base64
import json
import time
from typing import Optional

# ── Secret key (set a strong random string in .env) ──────────────────────────
SECRET_KEY  = os.getenv("JWT_SECRET", "pakorderbot-change-this-secret-in-production")
ALGORITHM   = "HS256"
EXPIRE_SECS = 8 * 3600   # 8 hours


# ─────────────────────────────────────────────────────────────────────────────
#  Minimal JWT (no external library needed)
# ─────────────────────────────────────────────────────────────────────────────

def _b64url_encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()

def _b64url_decode(s: str) -> bytes:
    pad = 4 - len(s) % 4
    return base64.urlsafe_b64decode(s + "=" * (pad % 4))

def _sign(header_b64: str, payload_b64: str) -> str:
    msg = f"{header_b64}.{payload_b64}".encode()
    sig = hmac.new(SECRET_KEY.encode(), msg, hashlib.sha256).digest()
    return _b64url_encode(sig)

def create_token(username: str, role: str) -> str:
    header  = _b64url_encode(json.dumps({"alg": ALGORITHM, "typ": "JWT"}).encode())
    payload = _b64url_encode(json.dumps({
        "sub":  username,
        "role": role,
        "iat":  int(time.time()),
        "exp":  int(time.time()) + EXPIRE_SECS,
    }).encode())
    sig = _sign(header, payload)
    return f"{header}.{payload}.{sig}"

def verify_token(token: str) -> Optional[dict]:
    """Returns payload dict if valid, None if invalid/expired."""
    try:
        parts = token.split(".")
        if len(parts) != 3:
            return None
        header_b64, payload_b64, sig = parts
        expected = _sign(header_b64, payload_b64)
        if not hmac.compare_digest(expected, sig):
            return None
        payload = json.loads(_b64url_decode(payload_b64))
        if payload.get("exp", 0) < time.time():
            return None
        return payload
    except Exception:
        return None


# ─────────────────────────────────────────────────────────────────────────────
#  Password hashing (PBKDF2-SHA256, no bcrypt needed)
# ─────────────────────────────────────────────────────────────────────────────

def hash_password(password: str) -> str:
    salt = os.urandom(16)
    key  = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, 260_000)
    return base64.b64encode(salt + key).decode()

def verify_password(password: str, stored_hash: str) -> bool:
    try:
        raw  = base64.b64decode(stored_hash.encode())
        salt = raw[:16]
        key  = raw[16:]
        check = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, 260_000)
        return hmac.compare_digest(key, check)
    except Exception:
        return False