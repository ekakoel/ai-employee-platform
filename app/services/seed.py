from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import AgentCatalog, Permission, Role

DEFAULT_PERMISSIONS = {
    "agent.read": "View hired AI Employees",
    "agent.hire": "Hire an AI Employee from the catalog",
    "agent.manage": "Configure hired AI Employees",
    "knowledge.read": "Read company knowledge",
    "knowledge.write": "Create, update, and delete company knowledge",
    "task.create": "Create AI Employee tasks",
    "task.read": "Read AI Employee tasks",
    "approval.read": "View approval requests",
    "approval.manage": "Approve or reject approval requests",
    "audit.read": "Read company audit logs",
    "team.manage": "Manage company users",
}

ROLE_PERMISSIONS = {
    "owner": set(DEFAULT_PERMISSIONS),
    "manager": set(DEFAULT_PERMISSIONS),
    "member": {
        "agent.read",
        "knowledge.read",
        "task.create",
        "task.read",
    },
}


def get_or_create_role(db: Session, role_name: str) -> Role:
    role = db.scalar(select(Role).where(Role.name == role_name))

    permission_keys = ROLE_PERMISSIONS.get(role_name)
    if permission_keys is None:
        raise ValueError(f"Unknown role: {role_name}")

    if role is None:
        role = Role(
            name=role_name,
            description=f"Built-in {role_name} company role",
        )
        db.add(role)
        db.flush()

    permissions = []

    for key in permission_keys:
        permission = db.scalar(
            select(Permission).where(Permission.key == key)
        )

        if not permission:
            permission = Permission(
                key=key,
                description=DEFAULT_PERMISSIONS[key],
            )
            db.add(permission)
            db.flush()

        permissions.append(permission)

    role.permissions = permissions
    db.flush()

    return role


def _upsert_catalog(db: Session, **kwargs) -> AgentCatalog:
    slug = kwargs["slug"]
    existing = db.scalar(select(AgentCatalog).where(AgentCatalog.slug == slug))
    if existing:
        for key, value in kwargs.items():
            setattr(existing, key, value)
        db.flush()
        return existing

    catalog = AgentCatalog(**kwargs)
    db.add(catalog)
    db.flush()
    return catalog


def seed_catalog(db: Session) -> None:
    for role_name in ROLE_PERMISSIONS:
        get_or_create_role(db, role_name)

    now = datetime.now(timezone.utc)

    _upsert_catalog(
        db,
        slug="reservation",
        name="Reservation AI Employee",
        description=(
            "AI Employee untuk pekerjaan reservation, quotation, "
            "itinerary, dan follow-up pelanggan."
        ),
        role="reservation",
        skills=[
            "availability_check",
            "reservation_management",
            "booking_support",
            "quotation_preparation",
            "itinerary_planning",
            "customer_follow_up",
            "reporting",
        ],
        allowed_tools=[
            "search_availability",
            "create_reservation",
            "get_reservation",
        ],
        status="active",
        version="1.0.0",
        scope=[
            "reservation",
            "quotation",
            "itinerary",
            "customer_follow_up",
            "reservation_reporting",
        ],
        responsibilities=[
            "process inquiries",
            "prepare quotations",
            "prepare itineraries",
            "check reservation information",
            "follow up customers",
            "prepare reservation reports",
            "escalate unusual cases",
        ],
        default_instructions=(
            "You are Reservation AI.\n"
            "Your responsibility is reservation, quotation, itinerary, "
            "and customer follow-up within company policy.\n"
            "You must:\n"
            "- work only within your defined scope;\n"
            "- use only available company data and allowed tools;\n"
            "- never invent availability, prices, or bookings;\n"
            "- request approval before sensitive actions;\n"
            "- report uncertainty clearly."
        ),
        default_knowledge_requirements=[
            "product_catalog",
            "pricing_rules",
            "cancellation_policy",
        ],
        default_policies={
            "draft_quotation": "auto",
            "quotation_calculation": "auto",
            "send_quotation": "approval",
            "unusual_discount": "approval",
            "booking_confirmation": "approval",
            "generate_report": "auto",
            "unknown_action": "deny",
        },
        default_approval_recommendations={
            "send_quotation": "manager",
            "unusual_discount": "manager",
            "booking_confirmation": "supervisor",
        },
        default_autonomy="1",
        evaluation_criteria=[
            "quotation accuracy",
            "policy compliance",
            "approval adherence",
            "customer response quality",
        ],
        is_published=True,
        published_at=now,
        changelog="Initial Reservation AI template v1.0.0",
    )

    _upsert_catalog(
        db,
        slug="contract-manager",
        name="Contract Manager AI Employee",
        description=(
            "AI Employee untuk analisis dan pengelolaan contract "
            "sesuai skill yang ditetapkan platform."
        ),
        role="contract_manager",
        skills=[
            "contract_analysis",
            "contract_extraction",
            "contract_validation",
        ],
        allowed_tools=[
            "read_document",
            "extract_contract",
            "search_contract",
        ],
        status="active",
        version="1.0.0",
        scope=[
            "contract_analysis",
            "contract_extraction",
            "contract_validation",
            "contract_reporting",
        ],
        responsibilities=[
            "analyze contracts",
            "extract key terms",
            "validate contract data",
            "search existing contracts",
            "escalate unusual clauses",
        ],
        default_instructions=(
            "You are Contract Manager.\n"
            "Your responsibility is to analyze and manage company contracts.\n"
            "You must:\n"
            "- use only available company data;\n"
            "- use available tools;\n"
            "- never invent contract information;\n"
            "- request approval before sensitive actions;\n"
            "- report uncertainty clearly."
        ),
        default_knowledge_requirements=[
            "contract_templates",
            "legal_guidelines",
        ],
        default_policies={
            "search_contract": "auto",
            "extract_contract": "auto",
            "analyze_contract": "auto",
            "update_contract": "approval",
            "delete_contract": "approval",
            "unknown_action": "deny",
        },
        default_approval_recommendations={
            "update_contract": "manager",
            "delete_contract": "owner",
        },
        default_autonomy="1",
        evaluation_criteria=[
            "extraction accuracy",
            "policy compliance",
            "escalation quality",
        ],
        is_published=True,
        published_at=now,
        changelog="Initial Contract Manager AI template v1.0.0",
    )

    db.commit()
