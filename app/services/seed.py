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
        "team.manage",  # invite/manage employees (not owner privileges)
    },
    # Operational staff (e.g. reservation desk)
    "reservation": {
        "agent.read",
        "knowledge.read",
        "task.create",
        "task.read",
        "approval.read",
    },
    # Administration — company back-office, users, usage (not AI catalog developer)
    "administration": {
        "agent.read",
        "knowledge.read",
        "task.read",
        "approval.read",
        "team.manage",
        "usage.read",
        "audit.read",
        "governance.read",
    },
    # Contract manager — upload/read contracts & knowledge; operational tasks
    "contract_manager": {
        "agent.read",
        "knowledge.read",
        "knowledge.write",
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
    # Accounting — finance-oriented read of tasks/knowledge/governance
    "accounting": {
        "agent.read",
        "knowledge.read",
        "task.read",
        "approval.read",
        "governance.read",
        "usage.read",
        "audit.read",
    },
}

# Platform developer is NOT listed here — uses is_platform_admin + /developer console.

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
    platform: list[dict] = [
        # ------------------------------------------------------------------
        # Reservation domain
        # ------------------------------------------------------------------
        dict(
            slug="availability_check",
            name="Availability Check",
            description="Check product or room availability.",
            objective="Return accurate availability from company data.",
            instructions=(
                "Use only allowed tools and company knowledge. "
                "Never invent availability. If data is missing, say so clearly."
            ),
            required_knowledge=["product_catalog"],
            allowed_tools=["search_availability"],
            workflow=[
                "receive request",
                "query availability",
                "return result",
            ],
            evaluation_criteria=["accuracy", "no invented data"],
        ),
        dict(
            slug="reservation_management",
            name="Reservation Management",
            description="Create and manage reservations.",
            objective="Manage reservations within policy.",
            instructions=(
                "Follow company reservation policy. "
                "Request approval for sensitive bookings (high value, special terms). "
                "Never invent guest or inventory data."
            ),
            required_knowledge=["product_catalog", "cancellation_policy"],
            allowed_tools=[
                "create_reservation",
                "get_reservation",
                "search_availability",
            ],
            workflow=[
                "validate request",
                "check availability",
                "create or update",
                "confirm",
            ],
            evaluation_criteria=["policy compliance", "data accuracy"],
        ),
        dict(
            slug="booking_support",
            name="Booking Support",
            description="Support booking and customer follow-up.",
            objective="Assist customers with booking status and follow-up.",
            instructions=(
                "Use reservation tools and knowledge. "
                "Escalate unusual cases (complaints, disputes, policy exceptions)."
            ),
            required_knowledge=["cancellation_policy"],
            allowed_tools=["get_reservation"],
            workflow=[
                "identify booking",
                "retrieve status",
                "respond",
            ],
            evaluation_criteria=["clarity", "escalation quality"],
        ),
        dict(
            slug="quotation_preparation",
            name="Quotation Preparation",
            description="Prepare accurate quotation drafts from pricing rules.",
            objective=(
                "Draft accurate quotations without inventing prices; "
                "include breakdown, tax, and validity terms."
            ),
            instructions=(
                "Never invent prices. Use company pricing knowledge and "
                "availability data only. Do not send the quotation to the "
                "customer unless policy allows auto-send; otherwise prepare "
                "a draft for human approval. Always include price breakdown, "
                "taxes, and validity period when known."
            ),
            required_knowledge=[
                "pricing_rules",
                "product_catalog",
                "tax_policy",
            ],
            allowed_tools=[
                "search_availability",
                "draft_quotation",
            ],
            workflow=[
                "gather requirements",
                "check availability",
                "calculate from pricing rules",
                "draft quotation",
                "request approval if required by policy",
            ],
            evaluation_criteria=[
                "price accuracy",
                "completeness",
                "no invented data",
            ],
        ),
        dict(
            slug="customer_follow_up",
            name="Customer Follow-up",
            description="Follow up customers on inquiries or active bookings.",
            objective=(
                "Send relevant, polite follow-ups based on latest booking "
                "or inquiry status without spamming."
            ),
            instructions=(
                "Use reservation and communication history only. "
                "Do not invent prior conversations. "
                "Respect communication tone guidelines. "
                "Escalate angry customers or out-of-scope cases. "
                "Avoid repeated follow-ups without a clear reason."
            ),
            required_knowledge=[
                "cancellation_policy",
                "communication_tone",
            ],
            allowed_tools=[
                "get_reservation",
                "search_knowledge",
            ],
            workflow=[
                "identify customer and latest status",
                "select appropriate follow-up angle",
                "draft message",
                "send or queue according to policy",
            ],
            evaluation_criteria=[
                "relevance",
                "professional tone",
                "no unnecessary repetition",
            ],
        ),
        # ------------------------------------------------------------------
        # Accounting domain
        # ------------------------------------------------------------------
        dict(
            slug="invoice_draft_preparation",
            name="Invoice Draft Preparation",
            description="Create invoice drafts from validated transactions.",
            objective="Produce accurate invoice drafts ready for human review.",
            instructions=(
                "Never send invoices to customers. Only create drafts. "
                "Use official transaction data only. "
                "Flag anomalies (negative amounts, duplicates, missing tax). "
                "Do not invent line items or customer details."
            ),
            required_knowledge=[
                "invoice_template",
                "tax_policy",
                "customer_master",
            ],
            allowed_tools=[
                "search_knowledge",
                "read_document",
            ],
            workflow=[
                "load validated transactions",
                "validate completeness",
                "calculate tax and totals",
                "create invoice draft",
                "flag for human approval",
            ],
            evaluation_criteria=[
                "numeric accuracy",
                "tax compliance",
                "no duplicates",
            ],
        ),
        dict(
            slug="expense_anomaly_detection",
            name="Expense Anomaly Detection",
            description="Detect unusual expenses for human review.",
            objective=(
                "Surface expense anomalies without automatically rejecting "
                "or paying anything."
            ),
            instructions=(
                "Compare against company historical patterns and categories. "
                "Never execute payment or rejection. "
                "Only flag items and explain why they look unusual. "
                "Prefer high-precision flags over noisy alerts."
            ),
            required_knowledge=[
                "expense_categories",
                "historical_patterns",
            ],
            allowed_tools=[
                "search_knowledge",
                "read_document",
            ],
            workflow=[
                "load expense data for period",
                "compare against baseline",
                "flag outliers",
                "prepare human-readable summary",
            ],
            evaluation_criteria=[
                "low false positives",
                "clear rationale",
                "no automatic side effects",
            ],
        ),
        # ------------------------------------------------------------------
        # Sales / Customer Service domain
        # ------------------------------------------------------------------
        dict(
            slug="lead_qualification",
            name="Lead Qualification",
            description="Qualify leads against company scoring rules.",
            objective=(
                "Classify leads (hot / warm / cold) and recommend the "
                "next action without inventing contact data."
            ),
            instructions=(
                "Score only from available data and company lead-scoring rules. "
                "Do not invent emails, phones, or company facts. "
                "Escalate enterprise or high-value leads to human sales. "
                "Keep status updates transparent and reversible."
            ),
            required_knowledge=[
                "lead_scoring_rules",
                "product_catalog",
            ],
            allowed_tools=[
                "search_knowledge",
            ],
            workflow=[
                "load lead data",
                "apply scoring rules",
                "assign status",
                "recommend next step",
            ],
            evaluation_criteria=[
                "consistent with scoring rules",
                "actionable recommendation",
                "no invented data",
            ],
        ),
        dict(
            slug="faq_response",
            name="FAQ Response",
            description="Answer approved company FAQs accurately.",
            objective=(
                "Answer only from approved FAQ knowledge; escalate anything else."
            ),
            instructions=(
                "Search approved FAQ knowledge only. "
                "If the question is outside FAQ coverage, classify intent and escalate. "
                "Never invent new policies or promises. "
                "Keep answers concise and cite the knowledge source when helpful."
            ),
            required_knowledge=[
                "approved_faq",
                "escalation_policy",
            ],
            allowed_tools=[
                "search_knowledge",
            ],
            workflow=[
                "classify intent",
                "search approved FAQ",
                "answer or escalate",
            ],
            evaluation_criteria=[
                "answers only from approved knowledge",
                "correct escalation",
                "clarity",
            ],
        ),
        # ------------------------------------------------------------------
        # Contract domain (existing)
        # ------------------------------------------------------------------
        dict(
            slug="contract_analysis",
            name="Contract Analysis",
            description="Analyze contract content.",
            objective="Extract and summarize contract terms accurately.",
            instructions=(
                "Never invent contract clauses. Use extraction tools. "
                "Flag risks and missing standard clauses clearly."
            ),
            required_knowledge=["contract_templates", "legal_guidelines"],
            allowed_tools=[
                "read_document",
                "extract_contract",
                "search_contract",
            ],
            workflow=[
                "locate contract",
                "extract terms",
                "summarize",
                "flag risks",
            ],
            evaluation_criteria=["extraction accuracy", "risk identification"],
        ),
        dict(
            slug="contract_extraction",
            name="Contract Extraction",
            description="Extract structured fields from contracts.",
            objective="Produce structured contract fields from documents.",
            instructions=(
                "Use extract_contract tool. Report missing fields clearly. "
                "Do not fill gaps with assumptions."
            ),
            required_knowledge=["contract_templates"],
            allowed_tools=["read_document", "extract_contract"],
            workflow=[
                "load document",
                "extract fields",
                "validate",
            ],
            evaluation_criteria=["field completeness", "accuracy"],
        ),
        dict(
            slug="contract_validation",
            name="Contract Validation",
            description="Validate contract data consistency.",
            objective="Validate extracted contract data against guidelines.",
            instructions=(
                "Do not approve invalid data. Escalate conflicts. "
                "Report every failed rule with a clear reason."
            ),
            required_knowledge=["legal_guidelines"],
            allowed_tools=["search_contract", "extract_contract"],
            workflow=[
                "load data",
                "validate rules",
                "report issues",
            ],
            evaluation_criteria=["rule coverage", "escalation quality"],
        ),
    ]

    for item in platform:
        _upsert_skill(
            db,
            company_id=None,
            version="1.0.0",
            is_active=True,
            **item,
        )


# ---------------------------------------------------------------------------
# Company-scoped demo / custom skills
# ---------------------------------------------------------------------------

def seed_demo_company_skills(db: Session, *, company_id: str) -> list[Skill]:
    """
    Seed example company-custom skills for a given tenant.

    Call this after the company (and optionally its agents) exist, e.g. from
    a demo bootstrap or onboarding flow.

    Returns the list of upserted Skill rows.
    """
    company_skills: list[dict] = [
        dict(
            slug="hotel_upsell_package",
            name="Hotel Upsell Package",
            description=(
                "Suggest room upgrade, breakfast, spa, or package upsells "
                "based on inventory and margin rules."
            ),
            objective=(
                "Increase booking value with relevant, non-aggressive upsell "
                "suggestions that respect inventory and policy."
            ),
            instructions=(
                "Only suggest items that are currently available in inventory. "
                "Respect customer preferences and communication tone. "
                "Do not offer discounts outside company policy. "
                "Never invent rates or packages. "
                "Prefer soft suggestions over pressure."
            ),
            required_knowledge=[
                "product_catalog",
                "upsell_margin_rules",
                "customer_preferences",
            ],
            allowed_tools=[
                "search_availability",
                "get_reservation",
                "draft_quotation",
            ],
            workflow=[
                "load active booking",
                "check upsell inventory",
                "filter relevant offers",
                "draft suggestion with price",
            ],
            evaluation_criteria=[
                "only available items",
                "margin within rules",
                "non-aggressive tone",
            ],
        ),
        # Tambahkan custom skill company lain di sini jika perlu.
    ]

    created: list[Skill] = []
    for item in company_skills:
        skill = _upsert_skill(
            db,
            company_id=company_id,
            version="1.0.0",
            is_active=True,
            **item,
        )
        created.append(skill)
    return created
