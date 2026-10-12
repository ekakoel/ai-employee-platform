"""Session lifecycle with database-owned serialization and digest-only records."""

from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from hashlib import sha256
import hmac
import logging
from uuid import UUID, uuid4

from sqlalchemy import select, update
from sqlalchemy.exc import SQLAlchemyError

from app.core.config import settings
from app.core.passwords import hash_password, verify_password
from app.core.security import create_access_token, create_refresh_token, create_reset_token, decode_access_token, decode_token
from app.models.entities import AuthSession, Company, PasswordResetRecord, RefreshTokenRecord, User
from app.services.access import user_permission_keys
from app.services.audit import record_audit

logger = logging.getLogger("app.security.auth")


class AuthError(Exception):
    def __init__(self, message="Invalid or expired session", status=401):
        super().__init__(message)
        self.status = status


class AuthUnavailable(AuthError):
    def __init__(self):
        super().__init__("Authentication temporarily unavailable", 503)


def now():
    return datetime.now(timezone.utc)


def utc(value):
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)


def digest(token):
    return sha256(token.encode("utf-8")).hexdigest()


def security_failure(action):
    # No unverified tenant, email, request body, exception, or credential is logged.
    logger.warning("auth rejected: %s", action)


def event(db, user, action, session_id=None, reason=None, request_id=None):
    details = {"reason": reason} if reason else {}
    if request_id:
        try:
            details["request_id"] = str(UUID(request_id))
        except (ValueError, TypeError, AttributeError):
            pass
    record_audit(db, company_id=user.company_id, user_id=user.id, action=action,
                 resource_type="auth_session" if session_id else "user",
                 resource_id=session_id or user.id, status="success", details=details)


@contextmanager
def transaction(db):
    try:
        yield
        db.commit()
    except SQLAlchemyError:
        db.rollback()
        raise AuthUnavailable() from None
    except Exception:
        db.rollback()
        raise


def lock_user(db, user_id):
    # A real write serializes the owner across workers on SQLite and PostgreSQL.
    # All lifecycle mutations acquire this lock before reading mutable credentials.
    result = db.execute(update(User).where(User.id == user_id).values(auth_version=User.auth_version)
                        .execution_options(synchronize_session=False))
    if result.rowcount != 1:
        raise AuthError()
    db.expire_all()
    return db.get(User, user_id)


def active_user(db, user):
    if not user or user.status != "active":
        raise AuthError()
    company = db.get(Company, user.company_id, populate_existing=True)
    if not company or not company.is_active:
        raise AuthError()


def bound_session(db, claims, allow_revoked=False):
    user = db.get(User, claims["sub"], populate_existing=True)
    active_user(db, user)
    session = db.get(AuthSession, claims["sid"], populate_existing=True)
    if (not session or session.user_id != user.id or
        session.company_id != user.company_id or claims["company_id"] != user.company_id or
        session.auth_version != user.auth_version or claims["ver"] != user.auth_version or
        utc(session.absolute_expires_at) <= now() or (session.revoked_at and not allow_revoked)):
        raise AuthError()
    return user, session


def validate_access(db, token, allow_revoked=False):
    try:
        return bound_session(db, decode_access_token(token), allow_revoked)
    except ValueError:
        raise AuthError() from None
    except SQLAlchemyError:
        db.rollback()
        raise AuthUnavailable() from None


def issue_pair(db, user, session):
    timestamp = now()
    expiry = utc(session.absolute_expires_at)
    identifier = str(uuid4())
    refresh = create_refresh_token(subject=user.id, company_id=user.company_id, session_id=session.id,
                                   token_id=identifier, auth_version=user.auth_version, expires_at=expiry)
    db.add(RefreshTokenRecord(id=identifier, session_id=session.id, token_digest=digest(refresh),
                              issued_at=timestamp, expires_at=expiry))
    access = create_access_token(subject=user.id, company_id=user.company_id, session_id=session.id,
                                 auth_version=user.auth_version,
                                 expires_at=min(expiry, timestamp + timedelta(minutes=settings.jwt_expire_minutes)))
    return {"access_token": access, "refresh_token": refresh, "token_type": "bearer",
            "user_id": user.id, "company_id": user.company_id, "email": user.email, "name": user.name,
            "role": user.role.name if user.role else None, "permissions": sorted(user_permission_keys(user)),
            "is_platform_admin": bool(user.is_platform_admin)}, identifier


def login(db, email, password, company_id=None, request_id=None):
    with transaction(db):
        query = select(User).join(Company).where(User.email == email.strip().lower(), User.status == "active", Company.is_active.is_(True))
        if company_id:
            query = query.where(User.company_id == company_id)
        candidates = list(db.scalars(query).all())
        if len(candidates) > 1:
            if any(verify_password(password, user.password_hash) for user in candidates):
                security_failure("login.ambiguous_company")
                raise AuthError("Company context required for this account", 409)
            candidates = []
        if not candidates:
            security_failure("login.invalid_credentials")
            raise AuthError("Invalid email or password")
        user = lock_user(db, candidates[0].id)
        active_user(db, user)
        if not verify_password(password, user.password_hash):
            security_failure("login.invalid_credentials")
            raise AuthError("Invalid email or password")
        timestamp = now()
        session = AuthSession(id=str(uuid4()), user_id=user.id, company_id=user.company_id,
                              auth_version=user.auth_version, created_at=timestamp,
                              absolute_expires_at=timestamp + timedelta(minutes=settings.jwt_refresh_expire_minutes))
        db.add(session)
        db.flush()
        pair, _ = issue_pair(db, user, session)
        event(db, user, "auth.login", session.id, request_id=request_id)
    return pair


def refresh(db, token, request_id=None):
    try:
        claims = decode_token(token, expected_type="refresh")
    except ValueError:
        security_failure("refresh.invalid_token")
        raise AuthError() from None
    with transaction(db):
        lock_user(db, claims["sub"])
        user, session = bound_session(db, claims)
        record = db.get(RefreshTokenRecord, claims["jti"])
        if (not record or record.session_id != session.id or
            not hmac.compare_digest(record.token_digest, digest(token)) or utc(record.expires_at) <= now()):
            raise AuthError()
        result = db.execute(update(RefreshTokenRecord).where(
            RefreshTokenRecord.id == record.id, RefreshTokenRecord.consumed_at.is_(None)
        ).values(consumed_at=now()).execution_options(synchronize_session=False))
        if result.rowcount != 1:
            session.revoked_at = now()
            session.revoke_reason = "refresh_replay"
            event(db, user, "auth.refresh_replay", session.id, "consumed_token", request_id)
            event(db, user, "auth.revoke_session", session.id, "refresh_replay", request_id)
            # Persist the security response before raising; outer rollback cannot undo it.
            db.commit()
            raise AuthError("Session revoked after refresh replay")
        pair, replacement = issue_pair(db, user, session)
        db.flush()
        record.replaced_by = replacement
        event(db, user, "auth.refresh", session.id, request_id=request_id)
    return pair


def revoke_all(db, user, reason, request_id=None):
    db.execute(update(AuthSession).where(AuthSession.user_id == user.id,
               AuthSession.company_id == user.company_id, AuthSession.revoked_at.is_(None)
               ).values(revoked_at=now(), revoke_reason=reason).execution_options(synchronize_session=False))
    event(db, user, "auth.revoke_all", reason=reason, request_id=request_id)


def logout(db, token, all_sessions=False, request_id=None):
    try:
        claims = decode_access_token(token)
    except ValueError:
        raise AuthError() from None
    with transaction(db):
        lock_user(db, claims["sub"])
        user, session = bound_session(db, claims, allow_revoked=True)
        if session.revoked_at:
            return
        if all_sessions:
            revoke_all(db, user, "logout_all", request_id)
        else:
            session.revoked_at = now()
            session.revoke_reason = "logout"
            event(db, user, "auth.revoke_session", session.id, "logout", request_id)
        event(db, user, "auth.logout_all" if all_sessions else "auth.logout", session.id, request_id=request_id)


def request_reset(db, email, company_id=None, request_id=None):
    token = None
    with transaction(db):
        query = select(User).join(Company).where(User.email == email.strip().lower(), User.status == "active", Company.is_active.is_(True))
        if company_id:
            query = query.where(User.company_id == company_id)
        users = list(db.scalars(query).all())
        if len(users) != 1:
            return None
        user = lock_user(db, users[0].id)
        try:
            active_user(db, user)
        except AuthError:
            return None
        timestamp = now()
        expiry = timestamp + timedelta(minutes=30)
        identifier = str(uuid4())
        token = create_reset_token(subject=user.id, company_id=user.company_id, token_id=identifier,
                                   auth_version=user.auth_version, expires_at=expiry)
        db.add(PasswordResetRecord(id=identifier, user_id=user.id, company_id=user.company_id,
                                  auth_version=user.auth_version, token_digest=digest(token),
                                  issued_at=timestamp, expires_at=expiry))
        event(db, user, "auth.forgot_password", request_id=request_id)
    return token


def reset_password(db, token, new_password, request_id=None):
    try:
        claims = decode_token(token, expected_type="password_reset")
    except ValueError:
        raise AuthError("Invalid or expired reset token", 400) from None
    with transaction(db):
        user = lock_user(db, claims["sub"])
        active_user(db, user)
        record = db.get(PasswordResetRecord, claims["jti"])
        if (not record or record.user_id != user.id or record.company_id != user.company_id or
            claims["company_id"] != user.company_id or record.auth_version != user.auth_version or
            claims["ver"] != user.auth_version or not hmac.compare_digest(record.token_digest, digest(token)) or
            utc(record.expires_at) <= now()):
            raise AuthError("Invalid or expired reset token", 400)
        result = db.execute(update(PasswordResetRecord).where(
            PasswordResetRecord.id == record.id, PasswordResetRecord.consumed_at.is_(None)
        ).values(consumed_at=now()).execution_options(synchronize_session=False))
        if result.rowcount != 1:
            raise AuthError("Invalid or expired reset token", 400)
        user.password_hash = hash_password(new_password)
        user.auth_version += 1
        revoke_all(db, user, "password_reset", request_id)
        event(db, user, "auth.reset_password", request_id=request_id)


def change_password(db, token, current_password, new_password, request_id=None):
    try:
        claims = decode_access_token(token)
    except ValueError:
        raise AuthError() from None
    with transaction(db):
        lock_user(db, claims["sub"])
        user, _ = bound_session(db, claims)
        if not verify_password(current_password, user.password_hash):
            security_failure("password_change.invalid_credentials")
            raise AuthError("Invalid current password")
        user.password_hash = hash_password(new_password)
        user.auth_version += 1
        revoke_all(db, user, "password_change", request_id)
        event(db, user, "auth.change_password", request_id=request_id)
