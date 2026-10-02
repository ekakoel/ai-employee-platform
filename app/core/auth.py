from fastapi import Header, HTTPException
from sqlalchemy.orm import Session

from app.models import User


def get_current_user(x_user_id: str | None = Header(default=None), db: Session | None = None):
    if not x_user_id or db is None:
        raise HTTPException(status_code=401, detail="X-User-ID header is required")
    user = db.get(User, x_user_id)
    if not user or user.status != "active":
        raise HTTPException(status_code=401, detail="Invalid or inactive user")
    return user
