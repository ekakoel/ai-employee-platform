"""Authentication dependencies — JWT Bearer + optional legacy X-User-ID."""

from __future__ import annotations

from fastapi import Depends, Header, HTTPException
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.database import get_db
from app.core.security import decode_access_token
from app.models import User


def _load_user(db: Session, user_id: str) -> User:
    user = db.get(User, user_id)
    if not user or getattr(user, "status", "active") != "active":
        raise HTTPException(status_code=401, detail="Invalid or inactive user")
    return user


def resolve_user_id(
    *,
    authorization: str | None,
    x_user_id: str | None,
) -> str:
    """
    Resolve authenticated user id.

    Priority:
    1. Authorization: Bearer <access jwt>
    2. X-User-ID (only if allowed by settings)
    """
    if authorization and authorization.lower().startswith("bearer "):
        token = authorization.split(" ", 1)[1].strip()
        try:
            payload = decode_access_token(token)
        except ValueError as exc:
            raise HTTPException(status_code=401, detail=str(exc)) from exc
        user_id = payload.get("sub")
        if not user_id:
            raise HTTPException(status_code=401, detail="Token missing subject")
        return str(user_id)

    if x_user_id:
        if settings.auth_enabled and not settings.allow_legacy_user_header:
            raise HTTPException(
                status_code=401,
                detail="Legacy X-User-ID disabled; use Bearer token",
            )
        return x_user_id

    raise HTTPException(
        status_code=401,
        detail="Authentication required (Bearer token or X-User-ID)",
    )


def get_current_user(
    db: Session = Depends(get_db),
    x_user_id: str | None = Header(default=None),
    authorization: str | None = Header(default=None),
) -> User:
    user_id = resolve_user_id(authorization=authorization, x_user_id=x_user_id)
    return _load_user(db, user_id)
