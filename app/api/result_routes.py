"""Personal bookmarks for persisted AI task results."""

from fastapi import APIRouter, Depends, Header, HTTPException, Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.routes import require_company_user, require_permission
from app.core.database import get_db
from app.models.entities import Task, TaskResultPin

router = APIRouter(prefix="/api/v1/companies/{company_id}", tags=["task-results"])


@router.get("/result-pins", response_model=list[str])
def list_result_pins(
    company_id: str,
    db: Session = Depends(get_db),
    x_user_id: str | None = Header(default=None),
):
    user = require_company_user(db, company_id, x_user_id)
    require_permission(user, "task.read")
    return list(db.scalars(select(TaskResultPin.task_id).where(
        TaskResultPin.company_id == company_id, TaskResultPin.user_id == user.id,
    )))


@router.put("/tasks/{task_id}/result-pin", status_code=204)
def pin_result(
    company_id: str,
    task_id: str,
    db: Session = Depends(get_db),
    x_user_id: str | None = Header(default=None),
):
    user = require_company_user(db, company_id, x_user_id)
    require_permission(user, "task.read")
    task = db.get(Task, task_id)
    if task is None or task.company_id != company_id:
        raise HTTPException(status_code=404, detail="Task not found")
    if not task.result or not task.result.strip():
        raise HTTPException(status_code=409, detail="Task has no result")
    if db.get(TaskResultPin, (user.id, task_id)) is None:
        db.add(TaskResultPin(user_id=user.id, task_id=task_id, company_id=company_id))
        db.commit()
    return Response(status_code=204)


@router.delete("/tasks/{task_id}/result-pin", status_code=204)
def unpin_result(
    company_id: str,
    task_id: str,
    db: Session = Depends(get_db),
    x_user_id: str | None = Header(default=None),
):
    user = require_company_user(db, company_id, x_user_id)
    require_permission(user, "task.read")
    pin = db.get(TaskResultPin, (user.id, task_id))
    if pin is not None and pin.company_id == company_id:
        db.delete(pin)
        db.commit()
    return Response(status_code=204)
