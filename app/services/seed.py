from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import AgentCatalog, Permission, Role, Skill

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
    # Job 35 — finer UI / API gating
    "policy.read": "View company policy rules",
    "policy.manage": "Create and update policy rules",
    "integration.manage": "Manage company integrations",
    "governance.read": "View governance metrics and cost",
    "usage.read": "View plan and usage quotas",
}

# Role matrix (company users). Platform developer is NOT a company role.
ROLE_PERMISSIONS = {
    "owner": set(DEFAULT_PERMISSIONS),
    # Supervisor: approvals + workforce ops; no team/plan admin
    "manager": {
        "agent.read",
        "agent.hire",
        "agent.manage",
        "knowledge.read",
        "knowledge.write",
        "task.create",
        "task.read",
        "approval.read",
        "approval.manage",
        "audit.read",
        "governance.read",
        "policy.read",
    },
    # AI Administrator: configure AI workforce, skills, knowledge, policy, integrations
    "ai_admin": {
        "agent.read",
        "agent.hire",
        "agent.manage",
        "knowledge.read",
        "knowledge.write",
        "task.create",
        "task.read",
        "approval.read",
        "policy.read",
        "policy.manage",
        "integration.manage",
        "governance.read",
        "audit.read",
    },
    # Operational staff (e.g. reservation desk)
    "reservation": {
        "agent.read",
        "knowledge.read",
        "task.create",
        "task.read",
        "approval.read",
    },
    "member": {
        "agent.read",
        "knowledge.read",
        "task.create",
        "task.read",
    },
}

VALID_COMPANY_ROLES = frozenset(ROLE_PERMISSIONS.keys())


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

    seed_platform_skills(db)

    db.commit()


def _upsert_skill(db: Session, **kwargs) -> Skill:
    slug = kwargs["slug"]
    company_id = kwargs.get("company_id")
    q = select(Skill).where(Skill.slug == slug)
    if company_id is None:
        q = q.where(Skill.company_id.is_(None))
    else:
        q = q.where(Skill.company_id == company_id)
    existing = db.scalar(q)
    if existing:
        for k, v in kwargs.items():
            setattr(existing, k, v)
        db.flush()
        return existing
    skill = Skill(**kwargs)
    db.add(skill)
    db.flush()
    return skill


def seed_platform_skills(db: Session) -> None:
    """Platform-level skills referenced by Agent Catalog templates."""
    platform = [
        dict(
            slug="availability_check",
            name="Availability Check",
            description="Check product or room availability.",
            objective="Return accurate availability from company data.",
            instructions="Use only allowed tools and company knowledge. Never invent availability.",
            required_knowledge=["product_catalog"],
            allowed_tools=["search_availability"],
            workflow=["receive request", "query availability", "return result"],
            evaluation_criteria=["accuracy", "no invented data"],
        ),
        dict(
            slug="reservation_management",
            name="Reservation Management",
            description="Create and manage reservations.",
            objective="Manage reservations within policy.",
            instructions="Follow company reservation policy. Request approval for sensitive bookings.",
            required_knowledge=["product_catalog", "cancellation_policy"],
            allowed_tools=["create_reservation", "get_reservation", "search_availability"],
            workflow=["validate request", "check availability", "create or update", "confirm"],
            evaluation_criteria=["policy compliance", "data accuracy"],
        ),
        dict(
            slug="booking_support",
            name="Booking Support",
            description="Support booking and customer follow-up.",
            objective="Assist customers with booking status and follow-up.",
            instructions="Use reservation tools and knowledge. Escalate unusual cases.",
            required_knowledge=["cancellation_policy"],
            allowed_tools=["get_reservation"],
            workflow=["identify booking", "retrieve status", "respond"],
            evaluation_criteria=["clarity", "escalation quality"],
        ),
        dict(
            slug="quotation_preparation",
            name="Quotation Preparation",
            description="Prepare quotation drafts.",
            objective="Draft accurate quotations from pricing rules.",
            instructions="Never invent prices. Use company pricing knowledge.",
            required_knowledge=["pricing_rules", "product_catalog"],
            allowed_tools=["search_availability"],
            workflow=["gather requirements", "calculate", "draft quotation"],
            evaluation_criteria=["price accuracy", "completeness"],
        ),
        dict(
            slug="contract_analysis",
            name="Contract Analysis",
            description="Analyze contract content.",
            objective="Extract and summarize contract terms accurately.",
            instructions="Never invent contract clauses. Use extraction tools.",
            required_knowledge=["contract_templates", "legal_guidelines"],
            allowed_tools=["read_document", "extract_contract", "search_contract"],
            workflow=["locate contract", "extract terms", "summarize", "flag risks"],
            evaluation_criteria=["extraction accuracy", "risk identification"],
        ),
        dict(
            slug="contract_extraction",
            name="Contract Extraction",
            description="Extract structured fields from contracts.",
            objective="Produce structured contract fields from documents.",
            instructions="Use extract_contract tool. Report missing fields clearly.",
            required_knowledge=["contract_templates"],
            allowed_tools=["read_document", "extract_contract"],
            workflow=["load document", "extract fields", "validate"],
            evaluation_criteria=["field completeness", "accuracy"],
        ),
        dict(
            slug="contract_validation",
            name="Contract Validation",
            description="Validate contract data consistency.",
            objective="Validate extracted contract data against guidelines.",
            instructions="Do not approve invalid data. Escalate conflicts.",
            required_knowledge=["legal_guidelines"],
            allowed_tools=["search_contract", "extract_contract"],
            workflow=["load data", "validate rules", "report issues"],
            evaluation_criteria=["rule coverage", "escalation quality"],
        ),
    ]
    for item in platform:
        _upsert_skill(db, company_id=None, version="1.0.0", is_active=True, **item)
