"""Authentication dependencies: identities always come from Bearer tokens."""

from __future__ import annotations

from fastapi import Depends, Header, HTTPException
from sqlalchemy.orm import Session

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
    """Resolve the token subject; client identity headers have no authority."""
    if authorization and authorization.lower().startswith("bearer "):
        token = authorization.split(" ", 1)[1].strip()
        try:
            payload = decode_access_token(token)
        except ValueError as exc:
            raise HTTPException(status_code=401, detail=str(exc)) from exc
        user_id = payload.get("sub")
        if not isinstance(user_id, str) or not user_id.strip():
            raise HTTPException(status_code=401, detail="Token missing subject")
        return str(user_id)

    raise HTTPException(
        status_code=401,
        detail="Authentication required (Bearer token)",
    )


def get_current_user(
    db: Session = Depends(get_db),
    x_user_id: str | None = Header(default=None),
    authorization: str | None = Header(default=None),
) -> User:
    user_id = resolve_user_id(authorization=authorization, x_user_id=x_user_id)
    return _load_user(db, user_id)


def get_authenticated_user_id(user: User = Depends(get_current_user)) -> str:
    """Supply a verified ID to existing company handlers and their audit calls."""
    return user.id
