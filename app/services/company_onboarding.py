"""Single-company onboarding; raw verification credentials never enter persistent storage."""

from datetime import timedelta
from contextlib import contextmanager
from email.message import EmailMessage
import secrets
import smtplib

from sqlalchemy import func, select, update
from sqlalchemy.exc import IntegrityError, SQLAlchemyError

from app.core.config import settings
from app.core.passwords import hash_password
from app.models.entities import Company, CompanyInvitation, EmailClaim, EmailVerification, User
from app.services import auth_sessions
from app.services.audit import record_audit
from app.services.seed import get_or_create_role


def normalized_email(value):
    email = value.strip().lower()
    if not email or len(email) > 320 or "@" not in email or any(c.isspace() for c in email):
        raise auth_sessions.AuthError("Invalid email", 400)
    return email


def development_token(token):
    return token if settings.debug and settings.app_env in {"development", "test"} else None


def mail_ready():
    return all((settings.smtp_host, settings.smtp_from, settings.public_base_url))


def require_delivery():
    if not mail_ready() and not (settings.debug and settings.app_env in {"development", "test"}):
        raise auth_sessions.AuthError("Email delivery is not configured", 503)


def deliver(email, subject, route, token):
    if not mail_ready():
        return
    message = EmailMessage()
    message["From"] = settings.smtp_from
    message["To"] = email
    message["Subject"] = subject
    message.set_content(f"Open {settings.public_base_url.rstrip('/')}{route}{token}")
    # SMTP failures are intentionally not logged with the message or token.
    try:
        with smtplib.SMTP_SSL(settings.smtp_host, settings.smtp_port, timeout=10) as smtp:
            if settings.smtp_username:
                smtp.login(settings.smtp_username, settings.smtp_password)
            smtp.send_message(message)
    except (OSError, smtplib.SMTPException):
        raise auth_sessions.AuthError("Email delivery temporarily unavailable", 503) from None


def claim_email(db, email):
    # The unique claim serializes concurrent registrations, including SQLite.
    if db.scalar(select(User.id).where(func.lower(User.email) == email).limit(1)):
        raise auth_sessions.AuthError("Email is already registered", 409)
    db.add(EmailClaim(email=email))
    db.flush()


@contextmanager
def identity_transaction(db):
    try:
        yield
        db.commit()
    except IntegrityError:
        db.rollback()
        raise auth_sessions.AuthError("Company or email is already registered", 409) from None
    except SQLAlchemyError:
        db.rollback()
        raise auth_sessions.AuthUnavailable() from None
    except Exception:
        db.rollback()
        raise


def register(db, *, company_name, owner_name, email, password):
    require_delivery()
    email = normalized_email(email)
    company_name = company_name.strip()
    owner_name = owner_name.strip()
    if len(company_name) < 2 or not owner_name:
        raise auth_sessions.AuthError("Company and owner names are required", 400)
    token = secrets.token_urlsafe(32)
    with identity_transaction(db):
        claim_email(db, email)
        role = get_or_create_role(db, "owner")
        company = Company(name=company_name, onboarding_status="pending")
        db.add(company)
        db.flush()
        user = User(company_id=company.id, name=owner_name, email=email,
                    password_hash=hash_password(password), role_id=role.id,
                    email_verified=False, is_platform_admin=False)
        db.add(user)
        db.flush()
        company.owner_user_id = user.id
        db.add(EmailVerification(user_id=user.id, token_digest=auth_sessions.digest(token),
                                 expires_at=auth_sessions.now() + timedelta(hours=24)))
        record_audit(db, company_id=company.id, user_id=user.id, action="company.register",
                     resource_type="company", resource_id=company.id, status="success")
        record_audit(db, company_id=company.id, user_id=user.id, action="auth.verification_requested",
                     resource_type="user", resource_id=user.id, status="success")
    deliver(email, "Verify your company account", "/workspace?verify=", token)
    return {"message": "Company created. Verify the owner email before signing in.",
            "company_id": company.id, "verification_token": development_token(token)}


def request_verification(db, email):
    require_delivery()
    email = normalized_email(email)
    user = db.scalar(select(User).where(User.email == email, User.email_verified.is_(False)))
    if not user:
        return {"message": "If the account needs verification, instructions were issued."}
    token = secrets.token_urlsafe(32)
    with auth_sessions.transaction(db):
        db.add(EmailVerification(user_id=user.id, token_digest=auth_sessions.digest(token),
                                 expires_at=auth_sessions.now() + timedelta(hours=24)))
        record_audit(db, company_id=user.company_id, user_id=user.id,
                     action="auth.verification_requested", resource_type="user", resource_id=user.id,
                     status="success")
    deliver(email, "Verify your company account", "/workspace?verify=", token)
    return {"message": "If the account needs verification, instructions were issued.",
            "verification_token": development_token(token)}


def verify_email(db, token):
    with auth_sessions.transaction(db):
        row = db.scalar(select(EmailVerification).where(
            EmailVerification.token_digest == auth_sessions.digest(token)).with_for_update())
        if not row or row.consumed_at or auth_sessions.utc(row.expires_at) <= auth_sessions.now():
            raise auth_sessions.AuthError("Invalid or expired verification token", 400)
        result = db.execute(update(EmailVerification).where(
            EmailVerification.id == row.id, EmailVerification.consumed_at.is_(None))
            .values(consumed_at=auth_sessions.now()).execution_options(synchronize_session=False))
        if result.rowcount != 1:
            raise auth_sessions.AuthError("Invalid or expired verification token", 400)
        user = auth_sessions.lock_user(db, row.user_id)
        if not user or user.email_verified:
            raise auth_sessions.AuthError("Invalid or expired verification token", 400)
        user.email_verified = True
        record_audit(db, company_id=user.company_id, user_id=user.id, action="auth.email_verified",
                     resource_type="user", resource_id=user.id, status="success")
    return {"message": "Email verified. You can sign in."}


def invite(db, actor, email):
    require_delivery()
    email = normalized_email(email)
    company = db.get(Company, actor.company_id)
    if company.owner_user_id != actor.id or company.onboarding_status != "complete":
        raise auth_sessions.AuthError("Only the company owner can invite employees after onboarding", 403)
    # Do not expose whether an arbitrary email already belongs to another tenant.
    if db.scalar(select(User.id).where(func.lower(User.email) == email).limit(1)):
        return {"message": "If eligible, an invitation has been created."}
    token = secrets.token_urlsafe(32)
    with auth_sessions.transaction(db):
        invitation = CompanyInvitation(company_id=company.id, invited_by_user_id=actor.id,
            email=email, role_name="member", token_digest=auth_sessions.digest(token),
            expires_at=auth_sessions.now() + timedelta(days=2))
        db.add(invitation)
        db.flush()
        record_audit(db, company_id=company.id, user_id=actor.id, action="company.invitation.create",
                     resource_type="company_invitation", resource_id=invitation.id, status="success")
    deliver(email, "Invitation to your company workspace", "/workspace?invite=", token)
    return {"message": "If eligible, an invitation has been created.",
            "invitation_token": development_token(token)}


def accept_invitation(db, token, name, password):
    with identity_transaction(db):
        invitation = db.scalar(select(CompanyInvitation).where(
            CompanyInvitation.token_digest == auth_sessions.digest(token)).with_for_update())
        if invitation and not invitation.consumed_at and not invitation.revoked_at and auth_sessions.utc(invitation.expires_at) <= auth_sessions.now():
            record_audit(db, company_id=invitation.company_id, user_id=invitation.invited_by_user_id,
                         action="company.invitation.expired", resource_type="company_invitation",
                         resource_id=invitation.id, status="expired")
            db.commit()
            raise auth_sessions.AuthError("Invalid or expired invitation", 400)
        if not invitation or invitation.consumed_at or invitation.revoked_at:
            raise auth_sessions.AuthError("Invalid or expired invitation", 400)
        company = db.get(Company, invitation.company_id)
        if not company or not company.is_active or company.onboarding_status != "complete":
            raise auth_sessions.AuthError("Invitation is unavailable", 403)
        claim_email(db, invitation.email)
        role = get_or_create_role(db, "member")
        user = User(company_id=company.id, name=name.strip(), email=invitation.email,
                    password_hash=hash_password(password), role_id=role.id,
                    email_verified=True, is_platform_admin=False)
        db.add(user)
        db.flush()
        result = db.execute(update(CompanyInvitation).where(
            CompanyInvitation.id == invitation.id, CompanyInvitation.consumed_at.is_(None),
            CompanyInvitation.revoked_at.is_(None))
            .values(consumed_at=auth_sessions.now()).execution_options(synchronize_session=False))
        if result.rowcount != 1:
            raise auth_sessions.AuthError("Invitation already used", 400)
        record_audit(db, company_id=company.id, user_id=user.id, action="company.invitation.accept",
                     resource_type="company_invitation", resource_id=invitation.id, status="success")
    return {"message": "Account created. You can sign in."}
