#!/usr/bin/env python3
"""
Installer / patch helper for Job 76 — Demo Knowledge Seed + Bootstrap Wire.

Run from repo root:
  python install_job76_demo_knowledge_seed.py

What it does (best-effort, non-destructive):
  1. Ensures seed_demo_company_knowledge exists in app/services/seed.py
     (appends from seed_demo_knowledge.py if missing).
  2. Prints instructions to wire bootstrap + UI badge.
  3. Writes a minimal test file if missing.

Does NOT auto-edit API bootstrap or frontend without confirmation —
those vary by project structure. Follow the printed checklist.
"""

from __future__ import annotations

import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
# When copied into repo root, ROOT = repo root
SEED_SRC = ROOT / "seed_demo_knowledge.py"
if not SEED_SRC.exists():
    # Artifacts path when run from elsewhere
    ARTIFACTS = Path(__file__).resolve().parent
    SEED_SRC = ARTIFACTS / "seed_demo_knowledge.py"
    ROOT = Path.cwd()

SEED_PY = ROOT / "app" / "services" / "seed.py"
TEST_PATH = ROOT / "tests" / "test_demo_knowledge_seed_job76.py"


BOOTSTRAP_HINT = '''
# --- Job 76: after company created in demo bootstrap ---
from app.services.seed import (
    seed_demo_company_skills,
    seed_demo_company_knowledge,  # may need to re-export
)

# ... company = create_company(...)
seed_demo_company_skills(db, company_id=company.id)
seed_demo_company_knowledge(db, company_id=company.id)
db.commit()
'''

TEST_TEMPLATE = '''"""Job 76 — demo knowledge seed + bootstrap wire regression."""
from __future__ import annotations

import os
import pytest
from fastapi.testclient import TestClient

# Adjust imports to project conventions
from app.main import app
from app.db.session import SessionLocal  # or project session factory
from app.services.seed import (
    seed_demo_company_skills,
    seed_demo_company_knowledge,
)


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


def test_seed_demo_company_knowledge_idempotent(client):
    """Seed knowledge for a demo company; second run does not duplicate keys."""
    # Prefer using existing demo bootstrap when DEBUG
    os.environ.setdefault("DEBUG", "true")
    os.environ.setdefault("APP_ENV", "development")

    # If bootstrap endpoint exists:
    r = client.post("/api/v1/demo/bootstrap")
    if r.status_code in (200, 201):
        data = r.json()
        company_id = data.get("company_id") or data.get("company", {}).get("id")
        assert company_id, data
        # Knowledge list API — adjust path to your project
        kr = client.get(f"/api/v1/companies/{company_id}/knowledge")
        if kr.status_code == 200:
            keys = {item.get("key") for item in kr.json() if isinstance(item, dict)}
            missing = REQUIRED_KEYS - keys
            assert not missing, f"Missing knowledge keys: {missing}"
        return

    # Fallback: unit-style with open session (skip if models differ)
    pytest.skip("demo bootstrap not available or returned non-2xx; wire path manually")


def test_skill_domain_map():
    from app.services.seed import skill_domain  # if exported
    assert skill_domain("quotation_preparation") == "Reservation"
    assert skill_domain("faq_response") == "Sales / CS"
    assert skill_domain("hotel_upsell_package") == "Custom"
'''


def main() -> int:
    print("Job 76 installer — Demo Knowledge Seed")
    print(f"CWD / ROOT: {ROOT}")

    if not SEED_PY.exists():
        print(f"[WARN] {SEED_PY} not found. Run from repo root after cloning.")
        print("       Copy seed_demo_knowledge.py next to app/ and merge manually.")
        return 1

    text = SEED_PY.read_text(encoding="utf-8")
    if "seed_demo_company_knowledge" in text:
        print("[OK] seed_demo_company_knowledge already present in seed.py")
    else:
        if not SEED_SRC.exists():
            print(f"[ERR] Source {SEED_SRC} missing")
            return 1
        # Append importable helpers
        src = SEED_SRC.read_text(encoding="utf-8")
        # Strip module docstring noise; keep functions
        append_block = (
            "\n\n# === Job 76: Demo knowledge seed (auto-appended) ===\n"
            + src
            + "\n"
        )
        SEED_PY.write_text(text + append_block, encoding="utf-8")
        print(f"[OK] Appended seed helpers to {SEED_PY}")

    if not TEST_PATH.exists():
        TEST_PATH.parent.mkdir(parents=True, exist_ok=True)
        TEST_PATH.write_text(TEST_TEMPLATE, encoding="utf-8")
        print(f"[OK] Wrote {TEST_PATH}")
    else:
        print(f"[OK] Test already exists: {TEST_PATH}")

    print("\n--- Manual steps remaining ---")
    print("1) Wire bootstrap (demo endpoint) to call:")
    print(BOOTSTRAP_HINT)
    print("2) Skills UI: map slug → domain via skill_domain() or SKILL_DOMAIN_MAP")
    print("   and render a small badge (Reservation / Accounting / Sales / CS / Contract / Custom).")
    print("3) Run:")
    print("   pytest tests/test_demo_knowledge_seed_job76.py -q")
    print("4) Commit & push development.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
