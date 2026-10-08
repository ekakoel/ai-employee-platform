"""Job 23 — Platform admin / support APIs (cross-tenant)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Header, HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.database import get_db
from app.models.entities import AuditLog, Company, User
from app.services.audit import record_audit
from app.services.platform_admin import grant_platform_admin, require_platform_admin
from app.services.quotas import usage_summary

router = APIRouter(prefix="/api/v1/admin", tags=["admin"])


@router.get("/companies")
def admin_list_companies(
    db: Session = Depends(get_db),
    x_user_id: str | None = Header(default=None),
    limit: int = 100,
):
    require_platform_admin(db, x_user_id)
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
    x_user_id: str | None = Header(default=None),
):
    admin = require_platform_admin(db, x_user_id)
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
    x_user_id: str | None = Header(default=None),
):
    admin = require_platform_admin(db, x_user_id)
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
    x_user_id: str | None = Header(default=None),
    limit: int = 100,
):
    """Cross-tenant audit view — platform admin only."""
    require_platform_admin(db, x_user_id)
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
    x_user_id: str | None = Header(default=None),
):
    require_platform_admin(db, x_user_id)
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
    x_user_id: str | None = Header(default=None),
):
    admin = require_platform_admin(db, x_user_id)
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
    x_user_id: str | None = Header(default=None),
):
    """
    Support impersonation — DISABLED by default (ALLOW_IMPERSONATION=false).
    When enabled, returns target user id for session bootstrap only.
    """
    admin = require_platform_admin(db, x_user_id)
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
