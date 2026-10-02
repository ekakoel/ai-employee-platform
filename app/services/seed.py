from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import AgentCatalog


def seed_catalog(db: Session) -> None:
    existing = db.scalar(select(AgentCatalog).where(AgentCatalog.slug == "reservation"))
    if existing:
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
