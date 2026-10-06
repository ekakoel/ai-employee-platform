from app.agents.context import AgentContext


def test_agent_context_contains_agent_information():
    context = AgentContext(
        company_id=1,
        company_name="Bali Kami Tour",
        agent_instance_id=10,
        agent_name="Contract Manager",
        agent_role="Contract Manager",
        skills=[
            "contract_search",
            "contract_analysis",
        ],
        allowed_tools=[
            "search_contract",
        ],
    )

    data = context.to_dict()

    assert data["company"]["id"] == 1
    assert data["company"]["name"] == "Bali Kami Tour"

    assert data["agent"]["id"] == 10
    assert data["agent"]["name"] == "Contract Manager"

    assert "contract_search" in data["agent"]["skills"]
    assert "search_contract" in data["agent"]["allowed_tools"]


def test_agent_context_contains_task():
    context = AgentContext(
        company_id=1,
        company_name="Bali Kami Tour",
        agent_instance_id=10,
        agent_name="Contract Manager",
        agent_role="Contract Manager",
        task_id=100,
        task_title="Find Villa ABC contract",
        task_instruction="Find the contract for Villa ABC.",
    )

    data = context.to_dict()

    assert data["task"]["id"] == 100
    assert data["task"]["title"] == "Find Villa ABC contract"
    assert (
        data["task"]["instruction"]
        == "Find the contract for Villa ABC."
    )


def test_agent_context_contains_knowledge():
    context = AgentContext(
        company_id=1,
        company_name="Bali Kami Tour",
        agent_instance_id=10,
        agent_name="Contract Manager",
        agent_role="Contract Manager",
        knowledge=[
            {
                "title": "Villa ABC Contract",
                "content": "Contract valid until December 2026.",
                "category": "contract",
            }
        ],
    )

    data = context.to_dict()

    assert len(data["knowledge"]) == 1
    assert data["knowledge"][0]["title"] == "Villa ABC Contract"
    assert "December 2026" in data["knowledge"][0]["content"]


def test_agent_context_has_safe_defaults():
    context = AgentContext(
        company_id=1,
        company_name="Bali Kami Tour",
        agent_instance_id=10,
        agent_name="Contract Manager",
        agent_role="Contract Manager",
    )

    data = context.to_dict()

    assert data["agent"]["skills"] == []
    assert data["agent"]["allowed_tools"] == []
    assert data["task"]["id"] is None
    assert data["task"]["title"] is None
    assert data["task"]["instruction"] is None
    assert data["knowledge"] == []
    assert data["configuration"] == {}