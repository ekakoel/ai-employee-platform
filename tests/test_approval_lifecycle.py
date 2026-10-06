from unittest.mock import patch

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from app.core.database import Base, get_db
from app.main import app
from app.models.entities import (
    AgentCatalog,
    AgentInstance,
    AgentSubscription,
    Approval,
    ApprovalStatus,
    Company,
    KnowledgeItem,
    Policy,
    Role,
    SubscriptionStatus,
    Task,
    TaskStatus,
    User,
)
from app.services.seed import seed_catalog
from app.tools.contract import SearchContractTool


engine = create_engine(
    "sqlite:///./test_approval_lifecycle.db",
    connect_args={"check_same_thread": False},
)

TestingSessionLocal = sessionmaker(
    bind=engine,
    autoflush=False,
    autocommit=False,
)

Base.metadata.drop_all(bind=engine)
Base.metadata.create_all(bind=engine)

with TestingSessionLocal() as db:
    seed_catalog(db)


def override_get_db():
    db = TestingSessionLocal()

    try:
        yield db
    finally:
        db.close()


app.dependency_overrides[get_db] = override_get_db

client = TestClient(app)


def create_approval_case(
    *,
    company_name: str,
    user_email: str,
    agent_name: str,
    policy_name: str,
    knowledge_title: str | None = None,
    knowledge_content: str | None = None,
):
    """
    Create a complete company/agent/task environment for approval tests.
    """

    with TestingSessionLocal() as db:
        # ---------------------------------------------------------
        # COMPANY
        # ---------------------------------------------------------
        company = Company(
            name=company_name,
        )

        db.add(company)
        db.flush()

        # ---------------------------------------------------------
        # MANAGER ROLE
        # ---------------------------------------------------------
        role = db.scalar(
            select(Role).where(
                Role.name == "manager",
            )
        )

        assert role is not None

        # ---------------------------------------------------------
        # USER
        # ---------------------------------------------------------
        user = User(
            company_id=company.id,
            email=user_email,
            name=f"{company_name} Manager",
            role_id=role.id,
            status="active",
        )

        db.add(user)
        db.flush()

        # ---------------------------------------------------------
        # AGENT CATALOG
        # ---------------------------------------------------------
        catalog = db.scalar(
            select(AgentCatalog).limit(1)
        )

        assert catalog is not None

        # ---------------------------------------------------------
        # SUBSCRIPTION
        # ---------------------------------------------------------
        subscription = AgentSubscription(
            company_id=company.id,
            catalog_agent_id=catalog.id,
            status=SubscriptionStatus.ACTIVE.value,
        )

        db.add(subscription)
        db.flush()

        # ---------------------------------------------------------
        # AGENT INSTANCE
        # ---------------------------------------------------------
        agent = AgentInstance(
            company_id=company.id,
            catalog_agent_id=catalog.id,
            subscription_id=subscription.id,
            name=agent_name,
            status="active",
            configuration={
                "allowed_tools": [
                    "search_contract",
                ],
            },
        )

        db.add(agent)
        db.flush()

        # ---------------------------------------------------------
        # KNOWLEDGE
        # ---------------------------------------------------------
        if knowledge_title is not None and knowledge_content is not None:
            knowledge = KnowledgeItem(
                company_id=company.id,
                agent_instance_id=agent.id,
                title=knowledge_title,
                content=knowledge_content,
                category="contract",
                is_active=True,
            )

            db.add(knowledge)
            db.flush()

        # ---------------------------------------------------------
        # APPROVAL POLICY
        # ---------------------------------------------------------
        policy = Policy(
            company_id=company.id,
            name=policy_name,
            description="Contract searches require human approval.",
            configuration={
                "tool": "search_contract",
                "effect": "require_approval",
            },
            is_active=True,
        )

        db.add(policy)
        db.flush()

        # ---------------------------------------------------------
        # TASK
        # ---------------------------------------------------------
        task = Task(
            company_id=company.id,
            agent_instance_id=agent.id,
            title="Search contract",
            instruction="Search contract",
            status=TaskStatus.PENDING.value,
        )

        db.add(task)
        db.commit()

        return {
            "company_id": company.id,
            "user_id": user.id,
            "agent_id": agent.id,
            "task_id": task.id,
        }


def get_approval(
    *,
    company_id: str,
    task_id: str,
) -> Approval | None:
    with TestingSessionLocal() as db:
        return (
            db.query(Approval)
            .filter(
                Approval.company_id == company_id,
                Approval.task_id == task_id,
            )
            .first()
        )


def get_task(
    *,
    company_id: str,
    task_id: str,
) -> Task | None:
    with TestingSessionLocal() as db:
        return db.scalar(
            select(Task).where(
                Task.id == task_id,
                Task.company_id == company_id,
            )
        )


def test_tool_requires_approval_and_task_waits():
    case = create_approval_case(
        company_name="Approval Test Company",
        user_email="approval-manager@test.local",
        agent_name="Contract AI",
        policy_name="Contract Search Approval",
    )

    # -------------------------------------------------------------
    # EXECUTE TASK
    # -------------------------------------------------------------
    response = client.post(
        f"/api/v1/companies/{case['company_id']}/tasks/"
        f"{case['task_id']}/execute",
        headers={
            "X-User-ID": case["user_id"],
        },
    )

    assert response.status_code == 200

    data = response.json()

    # -------------------------------------------------------------
    # TASK MUST WAIT FOR APPROVAL
    # -------------------------------------------------------------
    assert data["status"] == TaskStatus.WAITING_APPROVAL.value

    # -------------------------------------------------------------
    # APPROVAL MUST EXIST AND BE PENDING
    # -------------------------------------------------------------
    approval = get_approval(
        company_id=case["company_id"],
        task_id=case["task_id"],
    )

    assert approval is not None
    assert approval.status == ApprovalStatus.PENDING.value
    assert approval.action == "search_contract"
    assert approval.agent_instance_id == case["agent_id"]


def test_approval_approve_resumes_task_executes_tool_and_completes():
    case = create_approval_case(
        company_name="Approve Execution Company",
        user_email="approve-manager@test.local",
        agent_name="Contract AI Approve",
        policy_name="Contract Search Approval Approve",
        knowledge_title="Supplier Contract",
        knowledge_content="This is the supplier contract for Bali Kami.",
    )

    # -------------------------------------------------------------
    # STEP 1: EXECUTE TASK
    # -------------------------------------------------------------
    response = client.post(
        f"/api/v1/companies/{case['company_id']}/tasks/"
        f"{case['task_id']}/execute",
        headers={
            "X-User-ID": case["user_id"],
        },
    )

    assert response.status_code == 200
    assert response.json()["status"] == TaskStatus.WAITING_APPROVAL.value

    approval = get_approval(
        company_id=case["company_id"],
        task_id=case["task_id"],
    )

    assert approval is not None
    assert approval.status == ApprovalStatus.PENDING.value

    approval_id = approval.id

    # -------------------------------------------------------------
    # STEP 2: APPROVE
    # -------------------------------------------------------------
    response = client.post(
        f"/api/v1/companies/{case['company_id']}/approvals/"
        f"{approval_id}/approve",
        headers={
            "X-User-ID": case["user_id"],
        },
        json={
            "comment": "Approved for execution.",
        },
    )

    assert response.status_code == 200

    # -------------------------------------------------------------
    # APPROVAL MUST BE APPROVED
    # -------------------------------------------------------------
    approval = get_approval(
        company_id=case["company_id"],
        task_id=case["task_id"],
    )

    assert approval is not None
    assert approval.status == ApprovalStatus.APPROVED.value
    assert approval.reviewed_by == case["user_id"]
    assert approval.review_comment == "Approved for execution."
    assert approval.reviewed_at is not None

    # -------------------------------------------------------------
    # TASK MUST BE COMPLETED
    # -------------------------------------------------------------
    task = get_task(
        company_id=case["company_id"],
        task_id=case["task_id"],
    )

    assert task is not None
    assert task.status == TaskStatus.COMPLETED.value

    # -------------------------------------------------------------
    # TOOL RESULT MUST EXIST
    # -------------------------------------------------------------
    assert task.result is not None
    assert "Approved tool execution:" in task.result
    assert "search_contract" in task.result
    assert "Result count: 1" in task.result
    assert "Supplier Contract" in task.result


def test_rejected_approval_stops_task_without_executing_tool():
    case = create_approval_case(
        company_name="Reject Execution Company",
        user_email="reject-manager@test.local",
        agent_name="Contract AI Reject",
        policy_name="Contract Search Approval Reject",
        knowledge_title="Rejected Contract",
        knowledge_content="This contract must never be returned after rejection.",
    )

    # -------------------------------------------------------------
    # STEP 1: EXECUTE TASK
    # -------------------------------------------------------------
    response = client.post(
        f"/api/v1/companies/{case['company_id']}/tasks/"
        f"{case['task_id']}/execute",
        headers={
            "X-User-ID": case["user_id"],
        },
    )

    assert response.status_code == 200
    assert response.json()["status"] == TaskStatus.WAITING_APPROVAL.value

    approval = get_approval(
        company_id=case["company_id"],
        task_id=case["task_id"],
    )

    assert approval is not None
    assert approval.status == ApprovalStatus.PENDING.value

    approval_id = approval.id

    # -------------------------------------------------------------
    # STEP 2: REJECT
    #
    # SearchContractTool.execute must NEVER be called during
    # rejection because the tool must only execute after approval.
    # -------------------------------------------------------------
    with patch.object(
        SearchContractTool,
        "execute",
        side_effect=AssertionError(
            "Tool executed even though approval was rejected."
        ),
    ):
        response = client.post(
            f"/api/v1/companies/{case['company_id']}/approvals/"
            f"{approval_id}/reject",
            headers={
                "X-User-ID": case["user_id"],
            },
            json={
                "comment": "Rejected by manager.",
            },
        )

    assert response.status_code == 200

    # -------------------------------------------------------------
    # APPROVAL MUST BE REJECTED
    # -------------------------------------------------------------
    approval = get_approval(
        company_id=case["company_id"],
        task_id=case["task_id"],
    )

    assert approval is not None
    assert approval.status == ApprovalStatus.REJECTED.value
    assert approval.reviewed_by == case["user_id"]
    assert approval.review_comment == "Rejected by manager."
    assert approval.reviewed_at is not None

    # -------------------------------------------------------------
    # TASK MUST BE FAILED
    # -------------------------------------------------------------
    task = get_task(
        company_id=case["company_id"],
        task_id=case["task_id"],
    )

    assert task is not None
    assert task.status == TaskStatus.FAILED.value
    assert task.result is not None
    assert "approval" in task.result.lower()
    assert "rejected" in task.result.lower()


def test_company_cannot_approve_another_company_approval():
    company_a = create_approval_case(
        company_name="Company A",
        user_email="manager-a@test.local",
        agent_name="Contract AI A",
        policy_name="Approval Policy A",
    )

    company_b = create_approval_case(
        company_name="Company B",
        user_email="manager-b@test.local",
        agent_name="Contract AI B",
        policy_name="Approval Policy B",
    )

    # -------------------------------------------------------------
    # CREATE PENDING APPROVAL FOR COMPANY A
    # -------------------------------------------------------------
    response = client.post(
        f"/api/v1/companies/{company_a['company_id']}/tasks/"
        f"{company_a['task_id']}/execute",
        headers={
            "X-User-ID": company_a["user_id"],
        },
    )

    assert response.status_code == 200
    assert response.json()["status"] == TaskStatus.WAITING_APPROVAL.value

    approval = get_approval(
        company_id=company_a["company_id"],
        task_id=company_a["task_id"],
    )

    assert approval is not None
    assert approval.status == ApprovalStatus.PENDING.value

    # -------------------------------------------------------------
    # COMPANY B TRIES TO APPROVE COMPANY A APPROVAL
    # -------------------------------------------------------------
    response = client.post(
        f"/api/v1/companies/{company_b['company_id']}/approvals/"
        f"{approval.id}/approve",
        headers={
            "X-User-ID": company_b["user_id"],
        },
        json={
            "comment": "Unauthorized cross-company approval attempt.",
        },
    )

    assert response.status_code == 409

    # -------------------------------------------------------------
    # COMPANY A APPROVAL MUST REMAIN PENDING
    # -------------------------------------------------------------
    approval = get_approval(
        company_id=company_a["company_id"],
        task_id=company_a["task_id"],
    )

    assert approval is not None
    assert approval.status == ApprovalStatus.PENDING.value

    # -------------------------------------------------------------
    # COMPANY A TASK MUST REMAIN WAITING FOR APPROVAL
    # -------------------------------------------------------------
    task = get_task(
        company_id=company_a["company_id"],
        task_id=company_a["task_id"],
    )

    assert task is not None
    assert task.status == TaskStatus.WAITING_APPROVAL.value


def test_approval_cannot_be_reviewed_twice():
    case = create_approval_case(
        company_name="Replay Approval Company",
        user_email="replay-manager@test.local",
        agent_name="Contract AI Replay",
        policy_name="Contract Search Approval Replay",
        knowledge_title="Replay Contract",
        knowledge_content="Replay protection test contract.",
    )

    # -------------------------------------------------------------
    # CREATE PENDING APPROVAL
    # -------------------------------------------------------------
    response = client.post(
        f"/api/v1/companies/{case['company_id']}/tasks/"
        f"{case['task_id']}/execute",
        headers={
            "X-User-ID": case["user_id"],
        },
    )

    assert response.status_code == 200
    assert response.json()["status"] == TaskStatus.WAITING_APPROVAL.value

    approval = get_approval(
        company_id=case["company_id"],
        task_id=case["task_id"],
    )

    assert approval is not None

    approval_id = approval.id

    # -------------------------------------------------------------
    # FIRST APPROVAL
    # -------------------------------------------------------------
    response = client.post(
        f"/api/v1/companies/{case['company_id']}/approvals/"
        f"{approval_id}/approve",
        headers={
            "X-User-ID": case["user_id"],
        },
        json={
            "comment": "First approval.",
        },
    )

    assert response.status_code == 200

    approval = get_approval(
        company_id=case["company_id"],
        task_id=case["task_id"],
    )

    assert approval is not None
    assert approval.status == ApprovalStatus.APPROVED.value

    # -------------------------------------------------------------
    # SECOND APPROVAL MUST BE REJECTED
    # -------------------------------------------------------------
    response = client.post(
        f"/api/v1/companies/{case['company_id']}/approvals/"
        f"{approval_id}/approve",
        headers={
            "X-User-ID": case["user_id"],
        },
        json={
            "comment": "Replay approval attempt.",
        },
    )

    assert response.status_code == 409

    # -------------------------------------------------------------
    # APPROVAL MUST STILL BE APPROVED
    # -------------------------------------------------------------
    approval = get_approval(
        company_id=case["company_id"],
        task_id=case["task_id"],
    )

    assert approval is not None
    assert approval.status == ApprovalStatus.APPROVED.value


def test_concurrent_task_execution_does_not_create_duplicate_approvals():
    from concurrent.futures import ThreadPoolExecutor

    case = create_approval_case(
        company_name="Concurrency Test Company",
        user_email="concurrency@example.com",
        agent_name="Concurrency Agent",
        policy_name="Concurrency Approval Policy",
        knowledge_title="Contract",
        knowledge_content="Sample contract content",
    )

    task_id = case["task_id"]
    company_id = case["company_id"]

    def execute_task():
        with TestingSessionLocal() as db:
            from app.services.task_runtime import TaskRuntimeService

            runtime = TaskRuntimeService()

            try:
                task = runtime.execute(
                    db,
                    company_id=company_id,
                    task_id=task_id,
                )

                return task.status

            except Exception as exc:
                return type(exc).__name__

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(
            executor.map(
                lambda _: execute_task(),
                range(2),
            )
        )

    with TestingSessionLocal() as db:
        approvals = list(
            db.scalars(
                select(Approval).where(
                    Approval.company_id == company_id,
                    Approval.task_id == task_id,
                )
            ).all()
        )

    assert len(approvals) <= 1, (
        f"Concurrent execution created {len(approvals)} approvals: "
        f"{approvals}"
    )


def test_concurrent_approval_does_not_execute_tool_twice():
    from concurrent.futures import ThreadPoolExecutor

    case = create_approval_case(
        company_name="Concurrent Approval Company",
        user_email="concurrent-approval@example.com",
        agent_name="Concurrent Approval Agent",
        policy_name="Concurrent Approval Policy",
        knowledge_title="Concurrent Contract",
        knowledge_content="Concurrent approval execution test contract.",
    )

    task_id = case["task_id"]
    company_id = case["company_id"]
    user_id = case["user_id"]

    # -------------------------------------------------------------
    # CREATE PENDING APPROVAL
    # -------------------------------------------------------------
    with TestingSessionLocal() as db:
        from app.services.task_runtime import TaskRuntimeService

        runtime = TaskRuntimeService()

        task = runtime.execute(
            db,
            company_id=company_id,
            task_id=task_id,
        )

        assert task.status == TaskStatus.WAITING_APPROVAL.value

    approval = get_approval(
        company_id=company_id,
        task_id=task_id,
    )

    assert approval is not None
    assert approval.status == ApprovalStatus.PENDING.value

    approval_id = approval.id

    # -------------------------------------------------------------
    # COUNT ACTUAL TOOL EXECUTIONS
    # -------------------------------------------------------------
    from threading import Lock

    execution_count = 0
    execution_count_lock = Lock()

    original_execute = SearchContractTool.execute

    def counted_execute(self, context, arguments):
        nonlocal execution_count

        with execution_count_lock:
            execution_count += 1

        return original_execute(self, context, arguments)

    # -------------------------------------------------------------
    # TWO CONCURRENT APPROVAL REQUESTS
    # -------------------------------------------------------------
    def approve():
        response = client.post(
            f'/api/v1/companies/{company_id}/approvals/{approval_id}/approve',
            headers={'X-User-ID': user_id},
            json={'comment': 'Concurrent approval test.'},
        )
        return response.status_code

    # Patch once around the complete concurrent operation.
    with patch.object(SearchContractTool, 'execute', new=counted_execute):
        with ThreadPoolExecutor(max_workers=2) as executor:
            results = list(
                executor.map(lambda _: approve(), range(2))
            )

    # -------------------------------------------------------------
    # EXACTLY ONE APPROVAL REQUEST MAY SUCCEED
    # -------------------------------------------------------------
    assert sorted(results) == [200, 409], (
        f"Unexpected concurrent approval responses: {results}"
    )

    # -------------------------------------------------------------
    # APPROVAL MUST ONLY BE APPROVED ONCE
    # -------------------------------------------------------------
    approval = get_approval(
        company_id=company_id,
        task_id=task_id,
    )

    assert approval is not None
    assert approval.status == ApprovalStatus.APPROVED.value

    # -------------------------------------------------------------
    # TOOL MUST ONLY EXECUTE ONCE
    # -------------------------------------------------------------
    assert execution_count == 1, (
        f"Concurrent approval executed tool "
        f"{execution_count} times instead of once."
    )

    # -------------------------------------------------------------
    # TASK MUST COMPLETE
    # -------------------------------------------------------------
    task = get_task(
        company_id=company_id,
        task_id=task_id,
    )

    assert task is not None
    assert task.status == TaskStatus.COMPLETED.value


def test_concurrent_resume_after_approval_executes_tool_once():
    from concurrent.futures import ThreadPoolExecutor
    from threading import Lock

    case = create_approval_case(
        company_name="Concurrent Resume Company",
        user_email="concurrent-resume@example.com",
        agent_name="Concurrent Resume Agent",
        policy_name="Concurrent Resume Policy",
        knowledge_title="Concurrent Resume Contract",
        knowledge_content="Concurrent resume execution test contract.",
    )

    task_id = case["task_id"]
    company_id = case["company_id"]

    # -------------------------------------------------------------
    # CREATE PENDING APPROVAL
    # -------------------------------------------------------------
    with TestingSessionLocal() as db:
        from app.services.task_runtime import TaskRuntimeService

        runtime = TaskRuntimeService()

        task = runtime.execute(
            db,
            company_id=company_id,
            task_id=task_id,
        )

        assert task.status == TaskStatus.WAITING_APPROVAL.value

    approval = get_approval(
        company_id=company_id,
        task_id=task_id,
    )

    assert approval is not None
    assert approval.status == ApprovalStatus.PENDING.value

    approval_id = approval.id

    # -------------------------------------------------------------
    # APPROVE ONCE
    # -------------------------------------------------------------
    with TestingSessionLocal() as db:
        from app.services.approval import ApprovalService

        approval_service = ApprovalService(db)

        approved = approval_service.approve(
            approval_id=approval_id,
            company_id=company_id,
            user_id=case["user_id"],
            comment="Approve concurrent resume test.",
        )

        assert approved.status == ApprovalStatus.APPROVED.value

    # -------------------------------------------------------------
    # COUNT ACTUAL TOOL EXECUTIONS
    # -------------------------------------------------------------
    execution_count = 0
    execution_count_lock = Lock()

    from app.tools.contract import SearchContractTool

    original_execute = SearchContractTool.execute

    def counted_execute(self, context, arguments):
        nonlocal execution_count

        with execution_count_lock:
            execution_count += 1

        return original_execute(self, context, arguments)

    # -------------------------------------------------------------
    # TWO CONCURRENT RESUME REQUESTS
    # -------------------------------------------------------------
    def resume():
        with TestingSessionLocal() as db:
            from app.services.task_runtime import TaskRuntimeService

            runtime = TaskRuntimeService()

            try:
                task = runtime.resume_after_approval(
                    db,
                    company_id=company_id,
                    task_id=task_id,
                    approval_id=approval_id,
                )

                return ("success", task.status)

            except ValueError as exc:
                return ("error", str(exc))

    with patch.object(
        SearchContractTool,
        "execute",
        new=counted_execute,
    ):
        with ThreadPoolExecutor(max_workers=2) as executor:
            results = list(
                executor.map(
                    lambda _: resume(),
                    range(2),
                )
            )

    # -------------------------------------------------------------
    # EXACTLY ONE RESUME MAY WIN
    # -------------------------------------------------------------
    successful = [
        result
        for result in results
        if result[0] == "success"
    ]

    failed = [
        result
        for result in results
        if result[0] == "error"
    ]

    assert len(successful) == 1, (
        f"Expected exactly one successful resume: {results}"
    )

    assert len(failed) == 1, (
        f"Expected exactly one rejected resume: {results}"
    )

    # -------------------------------------------------------------
    # TOOL MUST ONLY EXECUTE ONCE
    # -------------------------------------------------------------
    assert execution_count == 1, (
        f"Concurrent resume executed tool "
        f"{execution_count} times instead of once."
    )

    # -------------------------------------------------------------
    # TASK MUST COMPLETE
    # -------------------------------------------------------------
    task = get_task(
        company_id=company_id,
        task_id=task_id,
    )

    assert task is not None
    assert task.status == TaskStatus.COMPLETED.value
