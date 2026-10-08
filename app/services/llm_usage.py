"""Job 28 — LLM usage recording, cost summary, soft budget."""

from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Any

from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.entities import LLMUsage
from app.services.quotas import METRIC_LLM, increment_usage


def estimate_cost_usd(
    prompt_tokens: int,
    completion_tokens: int,
    *,
    prompt_rate: float | None = None,
    completion_rate: float | None = None,
) -> float:
    from app.core.config import settings as live

    pr = (
        prompt_rate
        if prompt_rate is not None
        else live.llm_cost_per_1k_prompt_tokens
    )
    cr = (
        completion_rate
        if completion_rate is not None
        else live.llm_cost_per_1k_completion_tokens
    )
    return (prompt_tokens / 1000.0) * float(pr) + (completion_tokens / 1000.0) * float(
        cr
    )


def record_llm_usage(
    db: Session,
    *,
    company_id: str,
    model: str = "",
    prompt_tokens: int = 0,
    completion_tokens: int = 0,
    total_tokens: int | None = None,
    agent_instance_id: str | None = None,
    task_id: str | None = None,
    provider: str = "ollama",
) -> LLMUsage:
    pt = max(0, int(prompt_tokens or 0))
    ct = max(0, int(completion_tokens or 0))
    tt = int(total_tokens) if total_tokens is not None else pt + ct
    cost = estimate_cost_usd(pt, ct)
    row = LLMUsage(
        company_id=company_id,
        agent_instance_id=agent_instance_id,
        task_id=task_id,
        model=model or "",
        prompt_tokens=pt,
        completion_tokens=ct,
        total_tokens=tt,
        estimated_cost_usd=cost,
        provider=provider,
    )
    db.add(row)
    db.flush()
    # daily counter for quotas
    try:
        increment_usage(db, company_id, METRIC_LLM, by=1)
    except Exception:
        pass
    return row


def cost_summary(
    db: Session,
    *,
    company_id: str,
    period_date: str | None = None,
) -> dict[str, Any]:
    """Aggregate token/cost for company (all-time + today)."""
    today = period_date or date.today().isoformat()
    rows = list(
        db.scalars(
            select(LLMUsage).where(LLMUsage.company_id == company_id)
        ).all()
    )
    today_rows = [
        r
        for r in rows
        if r.created_at
        and (
            r.created_at.date().isoformat()
            if hasattr(r.created_at, "date")
            else str(r.created_at)[:10]
        )
        == today
    ]

    def agg(items: list[LLMUsage]) -> dict[str, Any]:
        return {
            "calls": len(items),
            "prompt_tokens": sum(i.prompt_tokens for i in items),
            "completion_tokens": sum(i.completion_tokens for i in items),
            "total_tokens": sum(i.total_tokens for i in items),
            "estimated_cost_usd": round(sum(i.estimated_cost_usd for i in items), 6),
        }

    by_model: dict[str, dict[str, Any]] = {}
    for r in rows:
        m = r.model or "unknown"
        slot = by_model.setdefault(
            m,
            {
                "calls": 0,
                "total_tokens": 0,
                "estimated_cost_usd": 0.0,
            },
        )
        slot["calls"] += 1
        slot["total_tokens"] += r.total_tokens
        slot["estimated_cost_usd"] = round(
            slot["estimated_cost_usd"] + r.estimated_cost_usd, 6
        )

    from app.core.config import settings as live

    budget = float(live.llm_daily_budget_usd or 0)
    today_cost = agg(today_rows)["estimated_cost_usd"]
    return {
        "period_date": today,
        "all_time": agg(rows),
        "today": agg(today_rows),
        "by_model": by_model,
        "budget": {
            "daily_usd": budget,
            "today_spend_usd": today_cost,
            "soft_limit_enabled": budget > 0,
            "over_budget": budget > 0 and today_cost >= budget,
            "remaining_usd": round(max(0.0, budget - today_cost), 6) if budget > 0 else None,
        },
    }


def check_llm_budget(db: Session, *, company_id: str) -> None:
    """Soft limit: raise 429 if daily estimated cost exceeds budget (when > 0)."""
    from app.core.config import settings as live

    budget = float(live.llm_daily_budget_usd or 0)
    if budget <= 0:
        return
    summary = cost_summary(db, company_id=company_id)
    if summary["budget"]["over_budget"]:
        raise HTTPException(
            status_code=429,
            detail={
                "error": "llm_budget_exceeded",
                "daily_budget_usd": budget,
                "today_spend_usd": summary["budget"]["today_spend_usd"],
            },
        )



class RecordingLLMProvider:
    """Wraps an LLMProvider and records each chat call to llm_usage."""

    def __init__(
        self,
        inner,
        db: Session,
        *,
        company_id: str,
        agent_instance_id: str | None = None,
        task_id: str | None = None,
        enforce_budget: bool = True,
    ):
        self.inner = inner
        self.db = db
        self.company_id = company_id
        self.agent_instance_id = agent_instance_id
        self.task_id = task_id
        self.enforce_budget = enforce_budget

    def chat(self, messages, *, temperature: float = 0.0, tools=None):
        if self.enforce_budget:
            check_llm_budget(self.db, company_id=self.company_id)
        response = self.inner.chat(
            messages, temperature=temperature, tools=tools
        )
        try:
            record_llm_usage(
                self.db,
                company_id=self.company_id,
                model=getattr(response, "model", "") or "",
                prompt_tokens=getattr(response, "prompt_tokens", 0) or 0,
                completion_tokens=getattr(response, "completion_tokens", 0) or 0,
                total_tokens=getattr(response, "total_tokens", None),
                agent_instance_id=self.agent_instance_id,
                task_id=self.task_id,
                provider=type(self.inner).__name__,
            )
        except Exception:
            pass
        return response
