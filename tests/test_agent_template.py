"""Phase 2 — Agent Template snapshot and isolation tests."""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from tests.helpers import provision_company
from app.core.database import Base, get_db
from app.main import app
from app.models.entities import AgentCatalog, AgentInstance
from app.services.seed import seed_catalog


engine = create_engine(
    "sqlite:///./test_agent_template.db",
    connect_args={"check_same_thread": False},
)
TestingSessionLocal = sessionmaker(
    bind=engine, autoflush=False, autocommit=False
)


@pytest.fixture()
def client():
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

    previous = app.dependency_overrides.get(get_db)
    app.dependency_overrides[get_db] = override_get_db

    with TestClient(app) as c:
        yield c

    if previous is None:
        app.dependency_overrides.pop(get_db, None)
    else:
        app.dependency_overrides[get_db] = previous


# def _create_company_with_owner(client: TestClient):
#     company = client.post(
#         "/api/v1/companies",
#         json={"name": "Template Co"},
#     )
#     assert company.status_code == 201, company.text
#     company_id = company.json()["id"]

#     user = client.post(
#         f"/api/v1/companies/{company_id}/users",
#         json={
#             "name": "Owner",
#             "email": "owner@template.test",
#             "role": "owner",
#         },
#     )
#     assert user.status_code == 201, user.text
#     return company_id, user.json()["id"]
def _create_company_with_owner(client: TestClient):
    company_id, user_id, headers, _ = provision_company(client)
    return company_id, user_id, headers

def test_catalog_exposes_template_fields(client: TestClient):
    response = client.get("/api/v1/agent-catalog")
    assert response.status_code == 200
    items = response.json()
    assert len(items) >= 2

    reservation = next(i for i in items if i["slug"] == "reservation")
    assert reservation["version"] == "1.0.0"
    assert "reservation" in reservation["scope"]
    assert reservation["default_autonomy"] == "1"
    assert reservation["default_policies"]["send_quotation"] == "approval"
    assert reservation["is_published"] is True
    assert "You are Reservation AI" in reservation["default_instructions"]


def test_hire_snapshots_template_version_and_defaults(client: TestClient):
    company_id, user_id, headers = _create_company_with_owner(client)

    catalog = client.get("/api/v1/agent-catalog").json()
    reservation = next(i for i in catalog if i["slug"] == "reservation")

    hire = client.post(
        f"/api/v1/companies/{company_id}/agents/{reservation['id']}/hire",
        json={"name": "Front Desk AI"},
        headers=headers,
    )
    assert hire.status_code == 201, hire.text
    instance = hire.json()

    assert instance["template_version"] == reservation["version"]
    assert instance["skills"] == reservation["skills"]
    assert instance["allowed_tools"] == reservation["allowed_tools"]
    assert instance["scope"] == reservation["scope"]
    assert instance["autonomy"] == reservation["default_autonomy"]
    assert instance["policies"] == reservation["default_policies"]
    assert instance["instructions"] == reservation["default_instructions"]
    assert instance["configuration"]["evaluation_criteria"] == (
        reservation["evaluation_criteria"]
    )


def test_catalog_mutation_does_not_change_existing_instance(client: TestClient):
    company_id, user_id, headers = _create_company_with_owner(client)

    catalog_items = client.get("/api/v1/agent-catalog").json()
    reservation = next(i for i in catalog_items if i["slug"] == "reservation")

    hire = client.post(
        f"/api/v1/companies/{company_id}/agents/{reservation['id']}/hire",
        json={"name": "Pinned AI"},
        headers=headers,
    )
    assert hire.status_code == 201
    instance_id = hire.json()["id"]
    original_skills = list(hire.json()["skills"])
    original_version = hire.json()["template_version"]

    # Mutate catalog defaults after hire.
    with TestingSessionLocal() as db:
        cat = db.scalar(
            select(AgentCatalog).where(AgentCatalog.slug == "reservation")
        )
        assert cat is not None
        cat.skills = ["mutated_skill_only"]
        cat.version = "9.9.9"
        cat.default_instructions = "MUTATED"
        db.commit()

    with TestingSessionLocal() as db:
        inst = db.get(AgentInstance, instance_id)
        assert inst is not None
        assert inst.template_version == original_version
        assert list(inst.skills) == original_skills
        assert inst.instructions != "MUTATED"
        assert "mutated_skill_only" not in (inst.skills or [])


def test_unpublished_catalog_not_hireable(client: TestClient):
    company_id, user_id, headers = _create_company_with_owner(client)

    with TestingSessionLocal() as db:
        cat = db.scalar(
            select(AgentCatalog).where(AgentCatalog.slug == "reservation")
        )
        cat.is_published = False
        db.commit()
        catalog_id = cat.id

    hire = client.post(
        f"/api/v1/companies/{company_id}/agents/{catalog_id}/hire",
        json={"name": "Should Fail"},
        headers=headers,
    )
    assert hire.status_code == 404


def test_patch_instance_customization(client: TestClient):
    company_id, user_id, headers = _create_company_with_owner(client)
    catalog = client.get("/api/v1/agent-catalog").json()
    reservation = next(i for i in catalog if i["slug"] == "reservation")

    hire = client.post(
        f"/api/v1/companies/{company_id}/agents/{reservation['id']}/hire",
        json={"name": "Customizable AI"},
        headers=headers,
    )
    assert hire.status_code == 201
    instance_id = hire.json()["id"]

    updated = client.patch(
        f"/api/v1/companies/{company_id}/agents/{instance_id}",
        json={
            "instructions": "Custom company instructions",
            "autonomy": "2",
            "policies": {"send_quotation": "deny"},
        },
        headers=headers,
    )
    assert updated.status_code == 200, updated.text
    body = updated.json()
    assert body["instructions"] == "Custom company instructions"
    assert body["autonomy"] == "2"
    assert body["policies"]["send_quotation"] == "deny"


def test_patch_instance_profile_configuration(client: TestClient):
    company_id, user_id, headers = _create_company_with_owner(client)
    catalog = client.get("/api/v1/agent-catalog").json()
    reservation = next(i for i in catalog if i["slug"] == "reservation")

    hire = client.post(
        f"/api/v1/companies/{company_id}/agents/{reservation['id']}/hire",
        json={"name": "Profile Test AI"},
        headers=headers,
    )
    assert hire.status_code == 201, hire.text
    instance_id = hire.json()["id"]

    original_configuration = hire.json()["configuration"] or {}

    profile = {
        "job_description": "Mengelola reservasi pelanggan.",
        "responsibilities": [
            "Memeriksa ketersediaan kamar",
            "Mencatat permintaan pelanggan",
        ],
        "sop": [
            "Verifikasi tanggal menginap",
            "Konfirmasi ketersediaan sebelum memberi jawaban",
        ],
        "rules": [
            "Jangan menjanjikan kamar tanpa data ketersediaan",
        ],
        "success_criteria": [
            "Informasi reservasi akurat dan dapat diverifikasi",
        ],
    }

    updated = client.patch(
        f"/api/v1/companies/{company_id}/agents/{instance_id}",
        json=profile,
        headers=headers,
    )
    assert updated.status_code == 200, updated.text

    configuration = updated.json()["configuration"]

    for field, expected_value in profile.items():
        assert configuration[field] == expected_value

    # Konfigurasi lama yang bukan bagian dari profil tetap terjaga.
    for key, value in original_configuration.items():
        if key not in profile:
            assert configuration[key] == value

    # Pembaruan field lain tidak boleh menghapus profil.
    second_update = client.patch(
        f"/api/v1/companies/{company_id}/agents/{instance_id}",
        json={"instructions": "Instruksi tambahan perusahaan."},
        headers=headers,
    )
    assert second_update.status_code == 200, second_update.text

    final_body = second_update.json()
    assert final_body["instructions"] == "Instruksi tambahan perusahaan."

    for field, expected_value in profile.items():
        assert final_body["configuration"][field] == expected_value

    # List kosong dapat digunakan untuk menghapus isi suatu bagian profil.
    clear_response = client.patch(
        f"/api/v1/companies/{company_id}/agents/{instance_id}",
        json={"responsibilities": []},
        headers=headers,
    )
    assert clear_response.status_code == 200, clear_response.text
    assert clear_response.json()["configuration"]["responsibilities"] == []


def test_patch_instance_llm_configuration(client: TestClient):
    # 1. Buat perusahaan dan dapatkan autentikasi pemilik.
    company_id, user_id, headers = _create_company_with_owner(client)

    # 2. Cari template agen yang tersedia.
    catalog = client.get("/api/v1/agent-catalog")
    assert catalog.status_code == 200, catalog.text

    items = catalog.json()
    reservation = next(
        item for item in items if item["slug"] == "reservation"
    )

    # 3. Rekrut agen agar memiliki agent instance ID.
    hire = client.post(
        f"/api/v1/companies/{company_id}/agents/{reservation['id']}/hire",
        json={"name": "LLM Configuration Test AI"},
        headers=headers,
    )
    assert hire.status_code == 201, hire.text

    agent_id = hire.json()["id"]

    # 4. Atur konfigurasi LLM pada agen tersebut.
    llm_configuration = {
        "llm_provider": "openai",
        "llm_model": "gpt-4.1-mini",
        "llm_temperature": 0.1,
    }

    response = client.patch(
        f"/api/v1/companies/{company_id}/agents/{agent_id}",
        headers=headers,
        json=llm_configuration,
    )

    # 5. Pastikan API menerima dan menyimpan konfigurasi.
    assert response.status_code == 200, response.text

    configuration = response.json()["configuration"]

    assert configuration["llm_provider"] == "openai"
    assert configuration["llm_model"] == "gpt-4.1-mini"
    assert configuration["llm_temperature"] == 0.1


def test_patch_instance_rejects_unknown_llm_provider(
    client: TestClient,
):
    # 1. Buat perusahaan dan dapatkan autentikasi pemilik.
    company_id, user_id, headers = _create_company_with_owner(client)

    # 2. Cari template agen yang tersedia.
    catalog = client.get("/api/v1/agent-catalog")
    assert catalog.status_code == 200, catalog.text

    items = catalog.json()
    reservation = next(
        item for item in items if item["slug"] == "reservation"
    )

    # 3. Rekrut agen terlebih dahulu.
    hire = client.post(
        f"/api/v1/companies/{company_id}/agents/{reservation['id']}/hire",
        json={"name": "Invalid LLM Provider Test AI"},
        headers=headers,
    )
    assert hire.status_code == 201, hire.text

    agent_id = hire.json()["id"]

    # 4. Provider yang tidak didukung harus ditolak oleh validasi API.
    response = client.patch(
        f"/api/v1/companies/{company_id}/agents/{agent_id}",
        headers=headers,
        json={"llm_provider": "unknown-provider"},
    )

    assert response.status_code == 422, response.text
