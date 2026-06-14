from __future__ import annotations

import base64
import hashlib
import hmac
import json
import time
from dataclasses import dataclass

from fastapi import Depends, HTTPException, Request, status

from app.config import Settings, get_settings

TOKEN_PREFIX = "agent-v1"
ISSUER = "agent-service"
AUDIENCE = "apartment_gate"


@dataclass(frozen=True)
class AgentTokenClaims:
    subject: str
    scope: str
    expires_at: int
    audience: str


def _b64encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _b64decode(value: str) -> bytes:
    return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))


def _sign(payload: str, secret: str) -> str:
    return _b64encode(hmac.new(secret.encode("utf-8"), payload.encode("ascii"), hashlib.sha256).digest())


def encode_agent_token(
    *,
    secret: str,
    subject: str,
    scope: str,
    audience: str = AUDIENCE,
    expires_at: int | None = None,
) -> str:
    payload = {
        "iss": ISSUER,
        "aud": audience,
        "sub": subject,
        "scope": scope,
        "iat": int(time.time()),
        "exp": expires_at if expires_at is not None else int(time.time()) + 300,
    }
    encoded_payload = _b64encode(json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8"))
    return f"{TOKEN_PREFIX}.{encoded_payload}.{_sign(encoded_payload, secret)}"


def decode_agent_token(token: str, *, secret: str, audience: str = AUDIENCE) -> AgentTokenClaims | None:
    prefix, separator, rest = token.partition(".")
    payload, separator_two, signature = rest.partition(".")
    if prefix != TOKEN_PREFIX or separator != "." or separator_two != "." or not payload or not signature:
        return None
    if not hmac.compare_digest(signature, _sign(payload, secret)):
        return None
    try:
        claims = json.loads(_b64decode(payload))
    except (ValueError, json.JSONDecodeError):
        return None
    if not isinstance(claims, dict):
        return None
    if claims.get("iss") != ISSUER or claims.get("aud") != audience:
        return None
    subject = claims.get("sub")
    scope = claims.get("scope")
    expires_at = claims.get("exp")
    if not isinstance(subject, str) or not isinstance(scope, str) or not isinstance(expires_at, int):
        return None
    if expires_at <= int(time.time()):
        return None
    return AgentTokenClaims(subject=subject, scope=scope, expires_at=expires_at, audience=audience)


def bearer_token(request: Request) -> str | None:
    auth_header = request.headers.get("authorization")
    if auth_header and auth_header.lower().startswith("bearer "):
        return auth_header[7:].strip()
    return None


def require_agent_scope(scope: str):
    def dependency(
        request: Request,
        settings: Settings = Depends(get_settings),
    ) -> AgentTokenClaims:
        token = bearer_token(request)
        if not token or not settings.agent_integration_token_secret:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid agent token.")
        claims = decode_agent_token(token, secret=settings.agent_integration_token_secret)
        if claims is None or claims.scope != scope:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid agent token.")
        return claims

    return dependency
