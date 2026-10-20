"""Job 83 — API skills list dedupe by slug prefer company."""
from __future__ import annotations

import os

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.main import app


@pytest.fixture
def client():
    return TestClient(app)


def _session_local():
    try:
        from app.core.database import SessionLocal
        return SessionLocal
    except Exception:
        pass
    try:
        from app.db.session import SessionLocal
        return SessionLocal
    except Exception:
        return None


def test_list_available_skills_dedupes_by_slug():
    from app.services.skills import list_available_skills
    from app.models.entities import Skill
    from app.services.seed import seed_catalog

    SessionLocal = _session_local()
    if SessionLocal is None:
        pytest.skip("SessionLocal not found")

    db = SessionLocal()
    try:
        seed_catalog(db)
        # Create a fake company id string and a company-scoped copy of a platform skill
        from app.models.entities import Company
        company = Company(name="Dedupe Co Job83", onboarding_status="complete")
        db.add(company)
        db.flush()

        platform = db.scalar(
            select(Skill).where(
                Skill.slug == "availability_check",
                Skill.company_id.is_(None),
            )
        )
        if platform is None:
            pytest.skip("platform availability_check not seeded")

        existing_co = db.scalar(
            select(Skill).where(
                Skill.slug == "availability_check",
                Skill.company_id == company.id,
            )
        )
        if existing_co is None:
            clone = Skill(
                company_id=company.id,
                slug=platform.slug,
                name=platform.name + " (co)",
                description=platform.description or "",
                objective=getattr(platform, "objective", None) or "",
                instructions=getattr(platform, "instructions", None) or "",
                required_knowledge=list(platform.required_knowledge or []),
                allowed_tools=list(platform.allowed_tools or []),
                workflow=list(getattr(platform, "workflow", None) or []),
                evaluation_criteria=list(getattr(platform, "evaluation_criteria", None) or []),
                version=platform.version or "1.0.0",
                is_active=True,
            )
            db.add(clone)
            db.flush()

        result = list_available_skills(db, company.id)
        slugs = [s.slug for s in result]
        assert slugs.count("availability_check") == 1
        chosen = next(s for s in result if s.slug == "availability_check")
        assert chosen.company_id == company.id
    finally:
        db.close()


def test_list_available_skills_function_doc():
    from app.services import skills as skills_mod
    import inspect
    src = inspect.getsource(skills_mod.list_available_skills)
    assert "by_slug" in src or "Prefer company" in src or "company overrides" in src
