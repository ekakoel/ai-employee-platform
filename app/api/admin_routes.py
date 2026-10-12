"""Job 23 — Platform admin / support APIs (cross-tenant)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.database import get_db
from app.models.entities import AuditLog, Company, User
from app.services.audit import record_audit
from app.services.platform_admin import grant_platform_admin, require_platform_admin
from app.services.quotas import usage_summary

router = APIRouter(prefix="/api/v1/admin", tags=["admin"])

from pydantic import BaseModel, Field


class AdminCompanyCreate(BaseModel):
    name: str = Field(min_length=2, max_length=200)
    owner_name: str = Field(default="Owner", min_length=1, max_length=200)
    owner_email: str = Field(min_length=3, max_length=320)
    owner_password: str = Field(min_length=8, max_length=128)


class AdminCompanyUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=2, max_length=200)
    is_active: bool | None = None


@router.post("/companies", status_code=201)
def admin_create_company(
    payload: AdminCompanyCreate,
    db: Session = Depends(get_db),
    admin: User = Depends(require_platform_admin),
):
    """Platform developer provisions a company + owner account."""
    existing = db.scalar(select(Company).where(Company.name == payload.name))
    if existing:
        raise HTTPException(status_code=409, detail=f"Company '{payload.name}' already exists.")

    company = Company(name=payload.name)
    db.add(company)
    db.flush()
    try:
        from app.services.quotas import get_or_assign_plan
        get_or_assign_plan(db, company.id)
    except Exception:
        pass

    from app.services.seed import get_or_create_role
    from app.core.passwords import hash_password

    role = get_or_create_role(db, "owner")
    try:
        password_hash = hash_password(payload.owner_password)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    owner = User(
        company_id=company.id,
        name=payload.owner_name,
        email=payload.owner_email.strip().lower(),
        role_id=role.id,
        password_hash=password_hash,
    )
    db.add(owner)
    db.flush()

    record_audit(
        db,
        company_id=company.id,
        user_id=admin.id,
        action="admin.company.create",
        resource_type="company",
        resource_id=company.id,
        status="success",
        details={"owner_email": owner.email},
    )
    db.commit()
    db.refresh(company)
    db.refresh(owner)
    return {
        "company": {
            "id": company.id,
            "name": company.name,
            "is_active": bool(getattr(company, "is_active", True)),
        },
        "owner": {
            "id": owner.id,
            "email": owner.email,
            "name": owner.name,
            "role": "owner",
        },
        "message": "Company provisioned. Owner can sign in on /workspace with email + password.",
    }


@router.patch("/companies/{company_id}")
def admin_update_company(
    company_id: str,
    payload: AdminCompanyUpdate,
    db: Session = Depends(get_db),
    admin: User = Depends(require_platform_admin),
):
    company = db.get(Company, company_id)
    if not company:
        raise HTTPException(status_code=404, detail="Company not found")
    if payload.name is not None:
        company.name = payload.name
    if payload.is_active is not None:
        company.is_active = payload.is_active
    record_audit(
        db,
        company_id=company_id,
        user_id=admin.id,
        action="admin.company.update",
        resource_type="company",
        resource_id=company_id,
        status="success",
        details=payload.model_dump(exclude_none=True),
    )
    db.commit()
    return {
        "id": company.id,
        "name": company.name,
        "is_active": bool(getattr(company, "is_active", True)),
    }


@router.get("/companies/{company_id}/users")
def admin_list_company_users(
    company_id: str,
    db: Session = Depends(get_db),
    admin: User = Depends(require_platform_admin),
):
    company = db.get(Company, company_id)
    if not company:
        raise HTTPException(status_code=404, detail="Company not found")
    users = list(
        db.scalars(select(User).where(User.company_id == company_id).order_by(User.created_at.desc())).all()
    )
    out = []
    for u in users:
        role_name = u.role.name if u.role else None
        out.append(
            {
                "id": u.id,
                "name": u.name,
                "email": u.email,
                "role": role_name,
                "status": u.status,
                "is_platform_admin": bool(getattr(u, "is_platform_admin", False)),
            }
        )
    return {"company_id": company_id, "company_name": company.name, "users": out}


@router.get("/companies/{company_id}/agents")
def admin_list_company_agents(
    company_id: str,
    db: Session = Depends(get_db),
    admin: User = Depends(require_platform_admin),
):
    from app.models.entities import AgentInstance
    company = db.get(Company, company_id)
    if not company:
        raise HTTPException(status_code=404, detail="Company not found")
    agents = list(
        db.scalars(
            select(AgentInstance).where(AgentInstance.company_id == company_id)
        ).all()
    )
    return {
        "company_id": company_id,
        "agents": [
            {
                "id": a.id,
                "name": a.name,
                "status": a.status,
                "catalog_agent_id": a.catalog_agent_id,
            }
            for a in agents
        ],
    }




@router.get("/companies")
def admin_list_companies(
    db: Session = Depends(get_db),
    admin: User = Depends(require_platform_admin),
    limit: int = 100,
):
    companies = list(
        db.scalars(
            select(Company).order_by(Company.created_at.desc()).limit(min(limit, 500))
        ).all()
    )
    result = []
    for co in companies:
        user_count = db.scalar(
            select(func.count()).select_from(User).where(User.company_id == co.id)
        )
        result.append(
            {
                "id": co.id,
                "name": co.name,
                "is_active": bool(getattr(co, "is_active", True)),
                "created_at": co.created_at.isoformat() if co.created_at else None,
                "user_count": int(user_count or 0),
            }
        )
    return result


@router.post("/companies/{company_id}/disable")
def admin_disable_company(
    company_id: str,
    db: Session = Depends(get_db),
    admin: User = Depends(require_platform_admin),
):
    company = db.get(Company, company_id)
    if not company:
        raise HTTPException(status_code=404, detail="Company not found")
    company.is_active = False
    record_audit(
        db,
        company_id=company_id,
        user_id=admin.id,
        action="admin.company.disable",
        resource_type="company",
        resource_id=company_id,
        status="success",
    )
    db.commit()
    return {"id": company.id, "is_active": False}


@router.post("/companies/{company_id}/enable")
def admin_enable_company(
    company_id: str,
    db: Session = Depends(get_db),
    admin: User = Depends(require_platform_admin),
):
    company = db.get(Company, company_id)
    if not company:
        raise HTTPException(status_code=404, detail="Company not found")
    company.is_active = True
    record_audit(
        db,
        company_id=company_id,
        user_id=admin.id,
        action="admin.company.enable",
        resource_type="company",
        resource_id=company_id,
        status="success",
    )
    db.commit()
    return {"id": company.id, "is_active": True}


@router.get("/companies/{company_id}/audit")
def admin_company_audit(
    company_id: str,
    db: Session = Depends(get_db),
    admin: User = Depends(require_platform_admin),
    limit: int = 100,
):
    """Cross-tenant audit view — platform admin only."""
    company = db.get(Company, company_id)
    if not company:
        raise HTTPException(status_code=404, detail="Company not found")
    rows = list(
        db.scalars(
            select(AuditLog)
            .where(AuditLog.company_id == company_id)
            .order_by(AuditLog.created_at.desc())
            .limit(min(limit, 500))
        ).all()
    )
    return [
        {
            "id": r.id,
            "action": r.action,
            "status": r.status,
            "resource_type": r.resource_type,
            "resource_id": r.resource_id,
            "user_id": r.user_id,
            "created_at": r.created_at.isoformat() if r.created_at else None,
        }
        for r in rows
    ]


@router.get("/companies/{company_id}/usage")
def admin_company_usage(
    company_id: str,
    db: Session = Depends(get_db),
    admin: User = Depends(require_platform_admin),
):
    company = db.get(Company, company_id)
    if not company:
        raise HTTPException(status_code=404, detail="Company not found")
    summary = usage_summary(db, company_id)
    db.commit()
    return summary


@router.post("/users/{user_id}/grant-platform-admin")
def admin_grant_platform_admin(
    user_id: str,
    db: Session = Depends(get_db),
    admin: User = Depends(require_platform_admin),
):
    try:
        user = grant_platform_admin(db, user_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    record_audit(
        db,
        company_id=user.company_id,
        user_id=admin.id,
        action="admin.grant_platform_admin",
        resource_type="user",
        resource_id=user.id,
        status="success",
    )
    db.commit()
    return {
        "id": user.id,
        "email": user.email,
        "is_platform_admin": user.is_platform_admin,
    }


@router.post("/impersonate")
def admin_impersonate(
    payload: dict,
    db: Session = Depends(get_db),
    admin: User = Depends(require_platform_admin),
):
    """
    Support impersonation — DISABLED by default (ALLOW_IMPERSONATION=false).
    When enabled, returns target user id for session bootstrap only.
    """
    if not settings.allow_impersonation:
        raise HTTPException(
            status_code=403,
            detail="Impersonation is disabled (set ALLOW_IMPERSONATION=true to enable)",
        )
    target_id = str(payload.get("user_id") or "").strip()
    if not target_id:
        raise HTTPException(status_code=400, detail="user_id required")
    target = db.get(User, target_id)
    if not target:
        raise HTTPException(status_code=404, detail="Target user not found")
    record_audit(
        db,
        company_id=target.company_id,
        user_id=admin.id,
        action="admin.impersonate",
        resource_type="user",
        resource_id=target.id,
        status="success",
        details={"target_email": target.email},
    )
    db.commit()
    return {
        "impersonating": True,
        "user_id": target.id,
        "company_id": target.company_id,
        "email": target.email,
        "warning": "Support session — audit logged",
    }
