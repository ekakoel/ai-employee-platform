"""Job 15 — Production auth: register, login, refresh, token."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session
from sqlalchemy.exc import SQLAlchemyError

from app.core.database import get_db
from app.core.config import settings
from app.services import auth_sessions
from app.services import company_onboarding
from app.models.entities import User
from app.services.access import user_permission_keys

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])


class LoginRequest(BaseModel):
    email: str = Field(min_length=3, max_length=320)
    password: str = Field(min_length=8, max_length=128)
    # Legacy company_id is intentionally ignored; tenant comes from the account.
    company_id: str | None = None


class RefreshRequest(BaseModel):
    refresh_token: str


class ForgotPasswordRequest(BaseModel):
    email: str = Field(min_length=3, max_length=320)
    company_id: str | None = None


class ResetPasswordRequest(BaseModel):
    token: str = Field(min_length=10)
    new_password: str = Field(min_length=8, max_length=128)


class ChangePasswordRequest(BaseModel):
    current_password: str = Field(min_length=8, max_length=128)
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


def _run(operation):
    try:
        return operation()
    except auth_sessions.AuthError as exc:
        raise HTTPException(status_code=exc.status, detail=str(exc)) from None
    except SQLAlchemyError:
        raise HTTPException(status_code=503, detail="Authentication temporarily unavailable") from None
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid password") from None


def _bearer(authorization):
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status_code=401, detail="Authentication required (Bearer token)")
    return authorization.split(" ", 1)[1].strip()


def _request_id(request):
    return getattr(request.state, "request_id", None)


@router.post("/token")
def issue_token_legacy():
    """Passwordless token issuance is disabled in every environment."""
    raise HTTPException(status_code=410, detail="Use password authentication at /auth/login")


@router.post("/login", response_model=TokenResponse)
def login(payload: LoginRequest, request: Request, db: Session = Depends(get_db)):
    """Password login with server-resolved single active company."""
    return _run(lambda: auth_sessions.login(db, payload.email, payload.password,
                                            None, _request_id(request)))


class CompanyRegistration(BaseModel):
    model_config = ConfigDict(extra="forbid")
    company_name: str = Field(min_length=2, max_length=200)
    owner_name: str = Field(min_length=1, max_length=200)
    email: str = Field(min_length=3, max_length=320)
    password: str = Field(min_length=8, max_length=128)


class VerificationRequest(BaseModel):
    # Job 95: 6-digit OTP (also accepts legacy longer tokens)
    token: str = Field(min_length=6, max_length=128)


class VerificationResend(BaseModel):
    email: str = Field(min_length=3, max_length=320)


class InvitationAcceptance(BaseModel):
    token: str = Field(min_length=20)
    name: str = Field(min_length=1, max_length=200)
    password: str = Field(min_length=8, max_length=128)


@router.post("/register", status_code=201)
def register(payload: CompanyRegistration, db: Session = Depends(get_db)):
    return _run(lambda: company_onboarding.register(db, company_name=payload.company_name,
        owner_name=payload.owner_name, email=payload.email, password=payload.password))


@router.post("/verify-email")
def verify_email(payload: VerificationRequest, db: Session = Depends(get_db)):
    return _run(lambda: company_onboarding.verify_email(db, payload.token))


@router.post("/request-verification")
def request_verification(payload: VerificationResend, db: Session = Depends(get_db)):
    return _run(lambda: company_onboarding.request_verification(db, payload.email))


@router.post("/accept-invitation", status_code=201)
def accept_invitation(payload: InvitationAcceptance, db: Session = Depends(get_db)):
    return _run(lambda: company_onboarding.accept_invitation(db, payload.token, payload.name, payload.password))


@router.post("/refresh", response_model=TokenResponse)
def refresh_token(payload: RefreshRequest, request: Request, db: Session = Depends(get_db)):
    return _run(lambda: auth_sessions.refresh(db, payload.refresh_token, _request_id(request)))


@router.post("/logout", status_code=204)
def logout(request: Request, db: Session = Depends(get_db), authorization: str | None = Header(default=None)):
    _run(lambda: auth_sessions.logout(db, _bearer(authorization), request_id=_request_id(request)))


@router.post("/logout-all", status_code=204)
def logout_all(request: Request, db: Session = Depends(get_db), authorization: str | None = Header(default=None)):
    _run(lambda: auth_sessions.logout(db, _bearer(authorization), all_sessions=True, request_id=_request_id(request)))


@router.post("/change-password")
def change_password(payload: ChangePasswordRequest, request: Request, db: Session = Depends(get_db),
                    authorization: str | None = Header(default=None)):
    _run(lambda: auth_sessions.change_password(db, _bearer(authorization), payload.current_password,
                                               payload.new_password, _request_id(request)))
    return {"message": "Password updated. Please sign in again."}


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

    user_id = resolve_user_id(db=db, authorization=authorization, x_user_id=x_user_id)
    try:
        user = db.get(User, user_id)
        if not user or user.status != "active":
            raise HTTPException(status_code=401, detail="Invalid or inactive user")
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
    except SQLAlchemyError:
        db.rollback()
        raise HTTPException(status_code=503, detail="Authentication temporarily unavailable") from None


@router.post("/forgot-password")
def forgot_password(payload: ForgotPasswordRequest, request: Request, db: Session = Depends(get_db)):
    """Request a password reset token.

    Always returns a generic success message (no email enumeration).
    When app debug is on, includes a reset_token for local testing without SMTP.
    """
    token = _run(lambda: auth_sessions.request_reset(db, payload.email, payload.company_id, _request_id(request)))
    response: dict = {
        "message": "If an account exists for that email, password reset instructions were issued.",
    }
    if token and settings.debug and settings.app_env in {"development", "test"}:
        response["reset_token"] = token
        response["debug_hint"] = "Use POST /api/v1/auth/reset-password with this token (debug mode only exposes token)."
    return response


@router.post("/reset-password")
def reset_password(payload: ResetPasswordRequest, request: Request, db: Session = Depends(get_db)):
    """Set a new password using a forgot-password token."""
    _run(lambda: auth_sessions.reset_password(db, payload.token, payload.new_password, _request_id(request)))
    return {"message": "Password updated. You can sign in with your new password."}
