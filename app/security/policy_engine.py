from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.entities import AgentInstance, Policy


@dataclass(frozen=True)
class PolicyDecision:
    effect: str
    reason: str
    policy_id: str | None = None
    approval_level: str | None = None
    matched_conditions: dict[str, Any] = field(default_factory=dict)

    @property
    def allowed(self) -> bool:
        return self.effect == "allow"

    @property
    def requires_approval(self) -> bool:
        return self.effect == "require_approval"

    @property
    def denied(self) -> bool:
        return self.effect == "deny"


def _normalize_effect(raw: str | None) -> str:
    if not raw:
        return "deny"
    value = str(raw).strip().lower()
    # accept product aliases
    if value in {"auto", "allow", "allowed"}:
        return "allow"
    if value in {"approval", "require_approval", "needs_approval"}:
        return "require_approval"
    if value in {"deny", "denied", "block", "blocked"}:
        return "deny"
    return "deny"


def _as_number(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def conditions_match(
    conditions: dict[str, Any] | None,
    arguments: dict[str, Any] | None,
) -> bool:
    """
    Evaluate optional conditions against tool arguments.

    Supported keys:
      amount_gt, amount_gte, amount_lt, amount_lte
      currency (exact, case-insensitive)
      risk (exact, case-insensitive)
      action (exact match on arguments['action'] if present)
    Empty/missing conditions always match.
    """
    if not conditions:
        return True

    args = arguments or {}
    amount = _as_number(
        args.get("amount", args.get("value", args.get("total")))
    )
    currency = str(args.get("currency", "")).strip().upper()
    risk = str(args.get("risk", "")).strip().lower()
    action = str(args.get("action", "")).strip().lower()

    if "amount_gt" in conditions:
        threshold = _as_number(conditions["amount_gt"])
        if threshold is None or amount is None or not (amount > threshold):
            return False

    if "amount_gte" in conditions:
        threshold = _as_number(conditions["amount_gte"])
        if threshold is None or amount is None or not (amount >= threshold):
            return False

    if "amount_lt" in conditions:
        threshold = _as_number(conditions["amount_lt"])
        if threshold is None or amount is None or not (amount < threshold):
            return False

    if "amount_lte" in conditions:
        threshold = _as_number(conditions["amount_lte"])
        if threshold is None or amount is None or not (amount <= threshold):
            return False

    if "currency" in conditions:
        expected = str(conditions["currency"]).strip().upper()
        if not currency or currency != expected:
            return False

    if "risk" in conditions:
        expected = str(conditions["risk"]).strip().lower()
        if not risk or risk != expected:
            return False

    if "action" in conditions:
        expected = str(conditions["action"]).strip().lower()
        if not action or action != expected:
            return False

    return True


class PolicyEngine:
    """
    Deterministic policy enforcement layer.

    Evaluation order:
      1. Active company Policy rows (higher priority first)
      2. Agent instance.policies map (simple tool -> effect)
      3. Default allow

    The LLM must never decide authorization.
    """

    def __init__(self, db: Session):
        self.db = db

    def evaluate(
        self,
        *,
        company_id: str,
        agent_instance_id: str,
        tool_name: str,
        arguments: dict[str, Any] | None = None,
    ) -> PolicyDecision:
        arguments = arguments or {}

        policies = list(
            self.db.scalars(
                select(Policy).where(
                    Policy.company_id == company_id,
                    Policy.is_active.is_(True),
                )
            ).all()
        )

        # Higher priority first; stable by name for ties
        def sort_key(p: Policy) -> tuple:
            cfg = p.configuration or {}
            priority = cfg.get("priority", 0)
            try:
                priority_i = int(priority)
            except (TypeError, ValueError):
                priority_i = 0
            return (-priority_i, p.name or "")

        policies.sort(key=sort_key)

        for policy in policies:
            configuration = policy.configuration or {}
            configured_tool = configuration.get("tool") or configuration.get(
                "action"
            )
            if configured_tool != tool_name:
                continue

            conditions = configuration.get("conditions") or {}
            if not conditions_match(conditions, arguments):
                continue

            effect = _normalize_effect(configuration.get("effect"))
            approval_level = configuration.get("approval_level")
            reason = (
                policy.description
                or f"Policy '{policy.name}' matched tool '{tool_name}'."
            )

            return PolicyDecision(
                effect=effect,
                reason=reason,
                policy_id=policy.id,
                approval_level=str(approval_level) if approval_level else None,
                matched_conditions=dict(conditions),
            )

        # Fallback: agent instance snapshot policies
        agent = self.db.get(AgentInstance, agent_instance_id)
        if agent and agent.company_id == company_id:
            agent_policies = dict(agent.policies or {})
            if tool_name in agent_policies:
                effect = _normalize_effect(agent_policies.get(tool_name))
                return PolicyDecision(
                    effect=effect,
                    reason=(
                        f"Agent policy for tool '{tool_name}' "
                        f"resolved to '{effect}'."
                    ),
                    policy_id=None,
                    approval_level=None,
                    matched_conditions={},
                )

        return PolicyDecision(
            effect="allow",
            reason=f"No explicit policy matched tool '{tool_name}'.",
        )


def get_policy_engine(db: Session) -> PolicyEngine:
    return PolicyEngine(db)
