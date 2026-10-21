"""Lifecycle tests: disposable SQLite only, no application lifespan or network."""

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
import hashlib
import hmac
import importlib.util
import json
from pathlib import Path
import os
import sys
from threading import Barrier
from types import SimpleNamespace
from uuid import uuid4

from alembic.migration import MigrationContext
from alembic.operations import Operations
from alembic import command
from alembic.config import Config
from fastapi import FastAPI
from fastapi.testclient import TestClient
from jose import jwt
import pytest
from sqlalchemy import create_engine, event, inspect, select, text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session, sessionmaker

allowed_roots = set()


def disposable_connections(event_name, arguments):
    if event_name != "sqlite3.connect" or arguments[0] == ":memory:":
        return
    filename = Path(arguments[0]).resolve()
    if not any(filename.is_relative_to(root) for root in allowed_roots):
        raise AssertionError("Session tests must never open workspace SQLite files")


if os.environ.get("AUTH_ISOLATED_GUARDS", "0") == "1":
    sys.addaudithook(disposable_connections)

from app.api import auth_routes, admin_routes, routes, result_routes, inbox_routes
from app.core.config import Settings, settings
from app.core.database import Base, engine as application_engine, get_db
from app.core.passwords import hash_password
from app.core.security import decode_token
from app.models.entities import AuditLog, AuthSession, Company, Integration, PasswordResetRecord, RefreshTokenRecord, User
from app.services import auth_sessions
from app.services.integrations import create_integration
from app.services import automation
from app.services.seed import seed_catalog, get_or_create_role

PASSWORD = "isolated-session-password"
NEW_PASSWORD = "isolated-new-password"


@pytest.fixture(scope="module")
def stored_password():
    return hash_password(PASSWORD)


@pytest.fixture(autouse=True)
def no_application_engine():
    def reject(*args, **kwargs):
        raise AssertionError("Global application engine is forbidden")
    event.listen(application_engine, "do_connect", reject)
    event.listen(application_engine, "checkout", reject)
    yield
    event.remove(application_engine, "do_connect", reject)
    event.remove(application_engine, "checkout", reject)


@pytest.fixture()
def postgres_test_url():
    return None


@pytest.fixture()
def isolated(tmp_path, stored_password, postgres_test_url):
    root = tmp_path.resolve()
    assert not root.is_relative_to(Path.cwd().resolve())
    allowed_roots.add(root)
    database = root / "auth.sqlite3"
    if postgres_test_url:
        base_engine = create_engine(postgres_test_url, hide_parameters=True)
        schema = "aiep_auth_" + uuid4().hex
        with base_engine.begin() as connection:
            connection.execute(text('CREATE SCHEMA "' + schema + '"'))
        engine = base_engine.execution_options(schema_translate_map={None: schema})
    else:
        engine = create_engine("sqlite:///" + database.as_posix(), connect_args={"check_same_thread": False, "timeout": 30}, hide_parameters=True)

        @event.listens_for(engine, "connect")
        def sqlite_integrity(connection, _):
            connection.execute("PRAGMA foreign_keys=ON")

        with engine.connect() as connection:
            filename = connection.exec_driver_sql("PRAGMA database_list").one()[2]
            assert Path(filename).resolve() == database
    Base.metadata.create_all(engine)
    sessions = sessionmaker(bind=engine, expire_on_commit=False, autoflush=False)
    with sessions() as db:
        seed_catalog(db)
        a, b = Company(name="Session A"), Company(name="Session B")
        db.add_all([a, b])
        db.flush()
        role = get_or_create_role(db, "owner")
        user = User(company_id=a.id, email="owner@session.test", name="Owner", role_id=role.id, password_hash=stored_password)
        other = User(company_id=b.id, email="other@session.test", name="Other", role_id=role.id, password_hash=stored_password)
        db.add_all([user, other])
        db.commit()
        identities = {"user": user.id, "other": other.id, "company": a.id, "other_company": b.id}
    app = FastAPI()
    for router in [auth_routes.router, admin_routes.router, routes.router, result_routes.router, inbox_routes.router]:
        app.include_router(router)

    def database_dependency():
        with sessions() as db:
            yield db
    app.dependency_overrides[get_db] = database_dependency
    with TestClient(app, raise_server_exceptions=False) as client:
        yield client, sessions, identities
    engine.dispose()
    allowed_roots.remove(root)


def login(client, email="owner@session.test", password=PASSWORD, **context):
    response = client.post("/api/v1/auth/login", json={"email": email, "password": password, **context})
    assert response.status_code == 200
    return response.json()


def bearer(pair):
    return {"Authorization": "Bearer " + pair["access_token"]}


def refresh(client, pair):
    return client.post("/api/v1/auth/refresh", json={"refresh_token": pair["refresh_token"]})


def me(client, pair):
    return client.get("/api/v1/auth/me", headers=bearer(pair))


def reset_token(client, monkeypatch):
    monkeypatch.setattr(settings, "debug", True)
    response = client.post("/api/v1/auth/forgot-password", json={"email": "owner@session.test"})
    assert response.status_code == 200
    return response.json()["reset_token"]


def reset(client, token):
    return client.post("/api/v1/auth/reset-password", json={"token": token, "new_password": NEW_PASSWORD})


def parallel(*operations):
    barrier = Barrier(len(operations))
    def run(operation):
        barrier.wait(timeout=10)
        return operation()
    with ThreadPoolExecutor(max_workers=len(operations)) as executor:
        futures = [executor.submit(run, operation) for operation in operations]
        return [future.result(timeout=40) for future in futures]


def test_login_persists_session_digest_and_unique_pair(isolated):
    client, sessions, ids = isolated
    pair, second = login(client), login(client)
    access, refresh_claims = decode_token(pair["access_token"]), decode_token(pair["refresh_token"])
    assert access["sid"] == refresh_claims["sid"]
    assert access["jti"] != refresh_claims["jti"]
    assert access["sid"] != decode_token(second["access_token"])["sid"]
    assert me(client, pair).status_code == 200
    with sessions() as db:
        session = db.get(AuthSession, access["sid"])
        record = db.get(RefreshTokenRecord, refresh_claims["jti"])
        assert session.user_id == ids["user"] and session.company_id == ids["company"]
        assert record.token_digest == auth_sessions.digest(pair["refresh_token"])
        assert len(record.token_digest) == 64
        assert bool(record.token_digest != pair["refresh_token"])


@pytest.mark.parametrize("claim", ["exp", "iat", "sub", "company_id", "type", "sid", "jti", "ver"])
def test_required_claims_reject_access_refresh_and_legacy(isolated, claim):
    client, _, _ = isolated
    pair = login(client)
    for kind in ("access_token", "refresh_token"):
        claims = decode_token(pair[kind])
        claims.pop(claim)
        token = jwt.encode(claims, settings.jwt_secret, algorithm=settings.jwt_algorithm)
        response = client.get("/api/v1/auth/me", headers={"Authorization": "Bearer " + token}) if kind == "access_token" else client.post("/api/v1/auth/refresh", json={"refresh_token": token})
        assert response.status_code == 401


@pytest.mark.parametrize("claim", ["company_id", "sub", "sid", "ver"])
def test_claim_binding_cannot_replace_user_company_or_session(isolated, claim):
    client, _, ids = isolated
    pair = login(client)
    for kind in ("access_token", "refresh_token"):
        claims = decode_token(pair[kind])
        claims[claim] = 99 if claim == "ver" else ids["other_company"] if claim == "company_id" else ids["other"] if claim == "sub" else "missing-session"
        token = jwt.encode(claims, settings.jwt_secret, algorithm=settings.jwt_algorithm)
        response = client.get("/api/v1/auth/me", headers={"Authorization": "Bearer " + token}) if kind == "access_token" else client.post("/api/v1/auth/refresh", json={"refresh_token": token})
        assert response.status_code == 401


def test_rotation_replay_revokes_family_and_persists_audit(isolated):
    client, sessions, _ = isolated
    old = login(client)
    response = refresh(client, old)
    assert response.status_code == 200
    new = response.json()
    assert bool(new["refresh_token"] != old["refresh_token"])
    assert me(client, new).status_code == 200
    assert refresh(client, old).status_code == 401
    assert me(client, old).status_code == me(client, new).status_code == 401
    assert refresh(client, new).status_code == 401
    with sessions() as db:
        session = db.get(AuthSession, decode_token(old["access_token"])["sid"])
        assert session.revoke_reason == "refresh_replay" and session.revoked_at is not None
        assert db.scalar(select(AuditLog.id).where(AuditLog.action == "auth.refresh_replay"))


def test_parallel_refresh_has_one_winner_and_replay_revocation(isolated):
    client, sessions, _ = isolated
    pair = login(client)
    responses = parallel(lambda: refresh(client, pair), lambda: refresh(client, pair))
    assert sorted(response.status_code for response in responses) == [200, 401]
    with sessions() as db:
        session = db.get(AuthSession, decode_token(pair["access_token"])["sid"])
        assert session.revoked_at is not None
        records = list(db.scalars(select(RefreshTokenRecord).where(RefreshTokenRecord.session_id == session.id)))
        assert len(records) == 2
        assert sum(record.consumed_at is not None for record in records) == 1


def test_logout_current_is_idempotent_and_does_not_revoke_other_sessions(isolated):
    client, _, _ = isolated
    pair, second = login(client), login(client)
    other = login(client, "other@session.test")
    assert client.post("/api/v1/auth/logout", headers=bearer(pair)).status_code == 204
    assert client.post("/api/v1/auth/logout", headers=bearer(pair)).status_code == 204
    assert me(client, pair).status_code == refresh(client, pair).status_code == 401
    assert me(client, second).status_code == me(client, other).status_code == 200
    assert client.post("/api/v1/auth/logout", json={"refresh_token": second["refresh_token"]}).status_code == 401


def test_logout_all_only_revokes_the_authenticated_owner(isolated):
    client, _, ids = isolated
    pair, second = login(client), login(client)
    other = login(client, "other@session.test")
    headers = {**bearer(pair), "X-User-ID": ids["other"]}
    assert client.post("/api/v1/auth/logout-all", headers=headers).status_code == 204
    assert me(client, pair).status_code == me(client, second).status_code == 401
    assert me(client, other).status_code == 200
    fresh = login(client)
    assert client.post("/api/v1/auth/logout-all", headers=headers).status_code == 204
    assert me(client, fresh).status_code == 200


def test_reset_single_use_invalidates_sessions_and_other_reset_tokens(isolated, monkeypatch):
    client, sessions, ids = isolated
    pair, second = login(client), login(client)
    token, older = reset_token(client, monkeypatch), reset_token(client, monkeypatch)
    assert reset(client, token).status_code == 200
    assert reset(client, token).status_code == reset(client, older).status_code == 400
    assert me(client, pair).status_code == me(client, second).status_code == refresh(client, pair).status_code == 401
    assert login(client, password=NEW_PASSWORD)["user_id"] == ids["user"]
    with sessions() as db:
        record = db.get(PasswordResetRecord, decode_token(token)["jti"])
        assert record.consumed_at is not None and record.token_digest == auth_sessions.digest(token)
        assert db.get(User, ids["user"]).auth_version == 1


def test_parallel_reset_has_one_winner(isolated, monkeypatch):
    client, _, _ = isolated
    token = reset_token(client, monkeypatch)
    responses = parallel(lambda: reset(client, token), lambda: reset(client, token))
    assert sorted(response.status_code for response in responses) == [200, 400]


def test_password_change_requires_current_password_and_revokes_all(isolated):
    client, _, _ = isolated
    pair, second = login(client), login(client)
    assert client.post("/api/v1/auth/change-password", headers=bearer(pair), json={"current_password": "incorrect-password", "new_password": NEW_PASSWORD}).status_code == 401
    assert me(client, pair).status_code == 200
    assert client.post("/api/v1/auth/change-password", headers=bearer(pair), json={"current_password": PASSWORD, "new_password": NEW_PASSWORD}).status_code == 200
    assert me(client, pair).status_code == me(client, second).status_code == refresh(client, second).status_code == 401


def test_parallel_refresh_reset_cannot_restore_old_credentials(isolated, monkeypatch):
    client, sessions, _ = isolated
    pair, token = login(client), reset_token(client, monkeypatch)
    responses = parallel(lambda: refresh(client, pair), lambda: reset(client, token))
    assert responses[1].status_code == 200 and responses[0].status_code in (200, 401)
    assert me(client, pair).status_code == 401
    if responses[0].status_code == 200:
        assert me(client, responses[0].json()).status_code == 401
        assert refresh(client, responses[0].json()).status_code == 401
    with sessions() as db:
        assert all(session.revoked_at for session in db.scalars(select(AuthSession)))


def test_parallel_refresh_password_change_cannot_restore_session(isolated):
    client, sessions, _ = isolated
    pair = login(client)
    responses = parallel(lambda: refresh(client, pair),
                         lambda: client.post("/api/v1/auth/change-password", headers=bearer(pair),
                                             json={"current_password": PASSWORD, "new_password": NEW_PASSWORD}))
    assert responses[1].status_code == 200 and responses[0].status_code in (200, 401)
    assert me(client, pair).status_code == 401
    if responses[0].status_code == 200:
        assert me(client, responses[0].json()).status_code == refresh(client, responses[0].json()).status_code == 401
    with sessions() as db:
        assert all(session.revoked_at for session in db.scalars(select(AuthSession)))


def test_parallel_login_reset_leaves_no_old_credential_session(isolated, monkeypatch):
    client, sessions, _ = isolated
    token = reset_token(client, monkeypatch)
    responses = parallel(lambda: client.post("/api/v1/auth/login", json={"email": "owner@session.test", "password": PASSWORD}), lambda: reset(client, token))
    assert responses[1].status_code == 200 and responses[0].status_code in (200, 401)
    if responses[0].status_code == 200:
        assert me(client, responses[0].json()).status_code == 401
    with sessions() as db:
        assert all(session.revoked_at for session in db.scalars(select(AuthSession)))


@pytest.mark.parametrize("inactive", ["user", "company"])
def test_inactive_account_or_company_rejects_login_access_and_refresh(isolated, inactive):
    client, sessions, ids = isolated
    pair = login(client)
    with sessions() as db:
        if inactive == "user":
            db.get(User, ids["user"]).status = "inactive"
        else:
            db.get(Company, ids["company"]).is_active = False
        db.commit()
    assert me(client, pair).status_code == refresh(client, pair).status_code == 401
    assert client.post("/api/v1/auth/login", json={"email": "owner@session.test", "password": PASSWORD}).status_code == 401


def test_expiry_is_absolute_after_rotation_and_expired_session_rejected(isolated):
    client, sessions, _ = isolated
    old = login(client)
    new = refresh(client, old).json()
    assert decode_token(old["refresh_token"])["exp"] == decode_token(new["refresh_token"])["exp"]
    assert decode_token(new["access_token"])["exp"] <= decode_token(new["refresh_token"])["exp"]
    with sessions() as db:
        db.get(AuthSession, decode_token(old["access_token"])["sid"]).absolute_expires_at = datetime.now(timezone.utc) - timedelta(seconds=1)
        db.commit()
    assert me(client, new).status_code == refresh(client, new).status_code == 401


def test_database_failure_is_503_not_authenticated(isolated, monkeypatch):
    client, _, _ = isolated
    pair = login(client)
    def unavailable(*args, **kwargs):
        raise SQLAlchemyError("simulated database failure")
    monkeypatch.setattr(Session, "get", unavailable)
    assert me(client, pair).status_code == refresh(client, pair).status_code == 503


def test_profile_query_failure_after_session_validation_is_503(isolated, monkeypatch):
    client, _, _ = isolated
    pair = login(client)
    def unavailable(*args, **kwargs):
        raise SQLAlchemyError("simulated permission query failure")
    monkeypatch.setattr(auth_routes, "user_permission_keys", unavailable)
    assert me(client, pair).status_code == 503


def test_failed_rotation_rolls_back_consumption_and_success_audit(isolated, monkeypatch):
    client, sessions, _ = isolated
    old = login(client)
    original = auth_sessions.issue_pair
    def fail_after_issuance(*args):
        original(*args)
        raise SQLAlchemyError("simulated commit failure")
    monkeypatch.setattr(auth_sessions, "issue_pair", fail_after_issuance)
    assert refresh(client, old).status_code == 503
    with sessions() as db:
        record = db.get(RefreshTokenRecord, decode_token(old["refresh_token"])["jti"])
        assert record.consumed_at is None
        assert len(list(db.scalars(select(RefreshTokenRecord)))) == 1
        assert db.scalar(select(AuditLog.id).where(AuditLog.action == "auth.refresh")) is None
    monkeypatch.setattr(auth_sessions, "issue_pair", original)
    assert refresh(client, old).status_code == 200


def test_public_reset_response_consistent_and_ambiguous_email_fails_closed(isolated, monkeypatch):
    client, sessions, ids = isolated
    monkeypatch.setattr(settings, "debug", False)
    known = client.post("/api/v1/auth/forgot-password", json={"email": "owner@session.test"})
    unknown = client.post("/api/v1/auth/forgot-password", json={"email": "missing@session.test"})
    assert known.status_code == unknown.status_code == 200 and known.json() == unknown.json()
    with sessions() as db:
        db.get(User, ids["other"]).email = "owner@session.test"
        db.commit()
    assert client.post("/api/v1/auth/login", json={"email": "owner@session.test", "password": PASSWORD}).status_code == 409
    assert client.post("/api/v1/auth/login", json={"email": "owner@session.test",
        "password": PASSWORD, "company_id": ids["company"]}).status_code == 409
    assert client.post("/api/v1/auth/forgot-password", json={"email": "owner@session.test"}).json() == unknown.json()


def test_audit_and_security_logs_do_not_contain_credentials(isolated, monkeypatch, caplog):
    client, sessions, _ = isolated
    pair = login(client)
    new = refresh(client, pair).json()
    refresh(client, pair)
    token = reset_token(client, monkeypatch)
    reset(client, token)
    client.post("/api/v1/auth/login", json={"email": "owner@session.test", "password": "wrong-secret-password"})
    fresh = login(client, password=NEW_PASSWORD)
    client.post("/api/v1/auth/logout", headers=bearer(fresh))
    with sessions() as db:
        logs = list(db.scalars(select(AuditLog)))
        serialized = json.dumps([{"action": entry.action, "details": entry.details, "resource_id": entry.resource_id} for entry in logs]) + caplog.text
        for secret in [PASSWORD, NEW_PASSWORD, "wrong-secret-password", token, *[pair[key] for key in ("access_token", "refresh_token")], *[new[key] for key in ("access_token", "refresh_token")]]:
            assert bool(secret not in serialized)
        actions = {entry.action for entry in logs}
        assert {"auth.login", "auth.refresh", "auth.refresh_replay", "auth.logout", "auth.revoke_session", "auth.revoke_all", "auth.reset_password"} <= actions


@pytest.mark.parametrize("access,refresh", [(0, 100), (16, 100), (15, 0), (15, 20161)])
def test_invalid_expiry_settings_rejected(access, refresh):
    with pytest.raises(ValueError):
        Settings(_env_file=None, app_env="test", jwt_expire_minutes=access, jwt_refresh_expire_minutes=refresh)


def test_additive_migration_preserves_old_user_and_blocks_security_downgrade(isolated):
    spec = importlib.util.spec_from_file_location("session_migration", "alembic/versions/0004_auth_sessions.py")
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)
    engine = create_engine("sqlite://")
    with engine.begin() as connection:
        connection.execute(text("CREATE TABLE companies (id VARCHAR(36) PRIMARY KEY)"))
        connection.execute(text("CREATE TABLE users (id VARCHAR(36) PRIMARY KEY, company_id VARCHAR(36), password_hash VARCHAR(255))"))
        connection.execute(text("INSERT INTO users (id, company_id, password_hash) VALUES ('existing', 'company', 'unchanged')"))
        operations = Operations(MigrationContext.configure(connection))
        with operations.context(operations.get_context()):
            migration.upgrade()
        assert connection.execute(text("SELECT password_hash, auth_version FROM users")).one() == ("unchanged", 0)
        assert {"auth_sessions", "refresh_token_records", "password_reset_records"} <= set(inspect(connection).get_table_names())
        with pytest.raises(RuntimeError):
            migration.downgrade()
    engine.dispose()


def test_company_onboarding_migration_preserves_legacy_identity_without_owner_guess():
    spec = importlib.util.spec_from_file_location("company_migration", "alembic/versions/0005_company_onboarding.py")
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)
    engine = create_engine("sqlite://")
    with engine.begin() as connection:
        connection.execute(text("CREATE TABLE companies (id VARCHAR(36) PRIMARY KEY, name VARCHAR(200), created_at DATETIME)"))
        connection.execute(text("CREATE TABLE users (id VARCHAR(36) PRIMARY KEY, company_id VARCHAR(36), email VARCHAR(320))"))
        connection.execute(text("INSERT INTO companies (id, name, created_at) VALUES ('old-co', 'Legacy', CURRENT_TIMESTAMP)"))
        connection.execute(text("INSERT INTO users (id, company_id, email) VALUES ('old-user', 'old-co', 'Legacy@Example.test')"))
        operations = Operations(MigrationContext.configure(connection))
        with operations.context(operations.get_context()):
            migration.upgrade()
        assert connection.execute(text("SELECT owner_user_id, onboarding_status FROM companies WHERE id='old-co'")).one() == (None, "complete")
        assert connection.execute(text("SELECT email, email_verified FROM users WHERE id='old-user'")).one() == ("Legacy@Example.test", 1)
        assert connection.execute(text("SELECT email FROM email_claims")).scalar_one() == "legacy@example.test"
    engine.dispose()


@pytest.mark.parametrize("kind", ["access_token", "refresh_token"])
def test_expired_token_is_rejected(isolated, kind):
    client, _, _ = isolated
    pair = login(client)
    claims = decode_token(pair[kind])
    claims["iat"] = int((datetime.now(timezone.utc) - timedelta(minutes=5)).timestamp())
    claims["exp"] = int((datetime.now(timezone.utc) - timedelta(minutes=1)).timestamp())
    pair[kind] = jwt.encode(claims, settings.jwt_secret, algorithm=settings.jwt_algorithm)
    response = me(client, pair) if kind == "access_token" else refresh(client, pair)
    assert response.status_code == 401


def test_reset_type_digest_expiry_and_tenant_binding(isolated, monkeypatch):
    client, sessions, ids = isolated
    token = reset_token(client, monkeypatch)
    assert me(client, {"access_token": token}).status_code == 401
    assert refresh(client, {"refresh_token": token}).status_code == 401
    claims = decode_token(token)
    for key in ("exp", "sub", "company_id", "type", "jti", "ver", "purpose"):
        missing = dict(claims)
        missing.pop(key)
        altered = jwt.encode(missing, settings.jwt_secret, algorithm=settings.jwt_algorithm)
        assert reset(client, altered).status_code == 400
    mismatch = dict(claims, company_id=ids["other_company"])
    assert reset(client, jwt.encode(mismatch, settings.jwt_secret, algorithm=settings.jwt_algorithm)).status_code == 400
    with sessions() as db:
        record = db.get(PasswordResetRecord, claims["jti"])
        record.token_digest = "0" * 64
        db.commit()
    assert reset(client, token).status_code == 400
    with sessions() as db:
        record = db.get(PasswordResetRecord, claims["jti"])
        record.token_digest = auth_sessions.digest(token)
        record.expires_at = datetime.now(timezone.utc) - timedelta(seconds=1)
        db.commit()
    assert reset(client, token).status_code == 400


def test_failed_reset_rolls_back_password_consumption_and_revocation(isolated, monkeypatch):
    client, sessions, ids = isolated
    pair, token = login(client), reset_token(client, monkeypatch)
    original = auth_sessions.event
    def fail_reset(db, user, action, *args, **kwargs):
        if action == "auth.reset_password":
            raise SQLAlchemyError("simulated audit failure")
        return original(db, user, action, *args, **kwargs)
    monkeypatch.setattr(auth_sessions, "event", fail_reset)
    assert reset(client, token).status_code == 503
    assert me(client, pair).status_code == 200
    with sessions() as db:
        assert db.get(User, ids["user"]).auth_version == 0
        assert db.get(PasswordResetRecord, decode_token(token)["jti"]).consumed_at is None
    monkeypatch.setattr(auth_sessions, "event", original)
    assert reset(client, token).status_code == 200


def test_parallel_refresh_logout_does_not_restore_session(isolated):
    client, _, _ = isolated
    pair = login(client)
    responses = parallel(lambda: refresh(client, pair), lambda: client.post("/api/v1/auth/logout", headers=bearer(pair)))
    assert responses[1].status_code == 204 and responses[0].status_code in (200, 401)
    assert me(client, pair).status_code == 401
    if responses[0].status_code == 200:
        assert me(client, responses[0].json()).status_code == refresh(client, responses[0].json()).status_code == 401


def test_full_alembic_chain_on_disposable_sqlite(isolated, tmp_path, monkeypatch):
    filename = tmp_path / "migration.sqlite3"
    monkeypatch.setattr(settings, "database_url", "sqlite:///" + filename.as_posix())
    config = Config("alembic.ini")
    command.upgrade(config, "head")
    engine = create_engine(settings.database_url)
    with engine.connect() as connection:
        assert connection.execute(text("SELECT version_num FROM alembic_version")).scalar_one() == "0005_company_onboarding"
        assert {"auth_sessions", "refresh_token_records", "password_reset_records",
                "email_claims", "email_verifications", "company_invitations"} <= set(inspect(connection).get_table_names())
        assert "auth_version" in {column["name"] for column in inspect(connection).get_columns("users")}
        assert "email_verified" in {column["name"] for column in inspect(connection).get_columns("users")}
        assert "owner_user_id" in {column["name"] for column in inspect(connection).get_columns("companies")}
    engine.dispose()


def test_webhook_uses_signed_event_and_active_tenant(isolated, monkeypatch):
    client, sessions, ids = isolated
    with sessions() as db:
        integration, secret = create_integration(db, company_id=ids["company"], name="Contract events",
                                                 type="webhook_generic", event_map={"contract.updated": "contract.changed"})
        db.commit()
        integration_id = integration.id
    observed = []
    def capture_event(db, **kwargs):
        observed.append(kwargs)
        return []
    monkeypatch.setattr("app.services.integrations.fire_event", capture_event)
    raw = json.dumps({"event": "contract.updated", "integration_id": "forged", "integration_type": "forged",
                      "external_event": "forged", "event_type": "forged"}).encode()
    signature = hmac.new(secret.encode(), raw, hashlib.sha256).hexdigest()
    path = f"/api/v1/companies/{ids['company']}/integrations/{integration_id}/webhook"
    headers = {"X-Signature": "sha256=" + signature, "Content-Type": "application/json"}
    assert client.post(path + "?event_name=forged", content=raw, headers=headers).status_code == 400
    assert not observed
    assert client.post(path, content=raw, headers=headers).status_code == 200
    assert observed[0]["event_type"] == "contract.changed"
    assert observed[0]["payload"]["integration_id"] == integration_id
    assert observed[0]["payload"]["integration_type"] == "webhook_generic"
    assert observed[0]["payload"]["external_event"] == "contract.updated"
    assert observed[0]["payload"]["event_type"] == "contract.changed"
    with sessions() as db:
        db.get(Company, ids["company"]).is_active = False
        db.commit()
    assert client.post(path, content=raw, headers=headers).status_code == 404
    assert len(observed) == 1


def test_webhook_rejection_audit_is_committed_and_custom_secret_denied(isolated):
    client, sessions, ids = isolated
    pair = login(client)
    path = f"/api/v1/companies/{ids['company']}/integrations"
    reject = client.post(path, headers=bearer(pair), json={"name": "Weak", "type": "webhook_generic",
                                                          "webhook_secret": "weak"})
    assert reject.status_code == 400
    with sessions() as db:
        assert db.scalar(select(Integration.id).where(Integration.name == "Weak")) is None
        integration, _ = create_integration(db, company_id=ids["company"], name="Secure",
                                            type="webhook_generic")
        db.commit()
        integration_id = integration.id
    webhook = f"{path}/{integration_id}/webhook"
    assert client.post(webhook, content=b'{}', headers={"X-Signature": "sha256=bad"}).status_code == 401
    with sessions() as db:
        assert db.scalar(select(AuditLog.id).where(AuditLog.action == "integration.webhook.rejected",
                                                    AuditLog.company_id == ids["company"])) is not None


def test_tool_catalog_requires_session_and_uses_injected_db(isolated):
    client, _, ids = isolated
    assert client.get("/api/v1/tools", headers={"X-User-ID": ids["user"]}).status_code == 401
    pair = login(client)
    response = client.get("/api/v1/tools", headers=bearer(pair))
    assert response.status_code == 200 and isinstance(response.json(), list)


def test_company_resource_ids_cannot_cross_tenant(isolated):
    client, _, ids = isolated
    pair = login(client)
    other = ids["other_company"]
    for path in (f"/api/v1/companies/{other}/users", f"/api/v1/companies/{other}/inventory",
                 f"/api/v1/companies/{other}/integrations"):
        assert client.get(path, headers=bearer(pair)).status_code == 403


def test_automation_event_metadata_cannot_be_overridden(monkeypatch):
    observed = []
    rule = SimpleNamespace(id="rule")
    db = SimpleNamespace(scalars=lambda _: SimpleNamespace(all=lambda: [rule]))
    monkeypatch.setattr(automation, "create_and_execute_run", lambda db, **kwargs: observed.append(kwargs) or SimpleNamespace(id="run"))
    automation.fire_event(db, company_id="company", event_type="contract.changed",
                          payload={"trigger": "forged", "event_type": "forged", "subject": "contract"})
    assert observed[0]["payload"] == {"trigger": "event", "event_type": "contract.changed", "subject": "contract"}
