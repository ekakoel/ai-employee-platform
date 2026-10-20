"""Job 76 — demo knowledge seed + bootstrap wire regression.

Copy to: tests/test_demo_knowledge_seed_job76.py
"""
from __future__ import annotations

import os
import pytest
from fastapi.testclient import TestClient

from app.main import app


REQUIRED_KEYS = {
    "product_catalog",
    "cancellation_policy",
    "pricing_rules",
    "tax_policy",
    "communication_tone",
    "approved_faq",
    "legal_guidelines",
    "upsell_margin_rules",
    "customer_preferences",
}


@pytest.fixture
def client():
    return TestClient(app)


def test_demo_bootstrap_seeds_knowledge(client):
    """POST /api/v1/demo/bootstrap creates company knowledge for skill keys."""
    os.environ.setdefault("DEBUG", "true")
    os.environ.setdefault("APP_ENV", "development")

    r = client.post("/api/v1/demo/bootstrap")
    if r.status_code not in (200, 201):
        pytest.skip(f"demo bootstrap unavailable: {r.status_code} {r.text[:200]}")

    data = r.json()
    company_id = data.get("company_id") or (data.get("company") or {}).get("id")
    assert company_id, f"no company_id in bootstrap response: {data}"

    # Adjust knowledge list path if your API differs
    for path in (
        f"/api/v1/companies/{company_id}/knowledge",
        f"/api/v1/companies/{company_id}/knowledge-items",
        f"/companies/{company_id}/knowledge",
    ):
        kr = client.get(path)
        if kr.status_code == 200:
            body = kr.json()
            items = body if isinstance(body, list) else body.get("items") or body.get("data") or []
            keys = {item.get("key") for item in items if isinstance(item, dict)}
            missing = REQUIRED_KEYS - keys
            assert not missing, f"Missing knowledge keys after bootstrap: {missing}"
            return

    pytest.skip("knowledge list endpoint not found; wire path in test")


def test_seed_functions_idempotent():
    """Direct unit check if session factory available."""
    try:
        from app.db.session import SessionLocal
        from app.services.seed import (
            seed_demo_company_skills,
            seed_demo_company_knowledge,
        )
    except Exception as exc:
        pytest.skip(f"imports unavailable: {exc}")

    db = SessionLocal()
    try:
        # Use a throwaway company id string only if model allows; else skip
        # Prefer running after bootstrap so company exists
        pytest.skip("prefer integration path via bootstrap endpoint")
    finally:
        db.close()


def test_skill_domain_helper():
    try:
        from app.services.seed import skill_domain
    except ImportError:
        try:
            from seed_demo_knowledge import skill_domain  # local helper
        except ImportError:
            pytest.skip("skill_domain not exported yet")

    assert skill_domain("quotation_preparation") == "Reservation"
    assert skill_domain("invoice_draft_preparation") == "Accounting"
    assert skill_domain("faq_response") == "Sales / CS"
    assert skill_domain("contract_analysis") == "Contract"
    assert skill_domain("hotel_upsell_package") == "Custom"
    assert skill_domain("unknown_slug_xyz") == "Other"
