"""Signed token envelopes. Database session validation lives in auth_sessions."""

from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import uuid4

from jose import JWTError, jwt

from app.core.config import settings


def _encode(*, subject, company_id, token_type, token_id, auth_version, expires_at, session_id=None, extra=None):
    payload = dict(extra or {})
    payload.update(sub=subject, company_id=company_id, type=token_type, jti=token_id,
                   ver=auth_version, iat=datetime.now(timezone.utc), exp=expires_at)
    if session_id:
        payload["sid"] = session_id
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def create_access_token(*, subject: str, company_id: str, session_id: str,
                        auth_version: int, extra: dict[str, Any] | None = None,
                        expires_at: datetime | None = None) -> str:
    return _encode(subject=subject, company_id=company_id, token_type="access", token_id=str(uuid4()),
                   session_id=session_id, auth_version=auth_version, extra=extra,
                   expires_at=expires_at or datetime.now(timezone.utc) + timedelta(minutes=settings.jwt_expire_minutes))


def create_refresh_token(*, subject: str, company_id: str, session_id: str,
                         token_id: str, auth_version: int, expires_at: datetime) -> str:
    return _encode(subject=subject, company_id=company_id, token_type="refresh", token_id=token_id,
                   session_id=session_id, auth_version=auth_version, expires_at=expires_at)


def create_reset_token(*, subject: str, company_id: str, token_id: str,
                       auth_version: int, expires_at: datetime) -> str:
    return _encode(subject=subject, company_id=company_id, token_type="password_reset", token_id=token_id,
                   auth_version=auth_version, expires_at=expires_at, extra={"purpose": "password_reset"})


def decode_token(token: str, *, expected_type: str | None = None) -> dict[str, Any]:
    try:
        payload = jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_algorithm],
                             options={"require_exp": True, "require_sub": True, "require_iat": True})
    except JWTError:
        raise ValueError("Invalid or expired token") from None
    if expected_type and payload.get("type") != expected_type:
        raise ValueError("Invalid token type")
    if type(payload.get("exp")) is not int or type(payload.get("iat")) is not int or payload["exp"] <= payload["iat"]:
        raise ValueError("Invalid token timestamps")
    for key in ("sub", "company_id", "jti", "type"):
        if not isinstance(payload.get(key), str) or not payload[key].strip():
            raise ValueError("Missing token claims")
    if type(payload.get("ver")) is not int or payload["ver"] < 0:
        raise ValueError("Missing credential version")
    if payload["type"] in {"access", "refresh"}:
        if not isinstance(payload.get("sid"), str) or not payload["sid"].strip():
            raise ValueError("Legacy or invalid session token")
    if payload["type"] == "password_reset" and payload.get("purpose") != "password_reset":
        raise ValueError("Invalid reset purpose")
    return payload


def decode_access_token(token: str) -> dict[str, Any]:
    payload = decode_token(token, expected_type="access")
    if payload.get("purpose") == "password_reset":
        raise ValueError("Reset tokens cannot authenticate requests")
    return payload
