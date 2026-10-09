"""Job 16 — Runtime scope guard + directory-based delegation suggest."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy.orm import Session

from app.models.entities import (
    AgentInstance,
    DelegationRequest,
    DelegationStatus,
    Task,
    TaskStatus,
)
from app.services.audit import record_audit
from app.services.directory import (
    AgentCapabilityCard,
    agent_capability_card,
    list_directory,
)


_TOKEN_RE = re.compile(r"[a-z0-9_]{3,}")

# High-signal domain terms used when agent vocabulary is sparse
_DOMAIN_HINTS = {
    "contract": ["contract", "clause", "legal", "agreement", "vendor", "supplier"],
    "reservation": ["reservation", "booking", "itinerary", "quotation", "guest", "room"],
    "accounting": ["invoice", "accounting", "ledger", "payment", "tax", "finance"],
    "hr": ["payroll", "employee", "recruitment", "leave", "hr"],
}


def _tokenize(text: str) -> set[str]:
    return set(_TOKEN_RE.findall((text or "").lower()))


def agent_vocabulary(card: AgentCapabilityCard) -> set[str]:
    words: set[str] = set()
    for bucket in (card.scope, card.skills, card.tools, card.capabilities):
        for item in bucket or []:
            words |= _tokenize(str(item).replace(":", " ").replace("_", " "))
    words |= _tokenize(card.role or "")
    words |= _tokenize(card.name or "")
    if card.catalog_slug:
        words |= _tokenize(card.catalog_slug.replace("-", " "))
    for domain, aliases in _DOMAIN_HINTS.items():
        if domain in words:
            words.update(aliases)
    return {w for w in words if len(w) >= 3}


def score_overlap(instruction_tokens: set[str], vocab: set[str]) -> float:
    if not instruction_tokens:
        return 0.0
    if not vocab:
        return 0.0
    hit = instruction_tokens & vocab
    # weight by coverage of instruction domain tokens present in vocab
    return len(hit) / max(len(instruction_tokens), 1)


def score_card_for_instruction(
    instruction: str,
    card: AgentCapabilityCard,
) -> float:
    tokens = _tokenize(instruction)
    vocab = agent_vocabulary(card)
    base = score_overlap(tokens, vocab)
    # boost exact capability/skill substring matches
    text = instruction.lower()
    boost = 0.0
    for s in card.skills or []:
        if str(s).lower() in text:
            boost += 0.15
    for sc in card.scope or []:
        if str(sc).lower() in text:
            boost += 0.2
    for cap in card.capabilities or []:
        tail = cap.split(":")[-1] if ":" in cap else cap
        if tail and tail.lower() in text:
            boost += 0.1
    return min(1.0, base + boost)


@dataclass
class ScopeMatch:
    agent_instance_id: str
    name: str
    score: float
    capabilities: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "agent_instance_id": self.agent_instance_id,
            "name": self.name,
            "score": round(self.score, 4),
            "capabilities": list(self.capabilities)[:12],
        }


@dataclass
class ScopeCheckResult:
    in_scope: bool
    reason: str
    agent_instance_id: str
    agent_score: float
    alternatives: list[ScopeMatch] = field(default_factory=list)
    suggested_target_id: str | None = None
    auto_delegated: bool = False
    delegation_request_id: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "in_scope": self.in_scope,
            "reason": self.reason,
            "agent_instance_id": self.agent_instance_id,
            "agent_score": round(self.agent_score, 4),
            "alternatives": [a.to_dict() for a in self.alternatives],
            "suggested_target_id": self.suggested_target_id,
            "auto_delegated": self.auto_delegated,
            "delegation_request_id": self.delegation_request_id,
            "status": "IN_SCOPE" if self.in_scope else "OUT_OF_SCOPE",
        }


def _directory_scores(
    db: Session,
    *,
    company_id: str,
    instruction: str,
    exclude_agent_id: str | None,
) -> list[ScopeMatch]:
    cards = list_directory(db, company_id=company_id, active_only=True)
    matches: list[ScopeMatch] = []
    for card in cards:
        if exclude_agent_id and card.agent_instance_id == exclude_agent_id:
            continue
        score = score_card_for_instruction(instruction, card)
        if score <= 0:
            continue
        matches.append(
            ScopeMatch(
                agent_instance_id=card.agent_instance_id,
                name=card.name,
                score=score,
                capabilities=list(card.capabilities),
            )
        )
    matches.sort(key=lambda m: m.score, reverse=True)
    return matches


def check_scope(
    db: Session,
    *,
    company_id: str,
    agent: AgentInstance,
    instruction: str,
    auto_delegate: bool = False,
    user_id: str | None = None,
    source_task: Task | None = None,
) -> ScopeCheckResult:
    """
    Decide whether instruction fits the agent's professional scope.

    Rules:
    - Missing scope or no matching specialist capability fails closed.
    - If agent score is decent (>= 0.08) → in-scope.
    - If another agent scores significantly higher → out-of-scope.
    - If agent score is ~0 and alternatives exist → out-of-scope.
    - auto_delegate + single clear winner → create DelegationRequest.
    """
    card = agent_capability_card(db, agent)
    agent_score = score_card_for_instruction(instruction, card)
    alternatives = _directory_scores(
        db,
        company_id=company_id,
        instruction=instruction,
        exclude_agent_id=agent.id,
    )

    vocab = agent_vocabulary(card)
    if agent.company_id != company_id or agent.status != "active":
        return ScopeCheckResult(False, "Employee is not active in this company.", agent.id, 0.0)
    # Missing configuration is not authorization.
    if not vocab or not any((card.scope, card.skills, card.tools, card.capabilities)):
        result = ScopeCheckResult(
            in_scope=False,
            reason="Agent has no authorized scope/skills vocabulary.",
            agent_instance_id=agent.id,
            agent_score=agent_score,
            alternatives=alternatives[:5],
        )
        return result

    best_alt = alternatives[0] if alternatives else None
    clearly_better = (
        best_alt is not None
        and best_alt.score >= 0.12
        and best_alt.score >= agent_score + 0.08
    )
    weak_self = agent_score < 0.08

    if not weak_self and not clearly_better:
        return ScopeCheckResult(
            in_scope=True,
            reason="Instruction overlaps agent scope/skills.",
            agent_instance_id=agent.id,
            agent_score=agent_score,
            alternatives=alternatives[:5],
        )

    if weak_self and not alternatives:
        # Absence of another specialist does not authorize this employee.
        return ScopeCheckResult(
            in_scope=False,
            reason="Instruction does not match the assigned employee scope.",
            agent_instance_id=agent.id,
            agent_score=agent_score,
            alternatives=[],
        )

    # OUT OF SCOPE
    suggested = best_alt.agent_instance_id if best_alt else None
    result = ScopeCheckResult(
        in_scope=False,
        reason=(
            "Instruction appears outside this agent's scope. "
            "Prefer a specialist from the directory."
            if clearly_better or weak_self
            else "Scope check failed."
        ),
        agent_instance_id=agent.id,
        agent_score=agent_score,
        alternatives=alternatives[:5],
        suggested_target_id=suggested,
    )

    record_audit(
        db,
        company_id=company_id,
        user_id=user_id,
        agent_instance_id=agent.id,
        task_id=source_task.id if source_task else None,
        action="scope.miss",
        resource_type="agent_instance",
        resource_id=agent.id,
        status="warning",
        details={
            "agent_score": agent_score,
            "suggested_target_id": suggested,
            "alternatives": [a.to_dict() for a in alternatives[:3]],
            "instruction_preview": (instruction or "")[:200],
        },
    )

    # Auto-delegate when enabled and one clear winner
    cfg = agent.configuration if isinstance(agent.configuration, dict) else {}
    want_auto = bool(auto_delegate or cfg.get("auto_delegate"))
    if want_auto and best_alt and best_alt.score >= 0.12 and clearly_better:
        capability = "general"
        if best_alt.capabilities:
            capability = best_alt.capabilities[0]
        title = (
            source_task.title
            if source_task
            else f"Delegated: {(instruction or '')[:80]}"
        )
        delegation = DelegationRequest(
            company_id=company_id,
            source_agent_instance_id=agent.id,
            target_agent_instance_id=best_alt.agent_instance_id,
            requested_by_user_id=user_id,
            capability=capability[:200],
            title=title[:300],
            instruction=instruction,
            status=DelegationStatus.PENDING.value,
            validation_notes="Auto-created by scope guard (Job 16).",
        )
        db.add(delegation)
        db.flush()
        result.auto_delegated = True
        result.delegation_request_id = delegation.id
        result.suggested_target_id = best_alt.agent_instance_id

        record_audit(
            db,
            company_id=company_id,
            user_id=user_id,
            agent_instance_id=agent.id,
            task_id=source_task.id if source_task else None,
            action="delegation.suggested",
            resource_type="delegation_request",
            resource_id=delegation.id,
            status="success",
            details={
                "target_agent_instance_id": best_alt.agent_instance_id,
                "score": best_alt.score,
                "auto": True,
            },
        )

    return result


def enforce_scope_on_task(
    db: Session,
    *,
    company_id: str,
    agent: AgentInstance,
    task: Task,
    auto_delegate: bool = False,
    user_id: str | None = None,
    block_out_of_scope: bool = True,
) -> ScopeCheckResult:
    """
    Run scope check for an existing task.

    If out of scope and block_out_of_scope:
      - task.status = cancelled (or failed)
      - task.result = structured OUT_OF_SCOPE JSON string
    """
    import json

    result = check_scope(
        db,
        company_id=company_id,
        agent=agent,
        instruction=task.instruction or task.title or "",
        auto_delegate=auto_delegate,
        user_id=user_id,
        source_task=task,
    )
    if result.in_scope:
        return result

    payload = {
        "status": "OUT_OF_SCOPE",
        "message": result.reason,
        "agent_score": result.agent_score,
        "alternatives": [a.to_dict() for a in result.alternatives],
        "suggested_target_id": result.suggested_target_id,
        "delegation_request_id": result.delegation_request_id,
        "auto_delegated": result.auto_delegated,
    }
    if block_out_of_scope:
        task.status = TaskStatus.CANCELLED.value
        task.result = json.dumps(payload, ensure_ascii=False)
        db.flush()
    return result
