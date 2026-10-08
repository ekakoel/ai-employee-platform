"""Job 30 — Marketplace read-model: public templates + install (copy) into company."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.entities import AgentCatalog, MarketplaceInstallation, Skill
from app.services.audit import record_audit


def list_public_templates(db: Session) -> list[AgentCatalog]:
    """Published platform agent templates (marketplace catalog)."""
    return list(
        db.scalars(
            select(AgentCatalog).where(
                AgentCatalog.status == "active",
                AgentCatalog.is_published.is_(True),
            ).order_by(AgentCatalog.name)
        ).all()
    )


def get_public_template(db: Session, catalog_id: str) -> AgentCatalog | None:
    catalog = db.get(AgentCatalog, catalog_id)
    if not catalog or catalog.status != "active" or not catalog.is_published:
        return None
    return catalog


def _copy_skill_to_company(
    db: Session,
    *,
    company_id: str,
    platform_skill: Skill,
) -> Skill:
    """Ensure a company-scoped copy of a platform skill exists; return it."""
    existing = db.scalar(
        select(Skill).where(
            Skill.company_id == company_id,
            Skill.slug == platform_skill.slug,
            Skill.is_active.is_(True),
        )
    )
    if existing:
        return existing

    company_skill = Skill(
        company_id=company_id,
        slug=platform_skill.slug,
        name=platform_skill.name,
        description=platform_skill.description or "",
        objective=platform_skill.objective or "",
        instructions=platform_skill.instructions or "",
        required_knowledge=list(platform_skill.required_knowledge or []),
        allowed_tools=list(platform_skill.allowed_tools or []),
        workflow=list(platform_skill.workflow or []),
        evaluation_criteria=list(platform_skill.evaluation_criteria or []),
        version=platform_skill.version or "1.0.0",
        is_active=True,
    )
    db.add(company_skill)
    db.flush()
    return company_skill


def install_template(
    db: Session,
    *,
    company_id: str,
    catalog_id: str,
    user_id: str | None,
) -> MarketplaceInstallation:
    """
    Install a published platform template into a company.

    Copies each platform skill referenced by the template into company-scoped
    skills (idempotent per slug). Records MarketplaceInstallation.
    Re-install of same catalog for company is rejected (unique constraint).
    """
    catalog = get_public_template(db, catalog_id)
    if not catalog:
        raise ValueError("Template not found or not published")

    existing_install = db.scalar(
        select(MarketplaceInstallation).where(
            MarketplaceInstallation.company_id == company_id,
            MarketplaceInstallation.catalog_agent_id == catalog_id,
        )
    )
    if existing_install:
        raise ValueError("Template already installed for this company")

    skill_keys = list(catalog.skills or [])
    installed_ids: list[str] = []

    for key in skill_keys:
        platform_skill = db.scalar(
            select(Skill).where(
                Skill.slug == key,
                Skill.company_id.is_(None),
                Skill.is_active.is_(True),
            )
        )
        if not platform_skill:
            # Template may reference a skill not yet seeded; skip silently
            continue
        company_skill = _copy_skill_to_company(
            db, company_id=company_id, platform_skill=platform_skill
        )
        installed_ids.append(company_skill.id)

    installation = MarketplaceInstallation(
        company_id=company_id,
        catalog_agent_id=catalog.id,
        installed_by_user_id=user_id,
        installed_skill_ids=installed_ids,
        template_version=catalog.version or "1.0.0",
        catalog_slug=catalog.slug,
        catalog_name=catalog.name,
    )
    db.add(installation)
    db.flush()

    record_audit(
        db,
        company_id=company_id,
        user_id=user_id,
        agent_instance_id=None,
        action="marketplace.install",
        resource_type="marketplace_installation",
        resource_id=installation.id,
        status="success",
        details={
            "catalog_slug": catalog.slug,
            "catalog_id": catalog.id,
            "template_version": catalog.version,
            "skill_count": len(installed_ids),
            "installed_skill_ids": installed_ids,
        },
    )
    return installation


def list_installations(
    db: Session, *, company_id: str
) -> list[MarketplaceInstallation]:
    return list(
        db.scalars(
            select(MarketplaceInstallation)
            .where(MarketplaceInstallation.company_id == company_id)
            .order_by(MarketplaceInstallation.installed_at.desc())
        ).all()
    )
