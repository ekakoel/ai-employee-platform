"""Job 30 — Marketplace read-model tests."""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from app.core.database import Base, get_db
from app.main import app
from app.models.entities import MarketplaceInstallation, Skill
from app.services.seed import seed_catalog

engine = create_engine(
    "sqlite:///./test_marketplace_job30.db",
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
    co = client.post("/api/v1/companies", json={"name": "Market Co"}).json()
    owner = client.post(
        f"/api/v1/companies/{co['id']}/users",
        json={
            "name": "Owner",
            "email": "market@test.local",
            "role": "owner",
            "password": "secret123",
        },
    ).json()
    return co["id"], {"X-User-ID": owner["id"]}


def test_list_public_templates(client):
    r = client.get("/api/v1/marketplace/templates")
    assert r.status_code == 200, r.text
    items = r.json()
    assert len(items) >= 2
    slugs = {t["slug"] for t in items}
    assert "reservation" in slugs
    assert "contract-manager" in slugs
    for t in items:
        assert t["is_published"] is True
        assert "name" in t
        assert "skills" in t


def test_get_public_template(client):
    listing = client.get("/api/v1/marketplace/templates").json()
    catalog_id = listing[0]["id"]
    r = client.get(f"/api/v1/marketplace/templates/{catalog_id}")
    assert r.status_code == 200
    assert r.json()["id"] == catalog_id

    bad = client.get("/api/v1/marketplace/templates/does-not-exist")
    assert bad.status_code == 404


def test_install_creates_company_skills(client):
    company_id, headers = setup(client)
    templates = client.get("/api/v1/marketplace/templates").json()
    reservation = next(t for t in templates if t["slug"] == "reservation")
    catalog_id = reservation["id"]

    # Before install: company skills list empty (or no platform copies)
    before = client.get(
        f"/api/v1/companies/{company_id}/skills", headers=headers
    ).json()
    before_slugs = {s["slug"] for s in before}

    inst = client.post(
        f"/api/v1/companies/{company_id}/marketplace/install/{catalog_id}",
        headers=headers,
    )
    assert inst.status_code == 201, inst.text
    body = inst.json()
    assert body["installation"]["catalog_slug"] == "reservation"
    assert body["installation"]["company_id"] == company_id
    assert len(body["installation"]["installed_skill_ids"]) >= 1
    assert len(body["skills"]) >= 1
    for sk in body["skills"]:
        assert sk["company_id"] == company_id
        assert sk["is_active"] is True

    # Response skills must be company-scoped copies
    company_skills = [s for s in body["skills"] if s["company_id"] == company_id]
    assert len(company_skills) >= 1
    # And appear in company skill list with company_id set
    after = client.get(
        f"/api/v1/companies/{company_id}/skills", headers=headers
    ).json()
    company_only = [s for s in after if s.get("company_id") == company_id]
    assert len(company_only) >= 1
    assert {s["slug"] for s in company_skills} <= {s["slug"] for s in company_only}


def test_install_idempotent_conflict(client):
    company_id, headers = setup(client)
    templates = client.get("/api/v1/marketplace/templates").json()
    catalog_id = next(t for t in templates if t["slug"] == "reservation")["id"]

    first = client.post(
        f"/api/v1/companies/{company_id}/marketplace/install/{catalog_id}",
        headers=headers,
    )
    assert first.status_code == 201

    second = client.post(
        f"/api/v1/companies/{company_id}/marketplace/install/{catalog_id}",
        headers=headers,
    )
    assert second.status_code == 409


def test_list_installations(client):
    company_id, headers = setup(client)
    templates = client.get("/api/v1/marketplace/templates").json()
    catalog_id = next(t for t in templates if t["slug"] == "contract-manager")["id"]

    client.post(
        f"/api/v1/companies/{company_id}/marketplace/install/{catalog_id}",
        headers=headers,
    )
    listing = client.get(
        f"/api/v1/companies/{company_id}/marketplace/installations",
        headers=headers,
    )
    assert listing.status_code == 200
    rows = listing.json()
    assert len(rows) == 1
    assert rows[0]["catalog_slug"] == "contract-manager"


def test_tenant_isolation_installations(client):
    co1, h1 = setup(client)
    # second company
    co2 = client.post("/api/v1/companies", json={"name": "Other Market Co"}).json()
    owner2 = client.post(
        f"/api/v1/companies/{co2['id']}/users",
        json={
            "name": "Owner2",
            "email": "market2@test.local",
            "role": "owner",
            "password": "secret123",
        },
    ).json()
    h2 = {"X-User-ID": owner2["id"]}

    templates = client.get("/api/v1/marketplace/templates").json()
    catalog_id = templates[0]["id"]
    client.post(
        f"/api/v1/companies/{co1}/marketplace/install/{catalog_id}",
        headers=h1,
    )

    # Company 2 cannot see company 1 installations
    other = client.get(
        f"/api/v1/companies/{co1}/marketplace/installations",
        headers=h2,
    )
    assert other.status_code == 403

    empty = client.get(
        f"/api/v1/companies/{co2['id']}/marketplace/installations",
        headers=h2,
    )
    assert empty.status_code == 200
    assert empty.json() == []
