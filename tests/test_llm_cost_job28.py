"""Job 28 — LLM usage / cost dashboard tests."""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from app.core.database import Base, get_db
from app.llm.base import LLMMessage, LLMResponse
from app.main import app
from app.models.entities import LLMUsage
from app.services.llm_usage import (
    RecordingLLMProvider,
    check_llm_budget,
    cost_summary,
    estimate_cost_usd,
    record_llm_usage,
)
from app.services.seed import seed_catalog

engine = create_engine(
    "sqlite:///./test_llm_cost_job28.db",
    connect_args={"check_same_thread": False},
)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


class StubProvider:
    def chat(self, messages, *, temperature=0.0, tools=None):
        return LLMResponse(
            content="ok",
            model="stub-model",
            prompt_tokens=100,
            completion_tokens=50,
            total_tokens=150,
        )


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
    co = client.post("/api/v1/companies", json={"name": "Cost Co"}).json()
    owner = client.post(
        f"/api/v1/companies/{co['id']}/users",
        json={
            "name": "Owner",
            "email": "cost@test.local",
            "role": "owner",
            "password": "secret123",
        },
    ).json()
    return co["id"], {"X-User-ID": owner["id"]}


def test_estimate_and_record(client):
    company_id, headers = setup(client)
    cost = estimate_cost_usd(1000, 1000, prompt_rate=0.01, completion_rate=0.02)
    assert abs(cost - 0.03) < 1e-9

    with SessionLocal() as db:
        row = record_llm_usage(
            db,
            company_id=company_id,
            model="m",
            prompt_tokens=100,
            completion_tokens=20,
            total_tokens=120,
        )
        db.commit()
        assert row.total_tokens == 120

    summary = client.get(
        f"/api/v1/companies/{company_id}/governance/cost",
        headers=headers,
    )
    assert summary.status_code == 200, summary.text
    body = summary.json()
    assert body["all_time"]["calls"] >= 1
    assert body["all_time"]["total_tokens"] >= 120
    assert "budget" in body


def test_recording_provider(client):
    company_id, headers = setup(client)
    with SessionLocal() as db:
        wrap = RecordingLLMProvider(
            StubProvider(),
            db,
            company_id=company_id,
            enforce_budget=False,
        )
        resp = wrap.chat([LLMMessage(role="user", content="hi")])
        assert resp.content == "ok"
        db.commit()
        rows = list(
            db.scalars(
                select(LLMUsage).where(LLMUsage.company_id == company_id)
            ).all()
        )
        assert len(rows) == 1
        assert rows[0].prompt_tokens == 100
        assert rows[0].model == "stub-model"


def test_soft_budget(client, monkeypatch):
    from app.core import config as cfg_mod

    company_id, headers = setup(client)
    monkeypatch.setenv("LLM_DAILY_BUDGET_USD", "0.001")
    monkeypatch.setenv("LLM_COST_PER_1K_PROMPT_TOKENS", "10")
    monkeypatch.setenv("LLM_COST_PER_1K_COMPLETION_TOKENS", "10")
    cfg_mod.settings = cfg_mod.Settings()

    with SessionLocal() as db:
        record_llm_usage(
            db,
            company_id=company_id,
            model="pricey",
            prompt_tokens=1000,
            completion_tokens=1000,
        )
        db.commit()
        with pytest.raises(Exception) as ei:
            check_llm_budget(db, company_id=company_id)
        assert ei.value.status_code == 429

    # reset
    monkeypatch.setenv("LLM_DAILY_BUDGET_USD", "0")
    cfg_mod.settings = cfg_mod.Settings()
