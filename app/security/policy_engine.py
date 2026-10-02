from dataclasses import dataclass
from typing import Any

from sqlalchemy.orm import Session

from app.models import Policy


@dataclass(frozen=True)
class PolicyDecision:
    effect: str
    reason: str
    policy_id: str | None = None

    @property
    def allowed(self) -> bool:
        return self.effect == "allow"

    @property
    def requires_approval(self) -> bool:
        return self.effect == "require_approval"

    @property
    def denied(self) -> bool:
        return self.effect == "deny"


class PolicyEngine:
    """
    Deterministic policy enforcement layer.

    The LLM must never be responsible for deciding whether
    a sensitive tool action is allowed.
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
        policies = (
            self.db.query(Policy)
            .filter(
                Policy.company_id == company_id,
                Policy.is_active.is_(True),
            )
            .all()
        )

        for policy in policies:
            configuration = policy.configuration or {}

            configured_tool = configuration.get("tool")

            if configured_tool != tool_name:
                continue

            effect = configuration.get("effect", "deny")

            if effect == "require_approval":
                return PolicyDecision(
                    effect="require_approval",
                    reason=policy.description or f"Approval required for tool '{tool_name}'.",
                    policy_id=policy.id,
                )

            if effect == "deny":
                return PolicyDecision(
                    effect="deny",
                    reason=policy.description or f"Tool '{tool_name}' is denied by policy.",
                    policy_id=policy.id,
                )

            if effect == "allow":
                return PolicyDecision(
                    effect="allow",
                    reason=policy.description or f"Tool '{tool_name}' is allowed by policy.",
                    policy_id=policy.id,
                )

        # Default: allow when no explicit policy matches.
        return PolicyDecision(
            effect="allow",
            reason=f"No explicit policy matched tool '{tool_name}'.",
        )


def get_policy_engine(db: Session) -> PolicyEngine:
    return PolicyEngine(db)