"""Phase 6 — Knowledge chunking, retrieval, and agent memory."""

from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from app.core.database import Base, get_db
from app.knowledge.chunking import chunk_text
from app.knowledge.retrieval import score_text, search_knowledge_chunks
from app.main import app
from app.models.entities import KnowledgeChunk
from app.services.seed import seed_catalog

engine = create_engine(
    "sqlite:///./test_knowledge_memory.db",
    connect_args={"check_same_thread": False},
)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


@pytest.fixture()
def client():
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    with SessionLocal() as db:
        seed_catalog(db)

    def override():
        db = SessionLocal()
        try:
            yield db
        finally:
            db.close()

    prev = app.dependency_overrides.get(get_db)
    app.dependency_overrides[get_db] = override
    with TestClient(app) as c:
        yield c
    if prev is None:
        app.dependency_overrides.pop(get_db, None)
    else:
        app.dependency_overrides[get_db] = prev


def setup(client):
    co = client.post("/api/v1/companies", json={"name": "Know Co"}).json()
    owner = client.post(
        f"/api/v1/companies/{co['id']}/users",
        json={"name": "Owner", "email": "owner@k.test", "role": "owner"},
    ).json()
    catalog = client.get("/api/v1/agent-catalog").json()
    res = next(i for i in catalog if i["slug"] == "reservation")
    hire = client.post(
        f"/api/v1/companies/{co['id']}/agents/{res['id']}/hire",
        json={"name": "Know AI"},
        headers={"X-User-ID": owner["id"]},
    )
    assert hire.status_code == 201
    return co["id"], owner["id"], hire.json()["id"]


def test_chunk_text_splits_long_content():
    text = ("Paragraph one about pricing.\n\n" * 5) + ("More content on refunds.\n\n" * 5)
    chunks = chunk_text(text, max_chars=120, overlap=20)
    assert len(chunks) >= 2
    assert all(isinstance(c, str) and c for c in chunks)


def test_knowledge_create_indexes_chunks(client):
    company_id, owner_id, agent_id = setup(client)
    body = {
        "title": "Pricing Rules",
        "content": (
            "Standard room rate is 100 USD.\n\n"
            "Suite rate is 250 USD.\n\n"
            "Refund policy requires manager approval above 500 USD."
        ),
        "category": "pricing",
    }
    resp = client.post(
        f"/api/v1/companies/{company_id}/knowledge",
        headers={"X-User-ID": owner_id},
        json=body,
    )
    assert resp.status_code == 201, resp.text
    item_id = resp.json()["id"]

    with SessionLocal() as db:
        chunks = list(
            db.scalars(
                select(KnowledgeChunk).where(
                    KnowledgeChunk.knowledge_item_id == item_id
                )
            ).all()
        )
        assert len(chunks) >= 1
        assert all(c.company_id == company_id for c in chunks)


def test_search_finds_relevant_chunk(client):
    company_id, owner_id, agent_id = setup(client)
    client.post(
        f"/api/v1/companies/{company_id}/knowledge",
        headers={"X-User-ID": owner_id},
        json={
            "title": "Cancellation",
            "content": "Customers may cancel free within 24 hours. Late cancel incurs fee.",
            "category": "policy",
        },
    )
    search = client.post(
        f"/api/v1/companies/{company_id}/knowledge/search",
        headers={"X-User-ID": owner_id},
        json={"query": "cancel fee", "limit": 5},
    )
    assert search.status_code == 200, search.text
    hits = search.json()
    assert len(hits) >= 1
    assert hits[0]["score"] > 0


def test_tenant_isolation_search(client):
    c1, o1, _ = setup(client)
    client.post(
        f"/api/v1/companies/{c1}/knowledge",
        headers={"X-User-ID": o1},
        json={"title": "Secret", "content": "UniqueTokenXYZ123 confidential", "category": "x"},
    )
    co2 = client.post("/api/v1/companies", json={"name": "OtherKnow"}).json()
    o2 = client.post(
        f"/api/v1/companies/{co2['id']}/users",
        json={"name": "O2", "email": "o2@k.test", "role": "owner"},
    ).json()
    search = client.post(
        f"/api/v1/companies/{co2['id']}/knowledge/search",
        headers={"X-User-ID": o2["id"]},
        json={"query": "UniqueTokenXYZ123", "limit": 5},
    )
    assert search.status_code == 200
    assert search.json() == []


def test_agent_memory_lifecycle(client):
    company_id, owner_id, agent_id = setup(client)
    created = client.post(
        f"/api/v1/companies/{company_id}/agents/{agent_id}/memories",
        headers={"X-User-ID": owner_id},
        json={
            "title": "Preferred contact",
            "content": "Customer prefers WhatsApp for follow-up.",
            "category": "preference",
        },
    )
    assert created.status_code == 201, created.text
    mem_id = created.json()["id"]

    listed = client.get(
        f"/api/v1/companies/{company_id}/agents/{agent_id}/memories",
        headers={"X-User-ID": owner_id},
    )
    assert listed.status_code == 200
    assert any(m["id"] == mem_id for m in listed.json())

    deleted = client.delete(
        f"/api/v1/companies/{company_id}/agents/{agent_id}/memories/{mem_id}",
        headers={"X-User-ID": owner_id},
    )
    assert deleted.status_code == 204

    listed2 = client.get(
        f"/api/v1/companies/{company_id}/agents/{agent_id}/memories",
        headers={"X-User-ID": owner_id},
    )
    assert all(m["id"] != mem_id for m in listed2.json())


def test_expired_memory_not_listed(client):
    company_id, owner_id, agent_id = setup(client)
    past = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()
    created = client.post(
        f"/api/v1/companies/{company_id}/agents/{agent_id}/memories",
        headers={"X-User-ID": owner_id},
        json={
            "title": "Expired note",
            "content": "Should not appear",
            "expires_at": past,
        },
    )
    assert created.status_code == 201
    listed = client.get(
        f"/api/v1/companies/{company_id}/agents/{agent_id}/memories",
        headers={"X-User-ID": owner_id},
    ).json()
    assert all(m["title"] != "Expired note" for m in listed)


def test_score_text_basic():
    assert score_text("refund policy", "The refund policy requires approval") > 0
    assert score_text("xyz", "no match here") == 0
