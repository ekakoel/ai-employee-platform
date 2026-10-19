"""Authenticated company profile, invitation, and administrator controls."""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.core.auth import get_current_user
from app.core.database import get_db
from app.models.entities import Company, CompanyInvitation, User
from app.services import auth_sessions, company_onboarding
from app.services.audit import record_audit
from app.services.seed import get_or_create_role

router = APIRouter(prefix="/api/v1/companies", tags=["company-onboarding"])


def own_company(db: Session, user: User, company_id: str) -> Company:
    if user.company_id != company_id:
        raise HTTPException(status_code=403, detail="Company access denied")
    company = db.get(Company, company_id)
    if not company or not company.is_active:
        raise HTTPException(status_code=404, detail="Company not found")
    return company


def owner_only(company: Company, user: User):
    if company.owner_user_id != user.id or user.role.name != "owner":
        raise HTTPException(status_code=403, detail="Company owner required")


@router.get("/{company_id}/profile")
def profile(company_id: str, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    company = own_company(db, user, company_id)
    return {"id": company.id, "name": company.name, "contact_email": company.contact_email,
            "industry": company.industry, "onboarding_status": company.onboarding_status,
            "owner_user_id": company.owner_user_id}


class ProfileUpdate(BaseModel):
    name: str = Field(min_length=2, max_length=200)
    contact_email: str = Field(min_length=3, max_length=320)
    industry: str = Field(min_length=2, max_length=120)


@router.put("/{company_id}/profile")
def update_profile(company_id: str, payload: ProfileUpdate, db: Session = Depends(get_db),
                   user: User = Depends(get_current_user)):
    company = own_company(db, user, company_id)
    owner_only(company, user)
    company.name = payload.name.strip()
    company.contact_email = company_onboarding.normalized_email(payload.contact_email)
    company.industry = payload.industry.strip()
    if not company.name or not company.industry:
        raise HTTPException(status_code=400, detail="Company name and industry are required")
    company.onboarding_status = "complete"
    company.profile_completed_at = auth_sessions.now()
    record_audit(db, company_id=company.id, user_id=user.id, action="company.profile.complete",
                 resource_type="company", resource_id=company.id, status="success")
    try:
        db.commit()
    except Exception:
        db.rollback()
        raise HTTPException(status_code=409, detail="Company profile could not be updated") from None
    return profile(company_id, db, user)


class InviteRequest(BaseModel):
    email: str = Field(min_length=3, max_length=320)
    role_name: str = Field(default="member", min_length=2, max_length=100)


@router.post("/{company_id}/invitations", status_code=201)
def invite(company_id: str, payload: InviteRequest, db: Session = Depends(get_db),
           user: User = Depends(get_current_user)):
    company = own_company(db, user, company_id)
    owner_only(company, user)
    try:
        return company_onboarding.invite(db, user, payload.email, role_name=payload.role_name)
    except auth_sessions.AuthError as exc:
        raise HTTPException(status_code=exc.status, detail=str(exc)) from None


@router.get("/{company_id}/job-roles")
def list_job_roles(company_id: str, db: Session = Depends(get_db),
                   user: User = Depends(get_current_user)):
    """Company job positions available for invites and role assignment."""
    own_company(db, user, company_id)
    from app.services.seed import ROLE_PERMISSIONS
    labels = {
        "member": "Member (general employee)",
        "reservation": "Reservation",
        "manager": "Manager / Supervisor",
        "ai_admin": "AI Administrator",
        "contract_manager": "Contract Manager",
        "administration": "Administration",
        "accounting": "Accounting",
    }
    roles = []
    for name in sorted(ROLE_PERMISSIONS.keys()):
        if name == "owner":
            continue
        roles.append({
            "name": name,
            "label": labels.get(name, name.replace("_", " ").title()),
            "is_administrator": name == "ai_admin",
        })
    return {"roles": roles}


class JobRoleUpdate(BaseModel):
    role_name: str = Field(min_length=2, max_length=100)


@router.put("/{company_id}/users/{target_id}/role")
def update_job_role(company_id: str, target_id: str, payload: JobRoleUpdate,
                    db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    company = own_company(db, user, company_id)
    owner_only(company, user)
    try:
        return company_onboarding.set_job_role(db, user, target_id, payload.role_name)
    except auth_sessions.AuthError as exc:
        raise HTTPException(status_code=exc.status, detail=str(exc)) from None


@router.get("/{company_id}/invitations")
def list_invitations(company_id: str, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    company = own_company(db, user, company_id)
    owner_only(company, user)
    rows = db.scalars(select(CompanyInvitation).where(CompanyInvitation.company_id == company_id)
                      .order_by(CompanyInvitation.created_at.desc()).limit(100)).all()
    return [{"id": row.id, "email": row.email, "status": "revoked" if row.revoked_at else
             "accepted" if row.consumed_at else "expired" if auth_sessions.utc(row.expires_at) <= auth_sessions.now()
             else "pending", "role_name": row.role_name, "expires_at": row.expires_at.isoformat()} for row in rows]


@router.post("/{company_id}/invitations/{invitation_id}/revoke", status_code=204)
def revoke_invitation(company_id: str, invitation_id: str, db: Session = Depends(get_db),
                      user: User = Depends(get_current_user)):
    company = own_company(db, user, company_id)
    owner_only(company, user)
    result = db.execute(update(CompanyInvitation).where(CompanyInvitation.id == invitation_id,
        CompanyInvitation.company_id == company_id, CompanyInvitation.consumed_at.is_(None),
        CompanyInvitation.revoked_at.is_(None)).values(revoked_at=auth_sessions.now()))
    if result.rowcount != 1:
        raise HTTPException(status_code=404, detail="Pending invitation not found")
    record_audit(db, company_id=company_id, user_id=user.id, action="company.invitation.revoke",
                 resource_type="company_invitation", resource_id=invitation_id, status="success")
    db.commit()


class AdministratorUpdate(BaseModel):
    administrator: bool


@router.put("/{company_id}/administrators/{target_id}")
def set_administrator(company_id: str, target_id: str, payload: AdministratorUpdate,
                      db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    company = own_company(db, user, company_id)
    owner_only(company, user)
    target = db.scalar(select(User).where(User.id == target_id, User.company_id == company_id))
    if not target or target.status != "active" or not target.email_verified:
        raise HTTPException(status_code=404, detail="Active employee not found")
    if target.id == company.owner_user_id or target.role.name == "owner":
        raise HTTPException(status_code=403, detail="Owner role cannot be changed here")
    role_name = "ai_admin" if payload.administrator else "member"
    target.role_id = get_or_create_role(db, role_name).id
    target.auth_version += 1
    auth_sessions.revoke_all(db, target, "role_change")
    record_audit(db, company_id=company_id, user_id=user.id, action="company.administrator.update",
                 resource_type="user", resource_id=target.id, status="success",
                 details={"administrator": payload.administrator})
    db.commit()
    return {"user_id": target.id, "role": role_name}
