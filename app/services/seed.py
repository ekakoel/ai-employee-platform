from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import AgentCatalog, Permission, Role

DEFAULT_PERMISSIONS = {
    "agent.read": "View hired AI Employees",
    "agent.hire": "Hire an AI Employee from the catalog",
    "knowledge.read": "Read company knowledge",
    "knowledge.write": "Create, update, and delete company knowledge",
    "task.create": "Create AI Employee tasks",
    "task.read": "Read AI Employee tasks",
    "audit.read": "Read company audit logs",
    "team.manage": "Manage company users",
}

ROLE_PERMISSIONS = {
    "owner": set(DEFAULT_PERMISSIONS),
    "manager": set(DEFAULT_PERMISSIONS),
    "member": {"agent.read", "knowledge.read", "task.create", "task.read"},
}


def get_or_create_role(db: Session, role_name: str) -> Role:
    role = db.scalar(select(Role).where(Role.name == role_name))
    if role:
        return role
    permission_keys = ROLE_PERMISSIONS.get(role_name)
    if permission_keys is None:
        raise ValueError(f"Unknown role: {role_name}")
    role = Role(name=role_name, description=f"Built-in {role_name} company role")
    db.add(role)
    db.flush()
    permissions = []
    for key in permission_keys:
        permission = db.scalar(select(Permission).where(Permission.key == key))
        if not permission:
            permission = Permission(key=key, description=DEFAULT_PERMISSIONS[key])
            db.add(permission)
            db.flush()
        permissions.append(permission)
    role.permissions = permissions
    db.flush()
    return role


def seed_catalog(db: Session) -> None:
    for role_name in ROLE_PERMISSIONS:
        get_or_create_role(db, role_name)

    existing = db.scalar(select(AgentCatalog).where(AgentCatalog.slug == "reservation"))
    if existing:
        db.commit()
        return

    db.add(
        AgentCatalog(
            slug="reservation",
            name="Reservation AI Employee",
            description="AI Employee untuk pekerjaan reservation dan booking sesuai skill yang ditetapkan platform.",
            role="reservation",
            skills=["availability_check", "reservation_management", "booking_support"],
            allowed_tools=["search_availability", "create_reservation", "get_reservation"],
        )
    )
    db.add(
        AgentCatalog(
            slug="contract-manager",
            name="Contract Manager AI Employee",
            description="AI Employee untuk analisis dan pengelolaan contract sesuai skill yang ditetapkan platform.",
            role="contract_manager",
            skills=["contract_analysis", "contract_extraction", "contract_validation"],
            allowed_tools=["read_document", "extract_contract", "search_contract"],
        )
    )
    db.commit()
