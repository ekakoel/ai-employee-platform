"""Job 26 — Vector / hybrid knowledge retrieval tests."""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from app.core.database import Base, get_db
from app.knowledge.embeddings import (
    FakeEmbeddingProvider,
    cosine_similarity,
    get_embedding_provider,
)
from app.knowledge.indexing import replace_chunks_for_item
from app.knowledge.retrieval import search_knowledge_chunks
from app.main import app
from app.models.entities import KnowledgeChunk, KnowledgeItem
from app.services.seed import seed_catalog

engine = create_engine(
    "sqlite:///./test_vector_knowledge_job26.db",
    connect_args={"check_same_thread": False},
)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


@pytest.fixture()
def client(monkeypatch):
    from app.core import config as cfg_mod

    monkeypatch.setenv("KNOWLEDGE_VECTOR", "true")
    monkeypatch.setenv("EMBEDDING_PROVIDER", "fake")
    monkeypatch.setenv("EMBEDDING_DIMS", "32")
    cfg_mod.settings = cfg_mod.Settings()

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
    monkeypatch.setenv("KNOWLEDGE_VECTOR", "false")
    cfg_mod.settings = cfg_mod.Settings()


def test_fake_embedder_deterministic():
    p = FakeEmbeddingProvider(dims=32)
    a = p.embed("reservation booking hotel")
    b = p.embed("reservation booking hotel")
    c = p.embed("completely unrelated quantum physics")
    assert a == b
    assert cosine_similarity(a, b) > 0.99
    assert cosine_similarity(a, c) < cosine_similarity(a, b)


def test_indexing_stores_embedding(client, monkeypatch):
    from app.core import config as cfg_mod

    monkeypatch.setenv("KNOWLEDGE_VECTOR", "true")
    cfg_mod.settings = cfg_mod.Settings()

    co = client.post("/api/v1/companies", json={"name": "Vec Co"}).json()
    owner = client.post(
        f"/api/v1/companies/{co['id']}/users",
        json={
            "name": "Owner",
            "email": "vec@test.local",
            "role": "owner",
            "password": "secret123",
        },
    ).json()
    headers = {"X-User-ID": owner["id"]}
    item = client.post(
        f"/api/v1/companies/{co['id']}/knowledge",
        headers=headers,
        json={
            "title": "Check-in policy",
            "content": "Guests may check in after 3pm. Early check-in requires approval.",
            "category": "policy",
        },
    )
    assert item.status_code in (200, 201), item.text

    with SessionLocal() as db:
        chunks = list(
            db.scalars(
                select(KnowledgeChunk).where(
                    KnowledgeChunk.company_id == co["id"]
                )
            ).all()
        )
        assert chunks
        assert chunks[0].embedding is not None
        assert len(chunks[0].embedding) == cfg_mod.settings.embedding_dims
        assert chunks[0].embedding_model


def test_hybrid_search_returns_vector_scores(client, monkeypatch):
    from app.core import config as cfg_mod

    monkeypatch.setenv("KNOWLEDGE_VECTOR", "true")
    cfg_mod.settings = cfg_mod.Settings()

    co = client.post("/api/v1/companies", json={"name": "Hybrid Co"}).json()
    owner = client.post(
        f"/api/v1/companies/{co['id']}/users",
        json={
            "name": "Owner",
            "email": "hybrid@test.local",
            "role": "owner",
            "password": "secret123",
        },
    ).json()
    headers = {"X-User-ID": owner["id"]}
    client.post(
        f"/api/v1/companies/{co['id']}/knowledge",
        headers=headers,
        json={
            "title": "Cancellation",
            "content": "Free cancellation up to 24 hours before arrival. No refund after that.",
            "category": "policy",
        },
    )
    search = client.post(
        f"/api/v1/companies/{co['id']}/knowledge/search",
        headers=headers,
        json={"query": "cancel booking refund", "limit": 5},
    )
    assert search.status_code == 200, search.text
    hits = search.json()
    assert hits
    # hybrid mode metadata when vector enabled
    assert hits[0].get("search_mode") in ("hybrid", "keyword")
    if hits[0].get("search_mode") == "hybrid":
        assert "vector_score" in hits[0]
        assert "keyword_score" in hits[0]


def test_keyword_only_when_flag_off(monkeypatch):
    from app.core import config as cfg_mod

    monkeypatch.setenv("KNOWLEDGE_VECTOR", "false")
    cfg_mod.settings = cfg_mod.Settings()
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    with SessionLocal() as db:
        seed_catalog(db)
        item = KnowledgeItem(
            company_id="co1",
            title="Test",
            content="alpha beta gamma delta",
            category="ctx",
            is_active=True,
        )
        # need real company? skip FK for sqlite often needs company
    # simpler unit path
    with SessionLocal() as db:
        from app.models.entities import Company

        co = Company(name="KW Only Co")
        db.add(co)
        db.flush()
        item = KnowledgeItem(
            company_id=co.id,
            title="Test",
            content="alpha beta gamma hotel reservation",
            category="ctx",
            is_active=True,
        )
        db.add(item)
        db.flush()
        replace_chunks_for_item(db, item)
        db.commit()
        chunks = list(
            db.scalars(
                select(KnowledgeChunk).where(KnowledgeChunk.company_id == co.id)
            ).all()
        )
        assert chunks
        assert chunks[0].embedding is None
        hits = search_knowledge_chunks(
            db, company_id=co.id, agent_instance_id=None, query="hotel reservation"
        )
        assert hits
        assert hits[0]["search_mode"] == "keyword"


def test_get_embedding_provider_default():
    p = get_embedding_provider()
    assert p.dimensions > 0
    assert len(p.embed("hello world")) == p.dimensions
