"""Production auth endpoints (JWT)."""

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import create_access_token
from app.models.entities import User

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])


class TokenRequest(BaseModel):
    company_id: str
    email: str = Field(min_length=3)
    # MVP: no password store yet — token issuance is gated by active user match
    # Production should verify password/OIDC before calling this.


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user_id: str
    company_id: str


@router.post("/token", response_model=TokenResponse)
def issue_token(payload: TokenRequest, db: Session = Depends(get_db)):
    """
    Issue a JWT for an active user in a company.

    Note: MVP has no password hash; this endpoint identifies the user by
    company_id + email. Wire SSO/password before enabling AUTH_ENABLED=true
    in production.
    """
    user = db.scalar(
        select(User).where(
            User.company_id == payload.company_id,
            User.email == payload.email,
        )
    )
    if not user or getattr(user, "status", "active") != "active":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials",
        )
    token = create_access_token(
        subject=user.id,
        company_id=user.company_id,
        extra={"email": user.email, "role_id": user.role_id},
    )
    return TokenResponse(
        access_token=token,
        user_id=user.id,
        company_id=user.company_id,
    )
