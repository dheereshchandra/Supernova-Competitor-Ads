"""Shared-password auth with a display name for attribution.

Login = team password (constant-time compare) + "who are you" name; success
sets a signed cookie (itsdangerous TimestampSigner). If STUDIO_PASSWORD is
unset, auth is disabled (local dev) and everyone is "dev".
"""
from __future__ import annotations

import hmac
import json
import time

from fastapi import APIRouter, HTTPException, Request, Response
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer
from pydantic import BaseModel

from .config import settings

COOKIE = "studio_session"
MAX_AGE_S = 30 * 24 * 3600

router = APIRouter()

# token-bucket on login attempts (origin IPs are Cloudflare's, so global)
_attempts: list[float] = []
_RATE = 10  # per minute


def _serializer() -> URLSafeTimedSerializer:
    secret = settings().session_secret or "dev-only-secret"
    return URLSafeTimedSerializer(secret, salt="studio-auth")


def current_user(request: Request) -> str | None:
    if not settings().auth_enabled:
        return "dev"
    raw = request.cookies.get(COOKIE)
    if not raw:
        return None
    try:
        data = _serializer().loads(raw, max_age=MAX_AGE_S)
        return data.get("name") or None
    except (BadSignature, SignatureExpired, json.JSONDecodeError):
        return None


def require_user(request: Request) -> str:
    user = current_user(request)
    if not user:
        raise HTTPException(401, "Not signed in")
    return user


class LoginBody(BaseModel):
    password: str
    display_name: str


@router.post("/api/auth/login")
def login(body: LoginBody, request: Request, response: Response):
    now = time.time()
    _attempts[:] = [t for t in _attempts if now - t < 60]
    if len(_attempts) >= _RATE:
        raise HTTPException(429, "Too many attempts — wait a minute")
    _attempts.append(now)

    cfg = settings()
    if not cfg.auth_enabled:
        return {"name": "dev", "auth": "disabled"}
    if not hmac.compare_digest(body.password.encode(), cfg.password.encode()):
        raise HTTPException(401, "Wrong password")
    name = body.display_name.strip()[:40]
    if not name:
        raise HTTPException(422, "Tell us who you are")
    token = _serializer().dumps({"name": name})
    # Secure only over HTTPS — Cloudflare sets X-Forwarded-Proto=https through the tunnel.
    # On plain http://localhost a Secure cookie is silently dropped by browsers, so a
    # conditional flag lets local testing work while staying secure in production.
    https = (request.url.scheme == "https"
             or request.headers.get("x-forwarded-proto", "").lower() == "https")
    response.set_cookie(COOKIE, token, max_age=MAX_AGE_S, httponly=True,
                        secure=https, samesite="lax")
    return {"name": name}


@router.post("/api/auth/logout")
def logout(response: Response):
    response.delete_cookie(COOKIE)
    return {"ok": True}


@router.get("/api/auth/me")
def me(request: Request):
    user = current_user(request)
    if not user:
        raise HTTPException(401, "Not signed in")
    return {"name": user, "auth": "enabled" if settings().auth_enabled else "disabled"}
