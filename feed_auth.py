"""JWT HS256 (stdlib) cho feed UI / WebSocket."""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import logging
import secrets
import time
from pathlib import Path
from typing import Optional

from aiohttp import web

from settings import (
    FEED_AUTH_PASSWORD,
    FEED_AUTH_USER,
    FEED_JWT_SECRET,
    FEED_JWT_TTL,
    ROOT,
)

logger = logging.getLogger(__name__)
AUTH_FILE = ROOT / "data" / "feed_auth.json"


def _b64url_encode(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def _b64url_decode(data: str) -> bytes:
    pad = "=" * (-len(data) % 4)
    return base64.urlsafe_b64decode(data + pad)


def _load_or_create_secrets() -> tuple[str, str, str]:
    user = FEED_AUTH_USER
    password = FEED_AUTH_PASSWORD
    secret = FEED_JWT_SECRET
    stored: dict = {}
    if AUTH_FILE.is_file():
        try:
            stored = json.loads(AUTH_FILE.read_text(encoding="utf-8"))
        except Exception:
            stored = {}
    if not password:
        password = str(stored.get("password") or "")
    if not secret:
        secret = str(stored.get("secret") or "")
    if not password or not secret:
        AUTH_FILE.parent.mkdir(parents=True, exist_ok=True)
        password = password or secrets.token_urlsafe(12)
        secret = secret or secrets.token_hex(32)
        AUTH_FILE.write_text(
            json.dumps({"user": user, "password": password, "secret": secret}, indent=2)
            + "\n",
            encoding="utf-8",
        )
        logger.warning("Feed JWT credentials saved to %s (user=%s)", AUTH_FILE, user)
    return user, password, secret


_USER, _PASSWORD, _SECRET = _load_or_create_secrets()


def create_jwt(username: str, ttl: int | None = None) -> str:
    now = int(time.time())
    header = _b64url_encode(json.dumps({"alg": "HS256", "typ": "JWT"}, separators=(",", ":")).encode())
    payload = _b64url_encode(
        json.dumps(
            {"sub": username, "iat": now, "exp": now + int(ttl or FEED_JWT_TTL)},
            separators=(",", ":"),
        ).encode()
    )
    signing = f"{header}.{payload}".encode()
    sig = _b64url_encode(hmac.new(_SECRET.encode(), signing, hashlib.sha256).digest())
    return f"{header}.{payload}.{sig}"


def verify_jwt(token: Optional[str]) -> Optional[str]:
    if not token or token.count(".") != 2:
        return None
    header_b64, payload_b64, sig_b64 = token.split(".")
    signing = f"{header_b64}.{payload_b64}".encode()
    expected = _b64url_encode(hmac.new(_SECRET.encode(), signing, hashlib.sha256).digest())
    if not hmac.compare_digest(expected, sig_b64):
        return None
    try:
        payload = json.loads(_b64url_decode(payload_b64))
    except Exception:
        return None
    if int(payload.get("exp") or 0) < int(time.time()):
        return None
    user = str(payload.get("sub") or "").strip()
    return user or None


def check_password(username: str, password: str) -> bool:
    return hmac.compare_digest(username.strip(), _USER) and hmac.compare_digest(
        password, _PASSWORD
    )


def token_from_request(request: web.Request) -> Optional[str]:
    auth = request.headers.get("Authorization") or ""
    if auth.lower().startswith("bearer "):
        return auth[7:].strip()
    token = (request.query.get("token") or "").strip()
    if token:
        return token
    return (request.cookies.get("feed_token") or "").strip() or None


def require_jwt(request: web.Request) -> Optional[str]:
    return verify_jwt(token_from_request(request))
