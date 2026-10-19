"""Job 60 — local debug demo bootstrap (not for production)."""

from __future__ import annotations

import uuid

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.passwords import hash_password
from app.models.entities import Company, EmailClaim, User
from app.services.access import grant_operational_access_for_agent
from app.services.audit import record_audit
from app.services.seed import get_or_create_role


DEMO_PASSWORD = "demo12345"

PERSONAS = [
    ("owner", "owner@demo.local", "Demo Owner"),
    ("ai_admin", "aiadmin@demo.local", "AI Admin"),
    ("reservation", "reservation@demo.local", "Reservation"),
    ("manager", "manager@demo.local", "Manager"),
    ("contract_manager", "contracts@demo.local", "Contract Manager"),
    ("administration", "admin@demo.local", "Administration"),
]


def require_debug_bootstrap() -> None:
    """Allow in local/dev/test. Block only in production-like environments."""
    env = (getattr(settings, "app_env", None) or "").strip().lower()
    if settings.debug or env in {"development", "dev", "test", "local"}:
        return
    raise HTTPException(
        status_code=403,
        detail=(
            "Demo bootstrap is only available when DEBUG=true "
            "or APP_ENV=development/test (not production)."
        ),
    )


def bootstrap_demo_workspace(db: Session, *, hire_agents: bool = True) -> dict:
    """Create a ready-to-use demo company + verified owner personas.

    Returns credentials for immediate /auth/login (email + password).
    """
    require_debug_bootstrap()
    suffix = uuid.uuid4().hex[:8]
    company_name = f"Demo Co {suffix}"

    company = Company(
        name=company_name,
        onboarding_status="complete",
        contact_email="owner@demo.local",
        industry="travel",
    )
    db.add(company)
    db.flush()

    try:
        from app.services.quotas import get_or_assign_plan
        get_or_assign_plan(db, company.id)
    except Exception:
        pass

    users_out: list[dict] = []
    owner = None
    password_hash = hash_password(DEMO_PASSWORD)

    for role_name, email, name in PERSONAS:
        # Unique email per bootstrap run to avoid claim conflicts
        local, _, domain = email.partition("@")
        unique_email = f"{local}+{suffix}@{domain}" if domain else f"{email}+{suffix}"
        # Prefer stable owner@demo.local when free; else unique
        preferred = email
        claim_email = preferred
        existing_claim = db.get(EmailClaim, preferred)
        if existing_claim is not None:
            claim_email = unique_email

        role = get_or_create_role(db, role_name)
        if db.get(EmailClaim, claim_email) is None:
            db.add(EmailClaim(email=claim_email))

        user = User(
            company_id=company.id,
            name=name,
            email=claim_email,
            role_id=role.id,
            password_hash=password_hash,
            email_verified=True,
            status="active",
        )
        db.add(user)
        db.flush()
        users_out.append(
            {
                "id": user.id,
                "email": claim_email,
                "role": role_name,
                "name": name,
            }
        )
        if role_name == "owner":
            owner = user

    if owner is None:
        raise HTTPException(status_code=500, detail="Owner persona missing")

    company.owner_user_id = owner.id
    db.flush()

    hired: list[dict] = []
    if hire_agents:
        try:
            from app.models.entities import AgentCatalog, AgentInstance, AgentSubscription
             
            from sqlalchemy import select

            catalog_items = list(
                db.scalars(
                    select(AgentCatalog).where(
                        AgentCatalog.status == "active",
                        AgentCatalog.is_published.is_(True),
                    ).limit(2)
                ).all()
            )
            for catalog in catalog_items:
                subscription = AgentSubscription(
                    company_id=company.id,
                    catalog_agent_id=catalog.id,
                )
                db.add(subscription)
                db.flush()
                instance = AgentInstance(
                    company_id=company.id,
                    catalog_agent_id=catalog.id,
                    subscription_id=subscription.id,
                    name=(catalog.name or "Agent").replace(" AI Employee", "") + " (Demo)",
                    template_version=catalog.version,
                    instructions=catalog.default_instructions or "",
                    skills=list(catalog.skills or []),
                    allowed_tools=list(catalog.allowed_tools or []),
                    scope=list(catalog.scope or []),
                    autonomy=catalog.default_autonomy or "1",
                    policies=dict(catalog.default_policies or {}),
                    configuration={
                        "role": catalog.role,
                        "skills": list(catalog.skills or []),
                        "allowed_tools": list(catalog.allowed_tools or []),
                    },
                    supervisor_user_id=owner.id,
                    status="active",
                )
                db.add(instance)
                db.flush()
                try:
                    grant_operational_access_for_agent(
                        db, company_id=company.id, agent_instance_id=instance.id
                    )
                except Exception:
                    pass
                hired.append({"id": instance.id, "name": instance.name, "slug": catalog.slug})
        except Exception as exc:
            hired.append({"error": str(exc)})

    record_audit(
        db,
        company_id=company.id,
        user_id=owner.id,
        action="demo.bootstrap",
        resource_type="company",
        resource_id=company.id,
        status="success",
        details={"personas": len(users_out), "agents": len(hired)},
    )
    db.commit()

    return {
        "company_id": company.id,
        "company_name": company.name,
        "password": DEMO_PASSWORD,
        "owner_email": owner.email,
        "owner_user_id": owner.id,
        "users": users_out,
        "agents": hired,
        "message": "Demo workspace ready. Sign in with owner email + password demo12345.",
    }
