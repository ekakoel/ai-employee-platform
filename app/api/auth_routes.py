"""Job 15 — Production auth: register, login, refresh, token."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Header, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.passwords import hash_password, verify_password
from app.core.security import (
    create_access_token,
    create_refresh_token,
    decode_token,
)
from app.models.entities import User
from app.services.audit import record_audit
from app.services.access import user_permission_keys

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])


class LoginRequest(BaseModel):
    email: str = Field(min_length=3, max_length=320)
    password: str = Field(min_length=8, max_length=128)
    # Optional — legacy clients may still send company_id
    company_id: str | None = None


class RefreshRequest(BaseModel):
    refresh_token: str


class ForgotPasswordRequest(BaseModel):
    email: str = Field(min_length=3, max_length=320)


class ResetPasswordRequest(BaseModel):
    token: str = Field(min_length=10)
    new_password: str = Field(min_length=8, max_length=128)


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str | None = None
    token_type: str = "bearer"
    user_id: str
    company_id: str
    email: str | None = None
    name: str | None = None
    role: str | None = None
    permissions: list[str] = []
    is_platform_admin: bool = False


def _user_role_name(user: User) -> str | None:
    return user.role.name if user.role is not None else None


def _issue_pair(user: User) -> TokenResponse:
    access = create_access_token(
        subject=user.id,
        company_id=user.company_id,
        extra={"email": user.email, "role_id": user.role_id},
    )
    refresh = create_refresh_token(subject=user.id, company_id=user.company_id)
    perms = sorted(user_permission_keys(user))
    return TokenResponse(
        access_token=access,
        refresh_token=refresh,
        user_id=user.id,
        company_id=user.company_id,
        email=user.email,
        name=user.name,
        role=_user_role_name(user),
        permissions=perms,
        is_platform_admin=bool(getattr(user, "is_platform_admin", False)),
    )


@router.post("/token")
def issue_token_legacy():
    """Passwordless token issuance is disabled in every environment."""
    raise HTTPException(status_code=410, detail="Use password authentication at /auth/login")


@router.post("/login", response_model=TokenResponse)
def login(payload: LoginRequest, db: Session = Depends(get_db)):
    """Sign in with email + password only (Job 58).

    If the same email exists in multiple companies, the first active account
    whose password matches is used. Optional company_id narrows the lookup.
    """
    email = payload.email.strip().lower()
    q = select(User).where(User.email == email, User.status == "active")
    if payload.company_id:
        q = q.where(User.company_id == payload.company_id)
    candidates = list(db.scalars(q).all())
    user = None
    for candidate in candidates:
        if verify_password(payload.password, candidate.password_hash):
            user = candidate
            break
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
        )
    record_audit(
        db,
        company_id=user.company_id,
        user_id=user.id,
        action="auth.login",
        resource_type="user",
        resource_id=user.id,
        status="success",
    )
    db.commit()
    return _issue_pair(user)


@router.post("/register")
def register():
    """Company membership is provisioned by an authorized administrator."""
    raise HTTPException(status_code=403, detail="Public registration is disabled; contact your company administrator")


@router.post("/refresh", response_model=TokenResponse)
def refresh_token(payload: RefreshRequest, db: Session = Depends(get_db)):
    try:
        data = decode_token(payload.refresh_token, expected_type="refresh")
    except ValueError as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc

    user_id = data.get("sub")
    company_id = data.get("company_id")
    if not user_id:
        raise HTTPException(status_code=401, detail="Invalid refresh token")

    user = db.get(User, user_id)
    if not user or user.status != "active":
        raise HTTPException(status_code=401, detail="Invalid or inactive user")
    if company_id and user.company_id != company_id:
        raise HTTPException(status_code=401, detail="Tenant mismatch")

    return _issue_pair(user)


class MeResponse(BaseModel):
    user_id: str
    email: str | None = None
    name: str | None = None
    company_id: str
    role: str | None = None
    permissions: list[str] = []
    is_platform_admin: bool = False
    status: str | None = None


@router.get("/me", response_model=MeResponse)
def read_me(
    db: Session = Depends(get_db),
    x_user_id: str | None = Header(default=None),
    authorization: str | None = Header(default=None),
):
    """Current user + role permissions for workspace UI gating (Job 35)."""
    from app.core.auth import resolve_user_id

    user_id = resolve_user_id(authorization=authorization, x_user_id=x_user_id)
    user = db.get(User, user_id)
    if not user or user.status != "active":
        raise HTTPException(status_code=401, detail="Invalid or inactive user")
    # Ensure role relationship loaded
    _ = user.role
    if user.role is not None:
        _ = user.role.permissions
    db.commit()
    return MeResponse(
        user_id=user.id,
        email=user.email,
        name=user.name,
        company_id=user.company_id,
        role=user.role.name if user.role else None,
        permissions=sorted(user_permission_keys(user)),
        is_platform_admin=bool(user.is_platform_admin),
        status=user.status,
    )


@router.post("/forgot-password")
def forgot_password(payload: ForgotPasswordRequest, db: Session = Depends(get_db)):
    """Request a password reset token.

    Always returns a generic success message (no email enumeration).
    When app debug is on, includes a reset_token for local testing without SMTP.
    """
    from app.core.config import settings

    email = payload.email.strip().lower()
    users = list(
        db.scalars(select(User).where(User.email == email, User.status == "active")).all()
    )
    response: dict = {
        "message": "If an account exists for that email, password reset instructions were issued.",
    }
    if not users:
        return response

    # Prefer a single user; if multiple companies share email, first match
    user = users[0]
    token = create_access_token(
        subject=user.id,
        company_id=user.company_id,
        extra={"type": "password_reset", "purpose": "password_reset", "email": user.email},
        expires_minutes=30,
    )
    record_audit(
        db,
        company_id=user.company_id,
        user_id=user.id,
        action="auth.forgot_password",
        resource_type="user",
        resource_id=user.id,
        status="success",
    )
    db.commit()
    if settings.debug:
        response["reset_token"] = token
        response["debug_hint"] = "Use POST /api/v1/auth/reset-password with this token (debug mode only exposes token)."
    return response


@router.post("/reset-password")
def reset_password(payload: ResetPasswordRequest, db: Session = Depends(get_db)):
    """Set a new password using a forgot-password token."""
    try:
        data = decode_token(payload.token, expected_type="password_reset")
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Invalid or expired reset token") from exc

    if data.get("purpose") != "password_reset":
        raise HTTPException(status_code=400, detail="Invalid reset token")

    user_id = data.get("sub")
    user = db.get(User, user_id) if user_id else None
    if not user or user.status != "active":
        raise HTTPException(status_code=400, detail="Invalid reset token")

    try:
        user.password_hash = hash_password(payload.new_password)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    record_audit(
        db,
        company_id=user.company_id,
        user_id=user.id,
        action="auth.reset_password",
        resource_type="user",
        resource_id=user.id,
        status="success",
    )
    db.commit()
    return {"message": "Password updated. You can sign in with your new password."}
