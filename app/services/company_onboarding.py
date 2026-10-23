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
    link = f"{settings.public_base_url.rstrip('/')}{route}{token}"
    body = (
        "Activate your AI Employee Platform account.

"
        f"Open this link (valid 24 hours):
{link}

"
        "If you did not register, ignore this email.
"
    )
    message.set_content(body)
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
    deliver(email, "Activate your AI Employee Platform account", "/activate?token=", token)
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
    deliver(email, "Activate your AI Employee Platform account", "/activate?token=", token)
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


def _actor_permission_keys(actor) -> set:
    try:
        from app.services.access import user_permission_keys
        return set(user_permission_keys(actor))
    except Exception:
        if actor.role and actor.role.permissions:
            return {p.key for p in actor.role.permissions}
        return set()


def can_manage_team(actor, company) -> bool:
    if company.onboarding_status != "complete":
        return False
    if company.owner_user_id == actor.id and getattr(actor.role, "name", None) == "owner":
        return True
    return "team.manage" in _actor_permission_keys(actor)


# Roles an Administrator (ai_admin / administration) may assign via invite
ADMIN_INVITE_ROLES = frozenset({
    "member", "reservation", "manager", "contract_manager",
    "administration", "accounting",
})
# Owner may also invite AI administrators
OWNER_INVITE_ROLES = ADMIN_INVITE_ROLES | {"ai_admin"}


def invite(db, actor, email, role_name: str = "member"):
    """Owner or team manager (AI Admin / Administration) invites an employee."""
    require_delivery()
    email = normalized_email(email)
    company = db.get(Company, actor.company_id)
    if not can_manage_team(actor, company):
        raise auth_sessions.AuthError(
            "Only the owner or an administrator with team access can invite employees after onboarding",
            403,
        )
    from app.services.seed import ROLE_PERMISSIONS, get_or_create_role
    role_name = (role_name or "member").strip().lower()
    is_owner = company.owner_user_id == actor.id and getattr(actor.role, "name", None) == "owner"
    allowed = OWNER_INVITE_ROLES if is_owner else ADMIN_INVITE_ROLES
    if role_name not in ROLE_PERMISSIONS or role_name not in allowed:
        raise auth_sessions.AuthError(
            "Invalid job role for invitation (administrators cannot invite owners or AI admins)"
            if not is_owner else "Invalid job role for invitation",
            400,
        )
    # Do not expose whether an arbitrary email already belongs to another tenant.
    if db.scalar(select(User.id).where(func.lower(User.email) == email).limit(1)):
        return {"message": "If eligible, an invitation has been created."}
    token = secrets.token_urlsafe(32)
    with auth_sessions.transaction(db):
        invitation = CompanyInvitation(
            company_id=company.id,
            invited_by_user_id=actor.id,
            email=email,
            role_name=role_name,
            token_digest=auth_sessions.digest(token),
            expires_at=auth_sessions.now() + timedelta(days=2),
        )
        db.add(invitation)
        db.flush()
        record_audit(
            db,
            company_id=company.id,
            user_id=actor.id,
            action="company.invitation.create",
            resource_type="company_invitation",
            resource_id=invitation.id,
            status="success",
            details={"role_name": role_name},
        )
    deliver(email, "Invitation to your company workspace", "/workspace?invite=", token)
    return {
        "message": "If eligible, an invitation has been created.",
        "invitation_token": development_token(token),
        "role_name": role_name,
    }


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
        from app.services.seed import ROLE_PERMISSIONS, get_or_create_role
        assigned = (invitation.role_name or "member").strip().lower()
        if assigned not in ROLE_PERMISSIONS or assigned == "owner":
            assigned = "member"
        role = get_or_create_role(db, assigned)
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


def set_job_role(db, actor, target_user_id: str, role_name: str) -> dict:
    """Owner or team manager sets job role. Owner-only for ai_admin assignment."""
    from app.services.seed import ROLE_PERMISSIONS, get_or_create_role
    company = db.get(Company, actor.company_id)
    if not can_manage_team(actor, company):
        raise auth_sessions.AuthError("Not allowed to change job roles", 403)
    is_owner = company.owner_user_id == actor.id and getattr(actor.role, "name", None) == "owner"
    role_name = (role_name or "").strip().lower()
    if role_name == "owner" or role_name not in ROLE_PERMISSIONS:
        raise auth_sessions.AuthError("Invalid job role", 400)
    if not is_owner and role_name not in ADMIN_INVITE_ROLES:
        raise auth_sessions.AuthError("Only the owner can assign AI Administrator", 403)
    target = db.scalar(select(User).where(User.id == target_user_id, User.company_id == company.id))
    if not target or target.status != "active":
        raise auth_sessions.AuthError("Employee not found", 404)
    if target.id == company.owner_user_id or target.role.name == "owner":
        raise auth_sessions.AuthError("Owner role cannot be changed", 403)
    target.role_id = get_or_create_role(db, role_name).id
    target.auth_version += 1
    auth_sessions.revoke_all(db, target, "role_change")
    record_audit(
        db,
        company_id=company.id,
        user_id=actor.id,
        action="company.user.role_update",
        resource_type="user",
        resource_id=target.id,
        status="success",
        details={"role": role_name},
    )
    if role_name in {
        "reservation", "member", "manager", "contract_manager",
        "administration", "accounting", "ai_admin",
    }:
        try:
            from app.services.access import grant_all_agents_to_user
            grant_all_agents_to_user(db, company_id=company.id, user_id=target.id)
        except Exception:
            pass
    db.commit()
    return {"user_id": target.id, "role": role_name}
