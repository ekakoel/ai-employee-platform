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
from app.models.entities import Company, Role, User
from app.services.audit import record_audit
from app.services.seed import VALID_COMPANY_ROLES, get_or_create_role
from app.services.platform_admin import sync_platform_admin_flag
from app.services.access import user_permission_keys

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])


class TokenRequest(BaseModel):
    company_id: str
    email: str = Field(min_length=3)


class LoginRequest(BaseModel):
    company_id: str
    email: str = Field(min_length=3)
    password: str = Field(min_length=8, max_length=128)


class RegisterRequest(BaseModel):
    company_id: str
    email: str = Field(min_length=3, max_length=320)
    name: str = Field(min_length=1, max_length=200)
    password: str = Field(min_length=8, max_length=128)
    role: str = Field(default="member", max_length=50)


class RefreshRequest(BaseModel):
    refresh_token: str


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


@router.post("/token", response_model=TokenResponse)
def issue_token_legacy(payload: TokenRequest, db: Session = Depends(get_db)):
    """Dev/legacy: issue tokens by company + email without password."""
    user = db.scalar(
        select(User).where(
            User.company_id == payload.company_id,
            User.email == payload.email,
        )
    )
    if not user or user.status != "active":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials",
        )
    return _issue_pair(user)


@router.post("/login", response_model=TokenResponse)
def login(payload: LoginRequest, db: Session = Depends(get_db)):
    user = db.scalar(
        select(User).where(
            User.company_id == payload.company_id,
            User.email == payload.email,
        )
    )
    if not user or user.status != "active":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials",
        )
    if not verify_password(payload.password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials",
        )
    sync_platform_admin_flag(db, user)
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


@router.post(
    "/register",
    response_model=TokenResponse,
    status_code=status.HTTP_201_CREATED,
)
def register(payload: RegisterRequest, db: Session = Depends(get_db)):
    company = db.get(Company, payload.company_id)
    if not company:
        raise HTTPException(status_code=404, detail="Company not found")

    existing = db.scalar(
        select(User).where(
            User.company_id == payload.company_id,
            User.email == payload.email.strip().lower(),
        )
    )
    if existing:
        raise HTTPException(status_code=409, detail="Email already registered")

    role_name = payload.role if payload.role in VALID_COMPANY_ROLES else "member"
    role = get_or_create_role(db, role_name)

    try:
        pw_hash = hash_password(payload.password)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    user = User(
        company_id=payload.company_id,
        email=payload.email.strip().lower(),
        name=payload.name.strip(),
        password_hash=pw_hash,
        role_id=role.id,
        status="active",
    )
    db.add(user)
    db.flush()
    record_audit(
        db,
        company_id=user.company_id,
        user_id=user.id,
        action="auth.register",
        resource_type="user",
        resource_id=user.id,
        status="success",
    )
    db.commit()
    db.refresh(user)
    return _issue_pair(user)


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
    sync_platform_admin_flag(db, user)
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
