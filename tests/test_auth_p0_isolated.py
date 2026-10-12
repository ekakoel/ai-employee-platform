"""P0 regressions: only an in-memory DB and an app without production lifespan.

Run this file explicitly, never alongside the existing file-based DB fixtures.
The global application engine is guarded against any accidental connection.
"""

import ast
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from secrets import token_hex

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from jose import jwt
from pydantic import ValidationError
from sqlalchemy import create_engine, event, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool


def memory_only_sqlite(event_name, arguments):
    if event_name == "sqlite3.connect" and arguments[0] != ":memory:":
        raise AssertionError("P0 tests cannot open any file-backed SQLite database")


sys.addaudithook(memory_only_sqlite)

from app.api import admin_routes, auth_routes, company_onboarding_routes, inbox_routes, result_routes, routes
from app.core.config import Settings, settings
from app.core.database import Base, engine as application_engine, get_db
from app.core.passwords import hash_password
from app.core.security import create_access_token, decode_token
from app.models.entities import AuditLog, AuthSession, Company, User
from app.services.seed import get_or_create_role, seed_catalog


@pytest.fixture(autouse=True)
def forbid_application_database():
    def reject_connection(*_args, **_kwargs):
        raise AssertionError("P0 tests must not connect to the application database")

    event.listen(application_engine, "do_connect", reject_connection)
    event.listen(application_engine, "checkout", reject_connection)
    yield
    event.remove(application_engine, "do_connect", reject_connection)
    event.remove(application_engine, "checkout", reject_connection)


@pytest.fixture()
def isolated():
    engine = create_engine(
        "sqlite://", poolclass=StaticPool, connect_args={"check_same_thread": False},
    )
    assert engine.url.database is None
    assert engine is not application_engine
    with engine.connect() as connection:
        assert connection.exec_driver_sql("PRAGMA database_list").one()[2] == ""
    Base.metadata.create_all(engine)
    sessions = sessionmaker(bind=engine, expire_on_commit=False)
    identities = {}
    password = "isolated-password-123"
    with sessions() as db:
        seed_catalog(db)
        companies = [Company(name="P0 Company A"), Company(name="P0 Company B"), Company(name="P0 Empty")]
        db.add_all(companies)
        db.flush()
        password_hash = hash_password(password)
        for key, company, role, admin in [
            ("owner_a", companies[0], "owner", False),
            ("member_a", companies[0], "member", False),
            ("administration_a", companies[0], "administration", False),
            ("owner_b", companies[1], "owner", False),
            ("admin", companies[0], "owner", True),
        ]:
            user = User(
                company_id=company.id, name=key, email=f"{key}@p0.example",
                role_id=get_or_create_role(db, role).id,
                password_hash=password_hash, is_platform_admin=admin,
            )
            db.add(user)
            db.flush()
            session = AuthSession(user_id=user.id, company_id=company.id, auth_version=user.auth_version,
                                  absolute_expires_at=datetime.now(timezone.utc) + timedelta(days=14))
            db.add(session)
            db.flush()
            token = create_access_token(subject=user.id, company_id=company.id,
                                        session_id=session.id, auth_version=user.auth_version)
            identities[key] = {"id": user.id, "company_id": company.id, "email": user.email, "token": token}
        companies[0].owner_user_id = identities["owner_a"]["id"]
        companies[1].owner_user_id = identities["owner_b"]["id"]
        db.commit()
        empty_company_id = companies[2].id

    # This app mounts real routers, but has no migration/seed/storage lifespan.
    app = FastAPI()
    for router in [auth_routes.router, company_onboarding_routes.router, admin_routes.router, routes.router, result_routes.router, inbox_routes.router]:
        app.include_router(router)

    def memory_db():
        with sessions() as db:
            yield db

    app.dependency_overrides[get_db] = memory_db
    with TestClient(app) as client:
        yield client, identities, sessions, password, empty_company_id
    engine.dispose()


def bearer(identities, key, **extra):
    user = identities[key]
    token = user["token"]
    if extra:
        claims = decode_token(token)
        claims.update(extra)
        token = jwt.encode(claims, settings.jwt_secret, algorithm=settings.jwt_algorithm)
    return {"Authorization": f"Bearer {token}"}


@pytest.mark.parametrize("environment", ["development", "production"])
def test_passwordless_token_is_disabled_even_with_legacy_flags(isolated, monkeypatch, environment):
    client, users, sessions, _, _ = isolated
    monkeypatch.setattr(settings, "auth_enabled", False)
    monkeypatch.setattr(settings, "allow_legacy_user_header", True)
    monkeypatch.setattr(settings, "app_env", environment)
    response = client.post("/api/v1/auth/token", json=users["admin"])
    assert response.status_code == 410
    assert "access_token" not in response.json()
    with sessions() as db:
        assert db.scalar(select(User.id).where(User.id == users["admin"]["id"]))


@pytest.mark.parametrize("role", ["member", "owner", "manager", "ai_admin", "administration"])
def test_public_registration_cannot_select_tenant_or_role(isolated, role):
    client, users, sessions, _, _ = isolated
    response = client.post("/api/v1/auth/register", json={
        "company_id": users["owner_b"]["company_id"], "email": "outsider@p0.example",
        "company_name": "Outsider Company", "owner_name": "Outsider", "password": "outsider-password-123", "role": role,
        "is_platform_admin": True,
    })
    assert response.status_code == 422
    with sessions() as db:
        assert db.scalar(select(User.id).where(User.email == "outsider@p0.example")) is None


ADMIN_REQUESTS = [
    ("GET", "/companies", None),
    ("POST", "/companies", {"name": "New", "owner_email": "new@p0.example", "owner_password": "owner-password-123"}),
    ("PATCH", "/companies/{company}", {"name": "Renamed"}),
    ("GET", "/companies/{company}/users", None),
    ("GET", "/companies/{company}/agents", None),
    ("POST", "/companies/{company}/disable", {}),
    ("POST", "/companies/{company}/enable", {}),
    ("GET", "/companies/{company}/audit", None),
    ("GET", "/companies/{company}/usage", None),
    ("POST", "/users/{user}/grant-platform-admin", {}),
    ("POST", "/impersonate", {"user_id": "unused"}),
]


@pytest.mark.parametrize("method,path,payload", ADMIN_REQUESTS)
@pytest.mark.parametrize("credential", ["header_only", "member_with_admin_header"])
def test_every_admin_endpoint_rejects_spoofed_identity(isolated, method, path, payload, credential):
    client, users, _, _, _ = isolated
    headers = {"X-User-ID": users["admin"]["id"]}
    if credential == "member_with_admin_header":
        headers.update(bearer(users, "member_a"))
    path = path.format(company=users["owner_b"]["company_id"], user=users["member_a"]["id"])
    response = client.request(method, "/api/v1/admin" + path, headers=headers, json=payload)
    assert response.status_code == (401 if credential == "header_only" else 403)


def test_admin_token_overrides_non_admin_header(isolated):
    client, users, _, _, _ = isolated
    headers = {**bearer(users, "admin"), "X-User-ID": users["member_a"]["id"]}
    assert client.get("/api/v1/admin/companies", headers=headers).status_code == 200
    assert client.get("/api/v1/auth/me", headers=headers).json()["user_id"] == users["admin"]["id"]


@pytest.mark.parametrize("kind", ["invalid", "expired", "refresh", "inactive", "reset", "old_reset", "unknown_user"])
def test_admin_and_company_fail_closed_for_invalid_credentials(isolated, kind):
    client, users, sessions, _, _ = isolated
    user = users["admin"]
    if kind == "invalid":
        token = "not-a-jwt"
    elif kind == "expired":
        token = jwt.encode({"sub": user["id"], "company_id": user["company_id"], "type": "access",
                            "exp": datetime.now(timezone.utc) - timedelta(minutes=1)},
                           settings.jwt_secret, algorithm=settings.jwt_algorithm)
    elif kind == "refresh":
        claims = decode_token(user["token"])
        claims["type"] = "refresh"
        token = jwt.encode(claims, settings.jwt_secret, algorithm=settings.jwt_algorithm)
    elif kind == "unknown_user":
        claims = decode_token(user["token"])
        claims["sub"] = "missing-user"
        token = jwt.encode(claims, settings.jwt_secret, algorithm=settings.jwt_algorithm)
    else:
        extra = {"purpose": "password_reset"} if kind in {"reset", "old_reset"} else None
        if kind == "reset":
            extra["type"] = "password_reset"
        claims = decode_token(user["token"])
        claims.update(extra or {})
        token = jwt.encode(claims, settings.jwt_secret, algorithm=settings.jwt_algorithm)
        if kind == "inactive":
            with sessions() as db:
                db.get(User, user["id"]).status = "inactive"
                db.commit()
    headers = {"Authorization": f"Bearer {token}", "X-User-ID": user["id"]}
    for path in ["/api/v1/admin/companies", f"/api/v1/companies/{user['company_id']}/users"]:
        assert client.get(path, headers=headers).status_code == 401


def test_company_token_cannot_be_replaced_by_other_tenant_header(isolated):
    client, users, _, _, _ = isolated
    headers = {**bearer(users, "owner_a"), "X-User-ID": users["owner_b"]["id"]}
    assert client.get(f"/api/v1/companies/{users['owner_b']['company_id']}/users", headers=headers).status_code == 403
    response = client.get(f"/api/v1/companies/{users['owner_a']['company_id']}/users", headers=headers)
    assert response.status_code == 200
    assert all(row["company_id"] == users["owner_a"]["company_id"] for row in response.json())


def test_company_routes_use_bearer_without_middleware(isolated):
    client, users, _, _, _ = isolated
    company = users["member_a"]["company_id"]
    for path in [f"/companies/{company}/agents", f"/companies/{company}/result-pins",
                 f"/companies/{company}/inbox-attribution/task", f"/companies/{company}/marketplace/installations"]:
        assert client.get("/api/v1" + path, headers=bearer(users, "member_a")).status_code == 200
        assert client.get("/api/v1" + path, headers={"X-User-ID": users["member_a"]["id"]}).status_code == 401


def test_email_allowlist_never_grants_and_existing_admin_is_preserved(isolated, monkeypatch):
    client, users, sessions, password, _ = isolated
    monkeypatch.setattr(settings, "platform_admin_emails", users["member_a"]["email"])
    for key, expected in [("member_a", False), ("admin", True)]:
        login = client.post("/api/v1/auth/login", json={"email": users[key]["email"], "password": password})
        assert login.status_code == 200
        assert login.json()["is_platform_admin"] is expected
        headers = {"Authorization": f"Bearer {login.json()['access_token']}"}
        assert client.get("/api/v1/auth/me", headers=headers).json()["is_platform_admin"] is expected
        with sessions() as db:
            assert db.get(User, users[key]["id"]).is_platform_admin is expected


def test_authenticated_platform_grant_remains_supported(isolated):
    client, users, _, _, _ = isolated
    response = client.post(f"/api/v1/admin/users/{users['member_a']['id']}/grant-platform-admin",
                           headers=bearer(users, "admin"))
    assert response.status_code == 200
    assert response.json()["is_platform_admin"] is True


def test_company_creation_and_first_user_cannot_bootstrap_anonymous(isolated, monkeypatch):
    client, users, _, _, empty_company = isolated
    monkeypatch.setattr(settings, "public_company_create", True)
    assert client.post("/api/v1/companies", json={"name": "Anonymous"}).status_code == 401
    assert client.post("/api/v1/companies", headers=bearer(users, "owner_a"), json={"name": "Unauthorized"}).status_code == 403
    response = client.post(f"/api/v1/companies/{empty_company}/users", json={
        "name": "Untrusted", "email": "untrusted@p0.example", "password": "untrusted-password", "role": "owner",
    }, headers={"X-User-ID": users["admin"]["id"]})
    assert response.status_code == 401


def test_admin_provisions_company_and_server_assigned_owner(isolated):
    client, users, sessions, _, _ = isolated
    response = client.post("/api/v1/admin/companies", headers=bearer(users, "admin"), json={
        "name": "Provisioned", "owner_name": "Company owner", "owner_email": "provisioned@p0.example",
        "owner_password": "provisioned-password-123", "role": "member", "is_platform_admin": True,
    })
    assert response.status_code == 201
    body = response.json()
    assert body["owner"]["role"] == "owner"
    with sessions() as db:
        owner = db.get(User, body["owner"]["id"])
        assert owner.company_id == body["company"]["id"]
        assert owner.role.name == "owner"
        assert owner.is_platform_admin is False
    login = client.post("/api/v1/auth/login", json={"email": "provisioned@p0.example", "password": "provisioned-password-123"})
    assert login.status_code == 200


def test_provisioning_requires_explicit_owner_password(isolated):
    client, users, _, _, _ = isolated
    response = client.post("/api/v1/admin/companies", headers=bearer(users, "admin"),
                           json={"name": "Missing password", "owner_email": "missing@p0.example"})
    assert response.status_code == 422


def test_owner_assignment_and_administration_escalation_are_denied(isolated):
    client, users, _, _, _ = isolated
    company = users["administration_a"]["company_id"]
    headers = bearer(users, "administration_a")
    assert client.patch(f"/api/v1/companies/{company}/users/{users['administration_a']['id']}",
                        headers=headers, json={"role": "owner"}).status_code == 403
    assert client.post(f"/api/v1/companies/{company}/users", headers=headers, json={
        "name": "Extra owner", "email": "extra@p0.example", "role": "owner",
    }).status_code == 410
    assert client.patch(f"/api/v1/companies/{company}/users/{users['owner_a']['id']}",
                        headers=headers, json={"role": "member"}).status_code == 403


def test_authorized_invitation_records_verified_actor(isolated, monkeypatch):
    client, users, sessions, _, _ = isolated
    monkeypatch.setattr(settings, "debug", True)
    monkeypatch.setattr(settings, "app_env", "test")
    company = users["owner_a"]["company_id"]
    headers = {**bearer(users, "owner_a"), "X-User-ID": users["owner_b"]["id"]}
    response = client.post(f"/api/v1/companies/{company}/invitations", headers=headers, json={
        "email": "employee@p0.example",
    })
    assert response.status_code == 201
    token = response.json()["invitation_token"]
    accepted = client.post("/api/v1/auth/accept-invitation", json={
        "token": token, "name": "New employee", "password": "employee-password-123",
    })
    assert accepted.status_code == 201
    with sessions() as db:
        audit = db.scalar(select(AuditLog).where(AuditLog.action == "company.invitation.create"))
        assert audit.user_id == users["owner_a"]["id"]
    assert client.post("/api/v1/auth/login", json={"email": "employee@p0.example", "password": "employee-password-123"}).status_code == 200


def test_public_company_onboarding_and_owner_controls(isolated, monkeypatch):
    client, users, sessions, _, _ = isolated
    monkeypatch.setattr(settings, "debug", True)
    monkeypatch.setattr(settings, "app_env", "test")
    monkeypatch.setattr(settings, "smtp_host", "")
    response = client.post("/api/v1/auth/register", json={
        "company_name": "New Company", "owner_name": "New Owner",
        "email": "new.owner@example.test", "password": "strong-password-123",
    })
    assert response.status_code == 201
    company_id = response.json()["company_id"]
    token = response.json()["verification_token"]
    assert token
    assert client.post("/api/v1/auth/login", json={
        "email": "new.owner@example.test", "password": "strong-password-123",
    }).status_code == 401
    assert client.post("/api/v1/auth/verify-email", json={"token": token}).status_code == 200
    assert client.post("/api/v1/auth/verify-email", json={"token": token}).status_code == 400
    login = client.post("/api/v1/auth/login", json={
        "email": "new.owner@example.test", "password": "strong-password-123",
        "company_id": users["owner_b"]["company_id"],
    })
    assert login.status_code == 200
    pair = login.json()
    assert pair["company_id"] == company_id
    headers = {"Authorization": f"Bearer {pair['access_token']}", "X-User-ID": users["admin"]["id"]}
    assert client.get(f"/api/v1/companies/{company_id}/users", headers=headers).status_code == 403
    assert client.get(f"/api/v1/companies/{company_id}/profile", headers=headers).status_code == 200
    assert client.put(f"/api/v1/companies/{company_id}/profile", headers=headers, json={
        "name": "New Company", "contact_email": "contact@example.test", "industry": "Travel",
    }).status_code == 200
    assert client.get(f"/api/v1/companies/{company_id}/users", headers=headers).status_code == 200
    assert client.get(f"/api/v1/companies/{users['owner_b']['company_id']}/profile", headers=headers).status_code == 403
    with sessions() as db:
        company = db.get(Company, company_id)
        owner = db.get(User, pair["user_id"])
        assert company.owner_user_id == owner.id
        assert owner.role.name == "owner" and not owner.is_platform_admin


def test_invitation_single_use_admin_grant_and_session_revocation(isolated, monkeypatch):
    client, users, sessions, _, _ = isolated
    monkeypatch.setattr(settings, "debug", True)
    monkeypatch.setattr(settings, "app_env", "test")
    monkeypatch.setattr(settings, "smtp_host", "")
    company = users["owner_a"]["company_id"]
    owner_headers = bearer(users, "owner_a")
    assert client.post(f"/api/v1/companies/{company}/invitations", headers=bearer(users, "member_a"),
                       json={"email": "staff@example.test"}).status_code == 403
    invite = client.post(f"/api/v1/companies/{company}/invitations", headers=owner_headers,
                         json={"email": "staff@example.test"})
    assert invite.status_code == 201
    token = invite.json()["invitation_token"]
    payload = {"token": token, "name": "Staff", "password": "staff-password-123"}
    assert client.post("/api/v1/auth/accept-invitation", json=payload).status_code == 201
    assert client.post("/api/v1/auth/accept-invitation", json=payload).status_code == 400
    pair = client.post("/api/v1/auth/login", json={
        "email": "staff@example.test", "password": "staff-password-123",
    }).json()
    staff_headers = {"Authorization": f"Bearer {pair['access_token']}"}
    endpoint = f"/api/v1/companies/{company}/administrators/{pair['user_id']}"
    assert client.put(endpoint, headers=staff_headers, json={"administrator": True}).status_code == 403
    assert client.put(endpoint, headers=owner_headers, json={"administrator": True}).status_code == 200
    assert client.get("/api/v1/auth/me", headers=staff_headers).status_code == 401
    updated = client.post("/api/v1/auth/login", json={
        "email": "staff@example.test", "password": "staff-password-123",
    }).json()
    assert updated["role"] == "ai_admin" and "agent.manage" in updated["permissions"]
    assert client.put(endpoint, headers=owner_headers, json={"administrator": False}).status_code == 200
    with sessions() as db:
        assert db.get(User, pair["user_id"]).role.name == "member"


def test_public_registration_duplicate_email_and_missing_delivery(isolated, monkeypatch):
    client, users, sessions, _, _ = isolated
    payload = {"company_name": "Duplicate Email Company", "owner_name": "Owner",
               "email": users["owner_a"]["email"], "password": "strong-password-123"}
    monkeypatch.setattr(settings, "debug", True)
    monkeypatch.setattr(settings, "app_env", "test")
    monkeypatch.setattr(settings, "smtp_host", "")
    assert client.post("/api/v1/auth/register", json=payload).status_code == 409
    monkeypatch.setattr(settings, "debug", False)
    monkeypatch.setattr(settings, "app_env", "production")
    assert client.post("/api/v1/auth/register", json={**payload, "email": "fresh@example.test"}).status_code == 503
    with sessions() as db:
        assert db.scalar(select(Company.id).where(Company.name == "Duplicate Email Company")) is None


def test_registration_retry_does_not_create_second_company(isolated, monkeypatch):
    client, _, sessions, _, _ = isolated
    monkeypatch.setattr(settings, "debug", True)
    monkeypatch.setattr(settings, "app_env", "test")
    monkeypatch.setattr(settings, "smtp_host", "")
    payload = {"company_name": "Retry Company", "owner_name": "Owner",
               "email": "retry@example.test", "password": "strong-password-123"}
    assert client.post("/api/v1/auth/register", json=payload).status_code == 201
    assert client.post("/api/v1/auth/register", json=payload).status_code == 409
    with sessions() as db:
        assert len(db.scalars(select(Company).where(Company.name == "Retry Company")).all()) == 1


def test_invitation_revocation_and_expiration_are_audited(isolated, monkeypatch):
    client, users, sessions, _, _ = isolated
    monkeypatch.setattr(settings, "debug", True)
    monkeypatch.setattr(settings, "app_env", "test")
    monkeypatch.setattr(settings, "smtp_host", "")
    company = users["owner_a"]["company_id"]
    headers = bearer(users, "owner_a")
    first = client.post(f"/api/v1/companies/{company}/invitations", headers=headers,
                        json={"email": "revoked@example.test"}).json()
    invitation = client.get(f"/api/v1/companies/{company}/invitations", headers=headers).json()[0]
    assert client.post(f"/api/v1/companies/{company}/invitations/{invitation['id']}/revoke",
                       headers=headers).status_code == 204
    assert client.post("/api/v1/auth/accept-invitation", json={
        "token": first["invitation_token"], "name": "Revoked", "password": "strong-password-123",
    }).status_code == 400
    second = client.post(f"/api/v1/companies/{company}/invitations", headers=headers,
                         json={"email": "expired@example.test"}).json()
    from app.models.entities import CompanyInvitation
    with sessions() as db:
        row = db.scalar(select(CompanyInvitation).where(CompanyInvitation.email == "expired@example.test"))
        row.expires_at = datetime.now(timezone.utc) - timedelta(seconds=1)
        db.commit()
    assert client.post("/api/v1/auth/accept-invitation", json={
        "token": second["invitation_token"], "name": "Expired", "password": "strong-password-123",
    }).status_code == 400
    with sessions() as db:
        actions = set(db.scalars(select(AuditLog.action).where(AuditLog.company_id == company)).all())
        assert {"company.invitation.revoke", "company.invitation.expired"} <= actions


def test_login_and_refresh_still_require_valid_credentials(isolated):
    client, users, _, password, _ = isolated
    assert client.post("/api/v1/auth/login", json={"email": users["admin"]["email"]}).status_code == 422
    assert client.post("/api/v1/auth/login", json={"email": users["admin"]["email"], "password": "incorrect-password"}).status_code == 401
    assert client.post("/api/v1/auth/refresh", json={"refresh_token": "invalid"}).status_code == 401
    pair = client.post("/api/v1/auth/login", json={"email": users["admin"]["email"], "password": password}).json()
    refreshed = client.post("/api/v1/auth/refresh", json={"refresh_token": pair["refresh_token"]})
    assert refreshed.status_code == 200
    assert refreshed.json()["user_id"] == users["admin"]["id"]


def test_forgot_password_does_not_issue_an_access_token(isolated, monkeypatch):
    client, users, _, _, _ = isolated
    monkeypatch.setattr(settings, "debug", True)
    response = client.post("/api/v1/auth/forgot-password", json={"email": users["admin"]["email"]})
    token = response.json()["reset_token"]
    assert decode_token(token)["type"] == "password_reset"
    assert client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"}).status_code == 401
    assert client.post("/api/v1/auth/refresh", json={"refresh_token": token}).status_code == 401
    assert client.post("/api/v1/auth/reset-password", json={"token": token, "new_password": "reset-password-123"}).status_code == 200


def secure_settings(**overrides):
    values = dict(app_env="production", debug=False, auth_enabled=True,
                  allow_legacy_user_header=False, public_company_create=False,
                  jwt_secret=token_hex(32), database_url="sqlite://")
    values.update(overrides)
    return Settings(_env_file=None, **values)


@pytest.mark.parametrize("overrides", [
    {"auth_enabled": False}, {"allow_legacy_user_header": True}, {"debug": True},
    {"public_company_create": True}, {"jwt_secret": "dev-change-me-in-production"},
    {"jwt_secret": "change-me-in-production"}, {"jwt_secret": "short"},
    {"jwt_secret": ""}, {"jwt_algorithm": "none"}, {"app_env": "produciton"},
])
def test_unsafe_production_configuration_is_rejected(overrides):
    with pytest.raises(ValidationError):
        secure_settings(**overrides)


@pytest.mark.parametrize("environment", ["production", "prod", " Production ", "release", "staging", "stage"])
def test_environment_aliases_cannot_bypass_security(environment):
    with pytest.raises(ValidationError):
        secure_settings(app_env=environment, auth_enabled=False)
    secure_settings(app_env=environment).validate_security()


def test_validation_error_does_not_print_signing_secret():
    secret = token_hex(32)
    with pytest.raises(ValidationError) as caught:
        secure_settings(jwt_secret=secret, auth_enabled=False)
    assert secret not in str(caught.value)


def test_runtime_revalidation_precedes_database_startup():
    # Inspect startup ordering without importing/running the production app.
    tree = ast.parse(Path("app/main.py").read_text(encoding="utf-8"))
    lifespan = next(node for node in tree.body if isinstance(node, ast.AsyncFunctionDef) and node.name == "lifespan")
    assert ast.unparse(lifespan.body[0]) == "settings.validate_security()"
    configured = secure_settings()
    configured.auth_enabled = False
    with pytest.raises(ValueError):
        configured.validate_security()
