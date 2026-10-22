import pytest
from datetime import datetime, timedelta, timezone

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.database import Base, get_db
from app.core.security import create_access_token
from app.main import app
from app.models.entities import AuthSession, Company, Task, User
from app.services.seed import get_or_create_role, seed_catalog


def _bearer(user_id: str, company_id: str) -> dict:
    tok = create_access_token(
        subject=user_id,
        company_id=company_id,
        session_id=f"pin-{user_id}",
        auth_version=1,
    )
    return {"Authorization": f"Bearer {tok}", "X-User-ID": user_id}


@pytest.fixture
def result_client():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    sessions = sessionmaker(bind=engine)
    with sessions() as db:
        seed_catalog(db)
        role = get_or_create_role(db, "owner")
        db.add_all([Company(id="one", name="One"), Company(id="two", name="Two")])
        db.flush()
        db.add_all([
            User(id="alice", company_id="one", name="Alice", email="alice@test.local", role_id=role.id, auth_version=1),
            User(id="bob", company_id="one", name="Bob", email="bob@test.local", role_id=role.id, auth_version=1),
            User(id="eve", company_id="two", name="Eve", email="eve@test.local", role_id=role.id, auth_version=1),
            Task(id="result", company_id="one", agent_instance_id="agent", title="Report", instruction="Report", result="Persisted report"),
            Task(id="empty", company_id="one", agent_instance_id="agent", title="Empty", instruction="Empty"),
        ])
        db.flush()
        exp = datetime.now(timezone.utc) + timedelta(hours=12)
        db.add_all([
            AuthSession(id="pin-alice", user_id="alice", company_id="one", auth_version=1, absolute_expires_at=exp),
            AuthSession(id="pin-bob", user_id="bob", company_id="one", auth_version=1, absolute_expires_at=exp),
            AuthSession(id="pin-eve", user_id="eve", company_id="two", auth_version=1, absolute_expires_at=exp),
        ])
        db.commit()

    def override():
        with sessions() as db:
            yield db

    previous = app.dependency_overrides.get(get_db)
    app.dependency_overrides[get_db] = override
    try:
        yield TestClient(app)
    finally:
        if previous is None:
            app.dependency_overrides.pop(get_db, None)
        else:
            app.dependency_overrides[get_db] = previous
        engine.dispose()

def test_pins_persist_are_personal_and_idempotent(result_client):
    path = "/api/v1/companies/one/tasks/result/result-pin"
    alice = _bearer("alice", "one")
    for _ in range(2):
        assert result_client.put(path, headers=alice).status_code == 204
    assert result_client.get("/api/v1/companies/one/result-pins", headers=alice).json() == ["result"]
    assert result_client.get("/api/v1/companies/one/result-pins", headers=_bearer("bob", "one")).json() == []
    assert result_client.delete(path, headers=_bearer("bob", "one")).status_code == 204
    assert result_client.get("/api/v1/companies/one/result-pins", headers=alice).json() == ["result"]
    assert result_client.delete(path, headers=alice).status_code == 204
    assert result_client.get("/api/v1/companies/one/result-pins", headers=alice).json() == []


def test_pins_reject_cross_company_and_empty_results(result_client):
    alice = _bearer("alice", "one")
    assert result_client.put("/api/v1/companies/one/tasks/empty/result-pin", headers=alice).status_code == 409
    assert result_client.put("/api/v1/companies/one/tasks/missing/result-pin", headers=alice).status_code == 404
    assert result_client.put("/api/v1/companies/two/tasks/result/result-pin", headers=_bearer("eve", "two")).status_code == 404
    assert result_client.get("/api/v1/companies/one/result-pins", headers=_bearer("eve", "two")).status_code == 403
    assert result_client.get("/api/v1/companies/one/result-pins").status_code in (401, 403)


def test_pin_migration_is_idempotent_and_reversible():
    from pathlib import Path
    from runpy import run_path
    from alembic.migration import MigrationContext
    from alembic.operations import Operations
    from sqlalchemy import inspect

    migration = run_path(str(Path(__file__).resolve().parents[1] / "alembic/versions/0003_task_result_pins.py"))
    engine = create_engine("sqlite://")
    try:
        with engine.begin() as connection:
            with Operations.context(MigrationContext.configure(connection)):
                migration["upgrade"]()
                migration["upgrade"]()
                assert "task_result_pins" in inspect(connection).get_table_names()
                migration["downgrade"]()
                assert "task_result_pins" not in inspect(connection).get_table_names()
    finally:
        engine.dispose()
