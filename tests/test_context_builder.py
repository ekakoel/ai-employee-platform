from app.agents.context import AgentContext
from app.agents.context_builder import AgentContextBuilder


class FakeAgent:
    def __init__(self) -> None:
        self.id = 10
        self.company_id = 1


class FakeTask:
    def __init__(self) -> None:
        self.id = 100
        self.company_id = 1
        self.title = "Find Villa ABC contract"
        self.instruction = "Find the contract for Villa ABC."


def test_context_builder_delegates_to_context_loader(monkeypatch):
    expected = AgentContext(
        company_id=1,
        company_name="Bali Kami Tour",
        agent_instance_id=10,
        agent_name="Contract Manager",
        agent_role="Contract Manager",
    )

    def fake_loader(db, agent, task=None):
        assert agent.id == 10
        assert task is None
        return expected

    monkeypatch.setattr(
        "app.agents.context_builder.load_agent_context",
        fake_loader,
    )

    builder = AgentContextBuilder(object())

    context = builder.build(FakeAgent())

    assert context is expected


def test_context_builder_passes_task(monkeypatch):
    expected = AgentContext(
        company_id=1,
        company_name="Bali Kami Tour",
        agent_instance_id=10,
        agent_name="Contract Manager",
        agent_role="Contract Manager",
        task_id=100,
        task_title="Find Villa ABC contract",
        task_instruction="Find the contract for Villa ABC.",
    )

    task = FakeTask()

    def fake_loader(db, agent, task=None):
        assert agent.id == 10
        assert task is not None
        assert task.id == 100
        return expected

    monkeypatch.setattr(
        "app.agents.context_builder.load_agent_context",
        fake_loader,
    )

    builder = AgentContextBuilder(object())

    context = builder.build(
        FakeAgent(),
        task,
    )

    assert context is expected
    assert context.task_id == 100