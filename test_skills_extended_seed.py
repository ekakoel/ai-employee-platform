"""Extended platform skill seed — regression checks (Job 75)."""

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from app.core.database import Base
from app.services.seed import seed_catalog, seed_demo_company_skills
from app.models.entities import Skill, Company


engine = create_engine(
    "sqlite:///./test_skills_extended.db",
    connect_args={"check_same_thread": False},
)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


@pytest.fixture()
def db():
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    with SessionLocal() as session:
        seed_catalog(session)
        yield session


EXPECTED_PLATFORM_SLUGS = {
    "availability_check",
    "reservation_management",
    "booking_support",
    "quotation_preparation",
    "customer_follow_up",
    "invoice_draft_preparation",
    "expense_anomaly_detection",
    "lead_qualification",
    "faq_response",
    "contract_analysis",
    "contract_extraction",
    "contract_validation",
}


def test_platform_skills_extended_seeded(db):
    rows = list(db.scalars(select(Skill).where(Skill.company_id.is_(None))).all())
    slugs = {s.slug for s in rows}
    missing = EXPECTED_PLATFORM_SLUGS - slugs
    assert not missing, f"Missing platform skills: {missing}"
    assert len(rows) >= 12


def test_quotation_preparation_uses_draft_quotation_tool(db):
    skill = db.scalar(
        select(Skill).where(
            Skill.slug == "quotation_preparation",
            Skill.company_id.is_(None),
        )
    )
    assert skill is not None
    assert "draft_quotation" in (skill.allowed_tools or [])


def test_customer_follow_up_present(db):
    skill = db.scalar(
        select(Skill).where(
            Skill.slug == "customer_follow_up",
            Skill.company_id.is_(None),
        )
    )
    assert skill is not None
    assert skill.is_active is True
    assert "get_reservation" in (skill.allowed_tools or [])


def test_demo_company_skill_hotel_upsell(db):
    co = Company(name="Demo Upsell Co")
    db.add(co)
    db.flush()
    skills = seed_demo_company_skills(db, company_id=co.id)
    db.commit()
    assert any(s.slug == "hotel_upsell_package" for s in skills)
    assert all(s.company_id == co.id for s in skills)
    # platform skill must remain unscoped
    platform = db.scalar(
        select(Skill).where(
            Skill.slug == "availability_check",
            Skill.company_id.is_(None),
        )
    )
    assert platform is not None
