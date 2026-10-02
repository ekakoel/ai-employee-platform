from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models import AgentCatalog, AgentInstance, Company, KnowledgeItem, Task
from app.models.entities import TaskStatus
from app.schemas.domain import (
    AgentCatalogRead, AgentInstanceRead, CompanyCreate, CompanyRead,
    HireAgentRequest, KnowledgeCreate, KnowledgeRead, KnowledgeUpdate,
    TaskCreate, TaskRead,
)

router = APIRouter(prefix="/api/v1")


def get_company_or_404(db: Session, company_id: str) -> Company:
    company = db.get(Company, company_id)
    if not company:
        raise HTTPException(status_code=404, detail="Company not found")
    return company


def get_owned_agent_or_404(db: Session, company_id: str, agent_instance_id: str) -> AgentInstance:
    agent = db.scalar(
        select(AgentInstance).where(
            AgentInstance.id == agent_instance_id,
            AgentInstance.company_id == company_id,
        )
    )
    if not agent:
        raise HTTPException(status_code=403, detail="Agent is not hired by this company")
    return agent


@router.post("/companies", response_model=CompanyRead, status_code=status.HTTP_201_CREATED)
def create_company(payload: CompanyCreate, db: Session = Depends(get_db)):
    company = Company(name=payload.name)
    db.add(company)
    db.commit()
    db.refresh(company)
    return company


@router.get("/agent-catalog", response_model=list[AgentCatalogRead])
def list_agent_catalog(db: Session = Depends(get_db)):
    return list(db.scalars(select(AgentCatalog).where(AgentCatalog.status == "active")).all())


@router.post("/companies/{company_id}/agents/{catalog_agent_id}/hire", response_model=AgentInstanceRead, status_code=status.HTTP_201_CREATED)
def hire_agent(company_id: str, catalog_agent_id: str, payload: HireAgentRequest, db: Session = Depends(get_db)):
    get_company_or_404(db, company_id)
    catalog = db.get(AgentCatalog, catalog_agent_id)
    if not catalog or catalog.status != "active":
        raise HTTPException(status_code=404, detail="Agent catalog item not found or inactive")

    instance = AgentInstance(
        company_id=company_id,
        catalog_agent_id=catalog.id,
        name=payload.name,
        configuration={"role": catalog.role, "skills": catalog.skills, "allowed_tools": catalog.allowed_tools},
    )
    db.add(instance)
    db.commit()
    db.refresh(instance)
    return instance


@router.get("/companies/{company_id}/agents", response_model=list[AgentInstanceRead])
def list_company_agents(company_id: str, db: Session = Depends(get_db)):
    get_company_or_404(db, company_id)
    return list(db.scalars(select(AgentInstance).where(AgentInstance.company_id == company_id)).all())


@router.post("/companies/{company_id}/knowledge", response_model=KnowledgeRead, status_code=status.HTTP_201_CREATED)
def create_knowledge(company_id: str, payload: KnowledgeCreate, db: Session = Depends(get_db)):
    get_company_or_404(db, company_id)
    if payload.agent_instance_id:
        get_owned_agent_or_404(db, company_id, payload.agent_instance_id)
    item = KnowledgeItem(company_id=company_id, **payload.model_dump())
    db.add(item)
    db.commit()
    db.refresh(item)
    return item


@router.get("/companies/{company_id}/knowledge", response_model=list[KnowledgeRead])
def list_knowledge(company_id: str, db: Session = Depends(get_db)):
    get_company_or_404(db, company_id)
    return list(db.scalars(select(KnowledgeItem).where(KnowledgeItem.company_id == company_id)).all())


@router.patch("/companies/{company_id}/knowledge/{knowledge_id}", response_model=KnowledgeRead)
def update_knowledge(company_id: str, knowledge_id: str, payload: KnowledgeUpdate, db: Session = Depends(get_db)):
    item = db.scalar(select(KnowledgeItem).where(KnowledgeItem.id == knowledge_id, KnowledgeItem.company_id == company_id))
    if not item:
        raise HTTPException(status_code=404, detail="Knowledge item not found")
    for key, value in payload.model_dump(exclude_unset=True).items():
        setattr(item, key, value)
    db.commit()
    db.refresh(item)
    return item


@router.delete("/companies/{company_id}/knowledge/{knowledge_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_knowledge(company_id: str, knowledge_id: str, db: Session = Depends(get_db)):
    item = db.scalar(select(KnowledgeItem).where(KnowledgeItem.id == knowledge_id, KnowledgeItem.company_id == company_id))
    if not item:
        raise HTTPException(status_code=404, detail="Knowledge item not found")
    db.delete(item)
    db.commit()


@router.post("/companies/{company_id}/tasks", response_model=TaskRead, status_code=status.HTTP_201_CREATED)
def create_task(company_id: str, payload: TaskCreate, db: Session = Depends(get_db)):
    get_company_or_404(db, company_id)
    get_owned_agent_or_404(db, company_id, payload.agent_instance_id)
    task = Task(company_id=company_id, **payload.model_dump(), status=TaskStatus.PENDING.value)
    db.add(task)
    db.commit()
    db.refresh(task)
    return task


@router.get("/companies/{company_id}/tasks", response_model=list[TaskRead])
def list_tasks(company_id: str, db: Session = Depends(get_db)):
    get_company_or_404(db, company_id)
    return list(db.scalars(select(Task).where(Task.company_id == company_id)).all())
