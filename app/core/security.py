"""JWT helpers for production authentication."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from jose import JWTError, jwt

from app.core.config import settings


def create_access_token(
    *,
    subject: str,
    company_id: str,
    extra: dict[str, Any] | None = None,
    expires_minutes: int | None = None,
) -> str:
    expire = datetime.now(timezone.utc) + timedelta(
        minutes=expires_minutes or settings.jwt_expire_minutes
    )
    payload: dict[str, Any] = {
        "sub": subject,
        "company_id": company_id,
        "exp": expire,
        "iat": datetime.now(timezone.utc),
        "type": "access",
    }
    if extra:
        payload.update(extra)
    return jwt.encode(
        payload,
        settings.jwt_secret,
        algorithm=settings.jwt_algorithm,
    )


def decode_access_token(token: str) -> dict[str, Any]:
    try:
        return jwt.decode(
            token,
            settings.jwt_secret,
            algorithms=[settings.jwt_algorithm],
        )
    except JWTError as exc:
        raise ValueError("Invalid or expired token") from exc
