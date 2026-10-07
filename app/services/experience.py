"""Phase 7 — Controlled experience learning."""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.knowledge.retrieval import score_text
from app.models.entities import Experience, ExperienceStatus, Task


def create_candidate_from_task(
    db: Session,
    *,
    task: Task,
    decision: str = "",
    action: str = "",
    human_correction: str = "",
    lesson: str = "",
    confidence: float = 0.4,
) -> Experience:
    exp = Experience(
        company_id=task.company_id,
        agent_instance_id=task.agent_instance_id,
        source_task_id=task.id,
        situation=task.title or "",
        context="",
        problem=task.instruction or "",
        decision=decision or "",
        action=action or "",
        result=task.result or "",
        human_correction=human_correction or "",
        lesson=lesson or "",
        confidence=max(0.0, min(1.0, confidence)),
        validation_status=ExperienceStatus.CANDIDATE.value,
        is_active=True,
    )
    db.add(exp)
    db.flush()
    return exp


def validate_experience(
    db: Session,
    *,
    experience: Experience,
    user_id: str,
    approve: bool,
    lesson: str | None = None,
    confidence: float | None = None,
    human_correction: str | None = None,
) -> Experience:
    if approve:
        experience.validation_status = ExperienceStatus.VALIDATED.value
        if confidence is not None:
            experience.confidence = max(0.0, min(1.0, confidence))
        else:
            experience.confidence = max(experience.confidence, 0.7)
    else:
        experience.validation_status = ExperienceStatus.REJECTED.value

    experience.validated_by = user_id
    experience.validated_at = datetime.now(timezone.utc)
    if lesson is not None:
        experience.lesson = lesson
    if human_correction is not None:
        experience.human_correction = human_correction
    db.flush()
    return experience


def search_validated_experiences(
    db: Session,
    *,
    company_id: str,
    agent_instance_id: str | None,
    query: str,
    limit: int = 5,
    min_confidence: float = 0.3,
) -> list[dict]:
    rows = list(
        db.scalars(
            select(Experience).where(
                Experience.company_id == company_id,
                Experience.is_active.is_(True),
                Experience.validation_status == ExperienceStatus.VALIDATED.value,
                Experience.confidence >= min_confidence,
            )
        ).all()
    )

    # Prefer same agent, but allow company-wide validated experiences
    scored: list[tuple[float, Experience]] = []
    for row in rows:
        blob = " ".join(
            [
                row.situation,
                row.problem,
                row.decision,
                row.action,
                row.result,
                row.lesson,
                row.human_correction,
            ]
        )
        s = score_text(query, blob)
        if agent_instance_id and row.agent_instance_id == agent_instance_id:
            s += 0.15  # slight boost for same agent
        # freshness boost: not strict without created_at math
        s += 0.05 * min(row.success_count, 5) / 5
        if s > 0:
            scored.append((s, row))

    scored.sort(key=lambda x: (x[0], x[1].confidence), reverse=True)
    results = []
    for s, row in scored[:limit]:
        results.append(
            {
                "id": row.id,
                "situation": row.situation,
                "problem": row.problem,
                "decision": row.decision,
                "action": row.action,
                "result": row.result,
                "lesson": row.lesson,
                "human_correction": row.human_correction,
                "confidence": row.confidence,
                "score": round(s, 4),
                "agent_instance_id": row.agent_instance_id,
                "source_task_id": row.source_task_id,
            }
        )
    return results


def record_successful_reuse(db: Session, experience_id: str) -> None:
    exp = db.get(Experience, experience_id)
    if not exp:
        return
    exp.success_count = int(exp.success_count or 0) + 1
    # small confidence nudge, capped
    exp.confidence = min(1.0, float(exp.confidence or 0) + 0.02)
    db.flush()



def submit_feedback(
    db: Session,
    *,
    experience: Experience,
    user_id: str,
    helpful: bool,
    human_correction: str = "",
    lesson: str | None = None,
    confidence_delta: float = 0.0,
) -> Experience:
    """
    Post-validation human feedback (Job 10).

    - helpful=True: bump success_count and confidence
    - helpful=False: apply correction, lower confidence (does not auto-unvalidate)
    """
    if experience.validation_status != ExperienceStatus.VALIDATED.value:
        raise ValueError(
            "Feedback is only allowed on validated experiences."
        )

    if human_correction:
        prev = experience.human_correction or ""
        experience.human_correction = (
            ((prev + "\n") if prev else "") + human_correction.strip()
        )
    if lesson is not None:
        experience.lesson = lesson

    if helpful:
        experience.success_count = int(experience.success_count or 0) + 1
        delta = confidence_delta if confidence_delta else 0.05
        experience.confidence = min(
            1.0, float(experience.confidence or 0) + abs(delta)
        )
    else:
        delta = confidence_delta if confidence_delta else -0.1
        experience.confidence = max(
            0.0, float(experience.confidence or 0) + delta
        )

    db.flush()
    return experience


def archive_experience(
    db: Session,
    *,
    experience: Experience,
) -> Experience:
    experience.validation_status = ExperienceStatus.ARCHIVED.value
    experience.is_active = False
    db.flush()
    return experience


def get_experience_for_company(
    db: Session,
    *,
    company_id: str,
    experience_id: str,
) -> Experience | None:
    return db.scalar(
        select(Experience).where(
            Experience.id == experience_id,
            Experience.company_id == company_id,
        )
    )
