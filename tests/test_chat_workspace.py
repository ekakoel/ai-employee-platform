from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.database import Base, get_db
from app.llm.base import LLMResponse
from app.main import app
from app.models.entities import AgentInstance, AgentSubscription, AuditLog, Company, Conversation, KnowledgeItem, Message, Task, User
from app.services.conversation import clean_chat_content, list_messages
from app.services.seed import get_or_create_role


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
            User(id="eve", company_id="two", name="Eve", email="eve@test.local", role_id=role.id),
            AgentInstance(id="agent", company_id="one", name="Analyst", catalog_agent_id="catalog", subscription_id="subscription", scope=["reports", "budget"]),
            KnowledgeItem(id="budget", company_id="one", title="Budget", content="The company budget is 500.", category="report"),
        ])
        db.commit()
    calls = []

    class Provider:
        def chat(self, messages, **kwargs):
            calls.append((messages, kwargs))
            return LLMResponse(content='{"citations":[{"source_id":"knowledge:budget","quote":"The company budget is 500."}]}', model="test")

    monkeypatch.setattr("app.runtime.factory.create_llm_provider", lambda: Provider())

    def override():
        with sessions() as db:
            yield db

    previous = app.dependency_overrides.get(get_db)
    app.dependency_overrides[get_db] = override
    try:
        client = TestClient(app)
        base = "/api/v1/companies/one/conversations"
        headers = {"X-User-ID": "alice"}
        response = client.post(base, headers=headers, json={"agent_instance_id": "agent", "title": "Budget"})
        assert response.status_code == 201, response.text
        yield client, sessions, calls, base, headers, response.json()["id"]
    finally:
        if previous is None:
            app.dependency_overrides.pop(get_db, None)
        else:
            app.dependency_overrides[get_db] = previous
        engine.dispose()


def test_chat_api_followups_and_action_history(chat_fixture):
    client, sessions, calls, base, headers, conversation_id = chat_fixture
    path = f"{base}/{conversation_id}/messages"
    first = client.post(path, headers=headers, json={"content": "My budget is 500"})
    assert first.status_code == 200, first.text
    assert first.json()["human"]["sender_name"] == "Alice"
    assert first.json()["agent"]["sender_name"] == "Analyst"
    assert "Chat mode:" not in first.json()["agent"]["content"]
    assert first.json()["agent"]["work_result"] is None
    second = client.post(path, headers=headers, json={"content": "What was my budget?", "create_task": True, "task_mode": "execute"})
    assert second.status_code == 200, second.text
    context, kwargs = calls[-1]
    assert [(message.role, message.content) for message in context][1][1] == "My budget is 500"
    assert any(message.role == "assistant" for message in context)
    assert context[-1].content == "What was my budget?"
    assert sum(message.content == "What was my budget?" for message in context) == 1
    assert kwargs["tools"] is None
    with sessions() as db:
        task = db.get(Task, second.json()["task_id"])
        assert task.status == "pending" and task.mode == "execute"
        human_audit = db.scalar(select(AuditLog).where(AuditLog.resource_id == second.json()["human"]["id"]))
        agent_audit = db.scalar(select(AuditLog).where(AuditLog.resource_id == second.json()["agent"]["id"]))
        assert human_audit.user_id == "alice" and human_audit.created_at
        assert agent_audit.agent_instance_id == "agent" and agent_audit.user_id is None
    assert len(client.get(path, headers=headers).json()) == 5
    saved = client.get(base + "?agent_instance_id=agent", headers=headers).json()[0]
    assert saved["id"] == conversation_id and saved["user_name"] == "Alice"


def test_recent_transcript_window_preserves_order(chat_fixture):
    _, sessions, _, _, _, conversation_id = chat_fixture
    start = datetime.now(timezone.utc) + timedelta(days=1)
    with sessions() as db:
        for index in range(205):
            db.add(Message(id=f"m{index}", company_id="one", conversation_id=conversation_id, role="human", content=str(index), created_at=start + timedelta(seconds=index)))
        db.commit()
        rows = list_messages(db, company_id="one", conversation_id=conversation_id, limit=200)
        assert len(rows) == 200
        assert rows[-1].content == "204"
        assert rows[0].content == "5"


def test_chat_rejects_empty_closed_and_cross_tenant_requests(chat_fixture):
    client, sessions, _, base, headers, conversation_id = chat_fixture
    path = f"{base}/{conversation_id}/messages"
    assert client.get(path, headers={"X-User-ID": "eve"}).status_code == 403
    assert client.post(path, headers=headers, json={"content": " "}).status_code in (400, 422)
    with sessions() as db:
        db.get(Conversation, conversation_id).status = "closed"
        db.commit()
    assert client.post(path, headers=headers, json={"content": "Hello"}).status_code == 400


def test_llm_offline_fallback_and_failed_transaction(chat_fixture, monkeypatch):
    client, _, _, base, headers, conversation_id = chat_fixture
    path = f"{base}/{conversation_id}/messages"

    def offline():
        raise RuntimeError("LLM offline")

    monkeypatch.setattr("app.runtime.factory.create_llm_provider", offline)
    response = client.post(path, headers=headers, json={"content": "Review a report"})
    assert response.status_code == 200 and response.json()["agent"]["content"]
    before = len(client.get(path, headers=headers).json())

    def broken(*args):
        raise RuntimeError("Storage failure")

    monkeypatch.setattr("app.services.conversation._agent_reply_text", broken)
    assert client.post(path, headers=headers, json={"content": "Rejected"}).status_code == 502
    assert len(client.get(path, headers=headers).json()) == before


def test_saved_results_legacy_content_and_unknown_actor(chat_fixture):
    client, sessions, _, base, headers, conversation_id = chat_fixture
    path = f"{base}/{conversation_id}/messages"
    footer = '_(Chat mode: no tools executed. Use “Create task” to run with policy & tools.)_'
    with sessions() as db:
        db.add_all([
            Task(id="saved", company_id="one", agent_instance_id="agent", title="Revenue report", instruction="Work", status="completed", result="Saved revenue output"),
            Task(id="foreign", company_id="two", agent_instance_id="agent", title="Private result", instruction="Work", status="completed", result="Secret output"),
        ])
        db.flush()
        db.add_all([
            Message(id="legacy-human", company_id="one", conversation_id=conversation_id, role="human", content="Historic question"),
            Message(id="legacy-agent", company_id="one", conversation_id=conversation_id, role="agent", content=f"Report ready\n\n{footer}", task_id="saved"),
            Message(id="foreign-link", company_id="one", conversation_id=conversation_id, role="agent", content="Another reply", task_id="foreign"),
        ])
        db.commit()
    rows = {row["id"]: row for row in client.get(path, headers=headers).json()}
    assert rows["legacy-human"]["sender_name"] is None
    assert rows["legacy-human"]["sender_user_id"] is None
    assert rows["legacy-agent"]["content"] == "Report ready"
    assert rows["legacy-agent"]["work_result"]["result"] == "Saved revenue output"
    assert rows["foreign-link"]["work_result"] is None
    assert clean_chat_content("Report ready\n\n" + footer) == "Report ready"
    with sessions() as db:
        assert db.get(Message, "legacy-agent").content.endswith(footer)
        user = db.get(User, "alice")
        user.role.permissions = [permission for permission in user.role.permissions if permission.key != "task.read"]
        db.commit()
    limited = {row["id"]: row for row in client.get(path, headers=headers).json()}
    assert limited["legacy-agent"]["work_result"] is None


def test_sender_attribution_is_per_message_not_conversation_owner(chat_fixture):
    client, sessions, _, base, headers, conversation_id = chat_fixture
    with sessions() as db:
        owner = db.get(User, "alice")
        db.add(User(id="bob", company_id="one", name="Bob", email="bob@test.local", role_id=owner.role_id))
        db.commit()
    path = f"{base}/{conversation_id}/messages"
    response = client.post(path, headers={"X-User-ID": "bob"}, json={"content": "Bob's question"})
    assert response.status_code == 200, response.text
    assert response.json()["human"]["sender_name"] == "Bob"
    assert response.json()["human"]["sender_user_id"] == "bob"
    assert client.get(base, headers=headers).json()[0]["user_name"] == "Alice"


@pytest.mark.parametrize("wrapper", ["", "_", "*", "**"])
@pytest.mark.parametrize("quotes", [("\u201c", "\u201d"), ('"', '"')])
def test_footer_cleanup_handles_legacy_markdown_and_quotes(wrapper, quotes):
    footer = f'{wrapper}(Chat mode: no tools executed. Use {quotes[0]}Create task{quotes[1]} to run with policy & tools.){wrapper}'
    assert clean_chat_content("Quotation draft\n\n" + footer) == "Quotation draft"
    assert clean_chat_content("Quotation draft") == "Quotation draft"
