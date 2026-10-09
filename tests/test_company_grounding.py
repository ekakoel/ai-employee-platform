import json
from unittest.mock import Mock

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.agents.context import load_agent_context
from app.core.database import Base, get_db
from app.llm.base import LLMResponse
from app.main import app
from app.models.entities import (
    AgentInstance, AgentSkill, AgentSubscription, Approval, AuditLog,
    Company, Conversation, KnowledgeChunk, KnowledgeItem, Policy, Skill, Task, User,
)
from app.runtime.tool_executor import ApprovalRequiredError, ToolExecutionError, ToolExecutor
from app.security.policy_engine import PolicyEngine, conditions_match
from app.knowledge.retrieval import search_knowledge_chunks
from app.services.conversation import _agent_reply_text
from app.services.grounding import GroundingError, MISSING_INFORMATION, required_action_tool, validated_answer
from app.services.seed import get_or_create_role
from app.services.task_runtime import TaskRuntimeService
from app.tools.base import ToolContext
from app.tools.connectors import MockExternalSystemClient, get_external_client, set_external_client
from app.tools.domain import GetReservationTool, ReadDocumentTool, SearchAvailabilityTool


@pytest.fixture
def workspace():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    sessions = sessionmaker(bind=engine)
    previous_connector = get_external_client()
    set_external_client(MockExternalSystemClient())
    with sessions() as db:
        role = get_or_create_role(db, "owner")
        member = get_or_create_role(db, "member")
        db.add_all([Company(id="one", name="One"), Company(id="two", name="Two")])
        db.flush()
        db.add(AgentSubscription(id="sub", company_id="one", catalog_agent_id="catalog"))
        db.flush()
        tools = ["draft_quotation", "read_document", "search_availability", "get_reservation"]
        db.add_all([
            User(id="owner", company_id="one", name="Owner", email="owner@test", role_id=role.id),
            User(id="member", company_id="one", name="Member", email="member@test", role_id=member.id),
            AgentInstance(id="agent", company_id="one", name="Reservation", catalog_agent_id="catalog", subscription_id="sub",
                          scope=["quotation", "reservation", "pricing", "availability"], skills=["quotation_preparation"],
                          allowed_tools=tools, configuration={"allowed_tools": tools}, policies={name: "auto" for name in tools}),
            AgentInstance(id="other", company_id="one", name="Other", catalog_agent_id="catalog", subscription_id="sub"),
            Skill(id="skill", company_id="one", slug="quotation_preparation", name="Quotation preparation",
                  instructions="Use company pricing only.", workflow=["load pricing", "draft quotation"], allowed_tools=tools),
            KnowledgeItem(id="prices", company_id="one", category="pricing", title="Bali tour pricing",
                          content=json.dumps({"prices": [{"sku": "bali", "description": "3-day Bali tour", "amount": "300.00", "currency": "USD"}]})),
            KnowledgeItem(id="private", company_id="one", agent_instance_id="other", title="Private pricing", content="PRIVATE"),
            KnowledgeItem(id="foreign", company_id="two", title="Foreign pricing", content="FOREIGN"),
        ])
        db.flush()
        db.add_all([
            AgentSkill(company_id="one", agent_instance_id="agent", skill_id="skill"),
            Task(id="task", company_id="one", agent_instance_id="agent", title="Bali quotation", instruction="Create quotation for Ada: 3-day Bali tour for 2 guests."),
            Conversation(id="chat", company_id="one", agent_instance_id="agent", user_id="owner", title="Bali"),
        ])
        db.commit()

    def override():
        with sessions() as db:
            yield db

    previous = app.dependency_overrides.get(get_db)
    app.dependency_overrides[get_db] = override
    try:
        yield sessions, TestClient(app)
    finally:
        if previous is None:
            app.dependency_overrides.pop(get_db, None)
        else:
            app.dependency_overrides[get_db] = previous
        set_external_client(previous_connector)
        engine.dispose()


def quotation_arguments():
    return {"customer": "Ada", "items": [{"price_id": "prices:bali", "quantity": 2}], "currency": "USD"}


def tool_response(name="draft_quotation", arguments=None):
    return LLMResponse(content="", model="fake", raw={"message": {"content": "", "tool_calls": [
        {"function": {"name": name, "arguments": arguments or quotation_arguments()}}
    ]}})


def test_context_sources_skills_and_no_implicit_tool_grants(workspace):
    sessions, _ = workspace
    with sessions() as db:
        agent = db.get(AgentInstance, "agent")
        context = load_agent_context(db, agent, db.get(Task, "task"))
        assert {row["id"] for row in context.knowledge} == {"prices"}
        assert context.assigned_skills[0]["instructions"] == "Use company pricing only."
        assert context.assigned_skills[0]["workflow"] == ["load pricing", "draft quotation"]
        agent.allowed_tools = []
        agent.configuration = {"allowed_tools": []}
        assert load_agent_context(db, agent, db.get(Task, "task")).allowed_tools == []


def test_chat_validates_authorized_sources_and_rejects_hallucinations(workspace, monkeypatch):
    sessions, _ = workspace
    provider = Mock()
    monkeypatch.setattr("app.runtime.factory.create_llm_provider", lambda: provider)
    with sessions() as db:
        provider.chat.return_value = LLMResponse(content='{"citations":[{"source_id":"knowledge:prices","quote":"3-day Bali tour"}]}', model="fake")
        reply = _agent_reply_text(db, db.get(Conversation, "chat"), "What is the Bali tour pricing?")
        assert "3-day Bali tour" in reply and "knowledge:prices" in reply
        system = provider.chat.call_args.args[0][0].content
        assert "load pricing" in system and "Use company pricing only" in system
        assert "PRIVATE" not in system and "FOREIGN" not in system
        provider.chat.return_value = LLMResponse(content="The Bali price is USD 9999", model="fake")
        assert _agent_reply_text(db, db.get(Conversation, "chat"), "Bali pricing?") == MISSING_INFORMATION


def test_missing_sources_scope_and_inactive_agent_are_safe(workspace, monkeypatch):
    sessions, _ = workspace
    provider = Mock()
    monkeypatch.setattr("app.runtime.factory.create_llm_provider", lambda: provider)
    with sessions() as db:
        conv = db.get(Conversation, "chat")
        db.get(KnowledgeItem, "prices").is_active = False
        db.flush()
        assert _agent_reply_text(db, conv, "Bali quotation?") == MISSING_INFORMATION
        assert "outside" in _agent_reply_text(db, conv, "Calculate payroll tax")
        provider.chat.assert_not_called()
        db.get(AgentInstance, "agent").status = "inactive"
        with pytest.raises(ValueError, match="not active"):
            _agent_reply_text(db, conv, "Hello")


def test_quote_llm_persists_real_output_and_rejects_reexecution(workspace):
    sessions, client = workspace
    provider = Mock()
    provider.chat.side_effect = [tool_response(), LLMResponse(content="Invented total 9999", model="fake")]
    with sessions() as db:
        task = TaskRuntimeService(provider=provider).execute_with_llm(db, company_id="one", task_id="task")
        assert task.status == "completed"
        output = json.loads(task.result)
        quote = output["tool_results"][0]["result"]
        assert quote["total"] == 600 and "Total: 600.00 USD" in quote["draft"]
        assert quote["source_references"][0]["source_id"] == "knowledge:prices"
        assert "9999" not in task.result
        assert db.scalar(select(AuditLog).where(AuditLog.action == "tool.execute")).details["result"]["draft"] == quote["draft"]
        with pytest.raises(ValueError, match="cannot be executed"):
            TaskRuntimeService(provider=provider).execute_with_llm(db, company_id="one", task_id="task")
    saved = client.get("/api/v1/companies/one/tasks", headers={"X-User-ID": "owner"})
    assert saved.status_code == 200
    assert json.loads(saved.json()[0]["result"])["tool_results"][0]["result"]["total"] == 600


@pytest.mark.parametrize("failure", [RuntimeError("provider offline"), tool_response(arguments={"customer": "Ada", "items": [{"price_id": "foreign:bali", "amount": 1}]}), LLMResponse(content="Quotation created", model="fake")])
def test_llm_failure_never_completes_task(workspace, failure):
    sessions, _ = workspace
    provider = Mock()
    if isinstance(failure, Exception):
        provider.chat.side_effect = failure
    else:
        provider.chat.return_value = failure
    with sessions() as db:
        task = TaskRuntimeService(provider=provider).execute_with_llm(db, company_id="one", task_id="task")
        assert task.status == "failed" and task.result


def test_approval_exact_payload_pending_rejected_and_replay(workspace):
    sessions, _ = workspace
    provider = Mock()
    provider.chat.return_value = tool_response()
    with sessions() as db:
        agent = db.get(AgentInstance, "agent")
        agent.policies = {"draft_quotation": "approval"}
        db.commit()
        runtime = TaskRuntimeService(provider=provider)
        task = runtime.execute_with_llm(db, company_id="one", task_id="task")
        assert task.status == "waiting_approval"
        approval = db.scalar(select(Approval))
        assert approval.payload["items"] == quotation_arguments()["items"]
        executor = ToolExecutor(db)
        with pytest.raises(ToolExecutionError, match="approved state"):
            executor.execute_approved(company_id="one", task_id="task", approval_id=approval.id)
        approval.status = "rejected"
        db.commit()
        with pytest.raises(ToolExecutionError, match="approved state"):
            executor.execute_approved(company_id="one", task_id="task", approval_id=approval.id)
        approval.status = "approved"
        db.commit()
        completed = runtime.resume_after_approval(db, company_id="one", task_id="task", approval_id=approval.id)
        assert completed.status == "completed" and "600.00 USD" in completed.result
        assert provider.chat.call_count == 1
        with pytest.raises(ToolExecutionError):
            executor.execute_approved(company_id="one", task_id="task", approval_id=approval.id)


def test_policy_tool_task_and_employee_access_fail_closed(workspace):
    sessions, client = workspace
    with sessions() as db:
        assert PolicyEngine(db).evaluate(company_id="one", agent_instance_id="agent", tool_name="unknown").denied
        for company, tool, task in [("two", "draft_quotation", "task"), ("one", "unknown", "task"), ("one", "draft_quotation", "absent")]:
            with pytest.raises(ToolExecutionError):
                ToolExecutor(db).execute(company_id=company, agent_instance_id="agent", tool_name=tool, arguments=quotation_arguments(), task_id=task)
    headers = {"X-User-ID": "member"}
    for suffix in ("execute", "execute-llm"):
        response = client.post(f"/api/v1/companies/one/tasks/task/{suffix}", headers=headers)
        assert response.status_code == 403
    assert client.post("/api/v1/companies/one/agents/agent/tools/read_document/execute", headers=headers,
                       json={"arguments": {"knowledge_item_id": "prices"}}).status_code == 403
    assert client.get("/api/v1/companies/one/conversations/chat/messages", headers=headers).status_code == 403


def test_document_reservation_and_availability_tenant_isolation(workspace):
    sessions, _ = workspace
    context = ToolContext(company_id="one", agent_instance_id="agent", task_id="task")
    with sessions() as db:
        for source in ("foreign", "private"):
            assert ReadDocumentTool(db).execute(context, {"knowledge_item_id": source})["found"] is False
    record = get_external_client().create(system="reservations", payload={"company_id": "two", "guest_name": "Secret"})
    assert GetReservationTool().execute(context, {"reservation_id": record.record_id})["record"] is None
    result = SearchAvailabilityTool().execute(context, {"check_in": "2026-11-01", "check_out": "2026-11-03"})
    assert result["options"] == [] and result["count"] == 0


def test_citation_validation_rejects_fabricated_quote(workspace):
    sessions, _ = workspace
    with sessions() as db:
        context = load_agent_context(db, db.get(AgentInstance, "agent"), db.get(Task, "task"))
        with pytest.raises(GroundingError):
            validated_answer(context, '{"citations":[{"source_id":"knowledge:prices","quote":"The price is 9999"}]}')


def test_readonly_task_persists_validated_citations(workspace):
    sessions, _ = workspace
    provider = Mock()
    provider.chat.return_value = LLMResponse(content='{"citations":[{"source_id":"knowledge:prices","quote":"3-day Bali tour"}]}', model="fake")
    with sessions() as db:
        db.get(Task, "task").instruction = "What is the Bali pricing?"
        db.commit()
        task = TaskRuntimeService(provider=provider).execute_with_llm(db, company_id="one", task_id="task")
        assert task.status == "completed"
        assert json.loads(task.result)["citations"] == [{"source_id": "knowledge:prices", "quote": "3-day Bali tour"}]


def test_read_tool_does_not_satisfy_a_document_creation_request(workspace):
    sessions, _ = workspace
    provider = Mock()
    provider.chat.side_effect = [tool_response("read_document", {"knowledge_item_id": "prices"}), LLMResponse(content="Quotation created", model="fake")]
    with sessions() as db:
        task = TaskRuntimeService(provider=provider).execute_with_llm(db, company_id="one", task_id="task")
        assert task.status == "failed" and "not completed" in task.result


def test_derived_quotation_amount_controls_approval_not_model_amount(workspace):
    sessions, _ = workspace
    with sessions() as db:
        db.add(Policy(company_id="one", name="Large quote", configuration={
            "tool": "draft_quotation", "effect": "require_approval", "conditions": {"amount_gt": 500},
        }))
        db.commit()
        executor = ToolExecutor(db)
        forged = {**quotation_arguments(), "amount": 1}
        with pytest.raises(ToolExecutionError, match="Policy amount"):
            executor.execute(company_id="one", agent_instance_id="agent", task_id="task", tool_name="draft_quotation", arguments=forged)
        with pytest.raises(ApprovalRequiredError):
            executor.execute(company_id="one", agent_instance_id="agent", task_id="task", tool_name="draft_quotation", arguments=quotation_arguments())
        approval = db.scalar(select(Approval))
        assert approval.payload["amount"] == "600.00"
        assert db.get(Task, "task").status == "pending"
        with pytest.raises(ToolExecutionError, match="waiting for approval"):
            executor.execute(company_id="one", agent_instance_id="agent", task_id="task", tool_name="draft_quotation", arguments=quotation_arguments())
        assert conditions_match({"unknown_security_condition": True}, {})[0] is False


def test_inactive_parent_chunks_and_waiting_approval_cannot_bypass_checks(workspace):
    sessions, _ = workspace
    with sessions() as db:
        db.add(KnowledgeChunk(company_id="one", knowledge_item_id="private", content="Private Bali pricing", agent_instance_id=None))
        db.add(KnowledgeChunk(company_id="one", knowledge_item_id="prices", content="Bali pricing"))
        db.get(KnowledgeItem, "prices").is_active = False
        db.get(Task, "task").status = "waiting_approval"
        db.commit()
        assert search_knowledge_chunks(db, company_id="one", agent_instance_id="agent", query="Bali pricing") == []
        with pytest.raises(ToolExecutionError, match="waiting for approval"):
            ToolExecutor(db).execute(company_id="one", agent_instance_id="agent", task_id="task", tool_name="read_document", arguments={"knowledge_item_id": "prices"})


@pytest.mark.parametrize("instruction", ["Prepare a quotation for Ada", "Buat quotation untuk Ada"])
def test_preparation_request_requires_a_real_document_tool(instruction):
    assert required_action_tool(instruction) == "draft_quotation"


def test_empty_deterministic_output_cannot_complete_task(workspace):
    sessions, _ = workspace
    executor = Mock()
    executor.execute.return_value = ""
    with sessions() as db:
        task = TaskRuntimeService(executor=executor, provider=Mock()).execute(db, company_id="one", task_id="task")
        assert task.status == "failed" and "did not produce" in task.result


def test_unmatched_company_conditions_cannot_fall_back_to_snapshot_allow(workspace):
    sessions, _ = workspace
    with sessions() as db:
        db.add(Policy(company_id="one", name="Restricted quote", configuration={
            "tool": "draft_quotation", "effect": "allow", "conditions": {"department": "sales"},
        }))
        db.commit()
        with pytest.raises(ToolExecutionError, match="denied by policy"):
            ToolExecutor(db).execute(company_id="one", agent_instance_id="agent", task_id="task", tool_name="draft_quotation",
                                     arguments={**quotation_arguments(), "department": "sales", "risk": "low"})


def test_workflow_autoconsult_uses_shared_grounding_and_employee_access(workspace):
    sessions, client = workspace
    path = "/api/v1/companies/one/workflows"
    headers = {"X-User-ID": "owner"}
    response = client.post(path, headers=headers, json={"name": "Pricing consult", "steps": [
        {"type": "create_task", "agent_instance_id": "agent", "instruction": "Review Bali pricing", "mode": "consult"},
        {"type": "complete"},
    ]})
    assert response.status_code == 201, response.text
    run_path = f"{path}/{response.json()['id']}/runs"
    run = client.post(run_path, headers=headers, json={"context": {}})
    assert run.status_code == 201 and run.json()["status"] == "completed", run.text
    task_id = run.json()["step_results"][0]["task_id"]
    with sessions() as db:
        task = db.get(Task, task_id)
        assert task.status == "completed" and "knowledge:prices" in task.result
    denied = client.post(run_path, headers={"X-User-ID": "member"}, json={"context": {}})
    assert denied.status_code == 201 and denied.json()["status"] == "failed", denied.text


def test_workflow_child_failure_cannot_report_completed(workspace, monkeypatch):
    _, client = workspace

    def broken(*args, **kwargs):
        raise RuntimeError("Consultation unavailable")

    monkeypatch.setattr("app.services.workflow.run_consultation", broken)
    headers = {"X-User-ID": "owner"}
    path = "/api/v1/companies/one/workflows"
    created = client.post(path, headers=headers, json={"name": "Failure", "steps": [
        {"type": "create_task", "agent_instance_id": "agent", "instruction": "Review Bali pricing", "mode": "consult"},
        {"type": "complete"},
    ]})
    run = client.post(f"{path}/{created.json()['id']}/runs", headers=headers, json={})
    assert run.status_code == 201 and run.json()["status"] == "failed"
    assert run.json()["step_results"][0]["fail"] is True


def test_delegation_metadata_cannot_fake_instruction_scope(workspace):
    sessions, client = workspace
    headers = {"X-User-ID": "owner"}
    path = "/api/v1/companies/one/delegation-requests"
    created = client.post(path, headers=headers, json={
        "source_agent_instance_id": "other", "target_agent_instance_id": "agent",
        "capability": "quotation_preparation", "title": "Payroll", "instruction": "Calculate payroll tax",
    })
    assert created.status_code == 201, created.text
    response = client.post(f"{path}/{created.json()['id']}/execute", headers=headers, json={"mode": "consult"})
    assert response.status_code == 409, response.text
    with sessions() as db:
        child = db.scalar(select(Task).where(Task.title == "[Delegated] Payroll"))
        assert child.instruction == "Calculate payroll tax" and child.status == "cancelled"
