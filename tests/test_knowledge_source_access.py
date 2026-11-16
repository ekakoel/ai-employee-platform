from types import SimpleNamespace

from app.security.knowledge_access import grant_allows
from app.knowledge.retrieval import deduplicate_source_hits


def _grant(**overrides):
    values = {
        "classification": "B",
        "is_active": True,
        "is_approved": True,
        "approved_by_user_id": "approver-1",
        "approved_at": object(),
        "allowed_user_ids": [],
        "allowed_agent_instance_ids": ["agent-1"],
        "allowed_role_ids": ["role-ops"],
        "allowed_department_ids": [],
        "allowed_purposes": ["task_execution"],
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def _user(**overrides):
    values = {"id": "user-1", "role_id": "role-ops", "department_id": "dept-1"}
    values.update(overrides)
    return SimpleNamespace(**values)


def test_internal_grant_requires_active_approval_audience_and_purpose():
    assert grant_allows(_grant(), _user(), "task_execution", "agent-1")
    assert not grant_allows(_grant(is_active=False), _user(), "task_execution", "agent-1")
    assert not grant_allows(_grant(is_approved=False), _user(), "task_execution", "agent-1")
    assert not grant_allows(_grant(approved_by_user_id=None), _user(), "task_execution", "agent-1")
    assert not grant_allows(_grant(allowed_purposes=[]), _user(), "task_execution", "agent-1")
    assert not grant_allows(_grant(allowed_role_ids=[]), _user(), "task_execution", "agent-1")


def test_restricted_grant_requires_explicit_user_and_purpose():
    grant = _grant(
        classification="C",
        allowed_user_ids=["user-1"],
        allowed_role_ids=["role-ops"],
    )
    assert grant_allows(grant, _user(), "task_execution", "agent-1")
    assert not grant_allows(grant, _user(id="user-2"), "task_execution", "agent-1")


def test_secret_and_unclassified_sources_are_never_allowed():
    for classification in ("D", "U", "unknown", ""):
        assert not grant_allows(
            _grant(classification=classification, allowed_user_ids=["*"]),
            _user(),
            "task_execution",
            "agent-1",
        )


def test_public_corpus_requires_explicit_wildcard_admission():
    assert grant_allows(
        _grant(classification="A", allowed_user_ids=["*"]),
        _user(),
        "task_execution",
        "agent-1",
    )
    assert not grant_allows(
        _grant(classification="A", allowed_user_ids=["user-1"]),
        _user(),
        "task_execution",
        "*",
    )


def test_duplicate_passages_deduplicate_within_source_but_keep_provenance():
    hits = [
        {"id": "c1", "content": "Same   passage.", "source_type": "item", "source_id": "item-1", "score": 0.9},
        {"id": "c2", "content": " same passage. ", "source_type": "item", "source_id": "item-1", "score": 0.8},
        {"id": "c3", "content": "Same passage.", "source_type": "item", "source_id": "item-2", "score": 0.7},
    ]
    result = deduplicate_source_hits(hits)
    assert [row["id"] for row in result] == ["c1", "c3"]
