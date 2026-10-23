#!/usr/bin/env python3
"""
Job 87 FIX2 — repair test_chat_workspace.py syntax + AuthSession rows.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path.cwd()
PATH = ROOT / "tests" / "test_chat_workspace.py"

# Clean header + fixture seed (rest of file kept after chat_fixture def body start marker)
HEAD = r'''from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.database import Base, get_db
from app.core.security import create_access_token
from app.llm.base import LLMResponse
from app.main import app
from app.models.entities import (
    AgentInstance,
    AgentSubscription,
    AuditLog,
    AuthSession,
    Company,
    Conversation,
    KnowledgeItem,
    Message,
    Task,
    User,
)
from app.services.conversation import clean_chat_content, list_messages
from app.services.seed import get_or_create_role


def _bearer(user_id: str, company_id: str) -> dict:
    tok = create_access_token(
        subject=user_id,
        company_id=company_id,
        session_id=f"chat-{user_id}",
        auth_version=1,
    )
    return {"Authorization": f"Bearer {tok}", "X-User-ID": user_id}


@pytest.fixture
def chat_fixture(monkeypatch):
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    sessions = sessionmaker(bind=engine)
    with sessions() as db:
        role = get_or_create_role(db, "owner")
        db.add_all([Company(id="one", name="One"), Company(id="two", name="Two")])
        db.flush()
        db.add(AgentSubscription(id="subscription", company_id="one", catalog_agent_id="catalog"))
        db.flush()
        db.add_all([
            User(id="alice", company_id="one", name="Alice", email="alice@test.local", role_id=role.id),
            User(id="bob", company_id="one", name="Bob", email="bob@test.local", role_id=role.id),
            User(id="eve", company_id="two", name="Eve", email="eve@test.local", role_id=role.id),
            AgentInstance(
                id="agent",
                company_id="one",
                name="Analyst",
                catalog_agent_id="catalog",
                subscription_id="subscription",
                scope=["reports", "budget"],
            ),
            KnowledgeItem(
                id="budget",
                company_id="one",
                title="Budget",
                content="The company budget is 500.",
                category="report",
            ),
        ])
        db.flush()
        exp = datetime.now(timezone.utc) + timedelta(hours=12)
        db.add_all([
            AuthSession(id="chat-alice", user_id="alice", company_id="one", auth_version=1, absolute_expires_at=exp),
            AuthSession(id="chat-bob", user_id="bob", company_id="one", auth_version=1, absolute_expires_at=exp),
            AuthSession(id="chat-eve", user_id="eve", company_id="two", auth_version=1, absolute_expires_at=exp),
        ])
        db.commit()
    calls = []

    class Provider:
        def chat(self, messages, **kwargs):
            calls.append((messages, kwargs))
            return LLMResponse(
                content='{"citations":[{"source_id":"knowledge:budget","quote":"The company budget is 500."}]}',
                model="test",
            )

    monkeypatch.setattr("app.runtime.factory.create_llm_provider", lambda: Provider())

    def override():
        with sessions() as db:
            yield db

    previous = app.dependency_overrides.get(get_db)
    app.dependency_overrides[get_db] = override
    try:
        client = TestClient(app)
        base = "/api/v1/companies/one/conversations"
        headers = _bearer("alice", "one")
        response = client.post(base, headers=headers, json={"agent_instance_id": "agent", "title": "Budget"})
        assert response.status_code == 201, response.text
        yield client, sessions, calls, base, headers, response.json()["id"]
    finally:
        if previous is None:
            app.dependency_overrides.pop(get_db, None)
        else:
            app.dependency_overrides[get_db] = previous
        engine.dispose()

'''


def main() -> int:
    print("Job 87 FIX2 — rewrite chat_workspace header/fixture")
    if not PATH.exists():
        raise SystemExit(f"missing {PATH}")
    text = PATH.read_text(encoding="utf-8")
    # Keep everything after first real test function
    m = re.search(r"\ndef test_", text)
    if not m:
        raise SystemExit("no test_ functions found")
    rest = text[m.start() + 1 :]  # from def test_...
    # Fix any bad header lines in rest
    rest = rest.replace(
        'headers=_bearer("eve", "two")',
        'headers=_bearer("eve", "two")',
    )
    rest = rest.replace(
        'headers={"X-User-ID": "eve"}',
        'headers=_bearer("eve", "two")',
    )
    rest = rest.replace(
        'headers={"X-User-ID": "bob"}',
        'headers=_bearer("bob", "one")',
    )
    PATH.write_text(HEAD + rest, encoding="utf-8")
    # syntax check
    compile(PATH.read_text(encoding="utf-8"), str(PATH), "exec")
    print(f"[OK] {PATH} syntax OK")
    print(
        """
  python -c "import ast; ast.parse(open('tests/test_chat_workspace.py',encoding='utf-8').read()); print('syntax OK')"
  pytest -q --tb=line tests/test_chat_workspace.py tests/test_agent_directory.py tests/test_scope_guard.py

  git add tests/test_chat_workspace.py
  git commit -m "Job 87 fix2: repair chat_workspace syntax + AuthSession seed"
  git push origin development
"""
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
