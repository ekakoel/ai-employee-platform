"""Job 21 — Agent conversation / chat (no tool execution without Task)."""

from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.entities import (
    AgentInstance,
    Conversation,
    ConversationStatus,
    Message,
    MessageRole,
    Task,
    TaskStatus,
)
from app.services.audit import record_audit
from app.services.consultation import build_consultation_result


def create_conversation(
    db: Session,
    *,
    company_id: str,
    agent_instance_id: str,
    user_id: str,
    title: str = "",
) -> Conversation:
    agent = db.get(AgentInstance, agent_instance_id)
    if not agent or agent.company_id != company_id:
        raise ValueError("Agent not found in company")
    conv = Conversation(
        company_id=company_id,
        agent_instance_id=agent_instance_id,
        user_id=user_id,
        title=(title or "Chat")[:300],
        status=ConversationStatus.ACTIVE.value,
    )
    db.add(conv)
    db.flush()
    # system welcome
    db.add(
        Message(
            company_id=company_id,
            conversation_id=conv.id,
            role=MessageRole.SYSTEM.value,
            content=(
                "Conversation started. Chat is advisory only. "
                "To execute tools, create a Task from this chat."
            ),
        )
    )
    db.flush()
    record_audit(
        db,
        company_id=company_id,
        user_id=user_id,
        agent_instance_id=agent_instance_id,
        action="conversation.create",
        resource_type="conversation",
        resource_id=conv.id,
        status="success",
    )
    return conv


def list_conversations(
    db: Session,
    *,
    company_id: str,
    user_id: str | None = None,
    agent_instance_id: str | None = None,
    limit: int = 50,
) -> list[Conversation]:
    q = select(Conversation).where(Conversation.company_id == company_id)
    if user_id:
        q = q.where(Conversation.user_id == user_id)
    if agent_instance_id:
        q = q.where(Conversation.agent_instance_id == agent_instance_id)
    q = q.order_by(Conversation.updated_at.desc()).limit(min(limit, 100))
    return list(db.scalars(q).all())


def get_conversation(
    db: Session,
    *,
    company_id: str,
    conversation_id: str,
) -> Conversation | None:
    return db.scalar(
        select(Conversation).where(
            Conversation.id == conversation_id,
            Conversation.company_id == company_id,
        )
    )


def list_messages(
    db: Session,
    *,
    company_id: str,
    conversation_id: str,
    limit: int = 200,
) -> list[Message]:
    return list(
        db.scalars(
            select(Message)
            .where(
                Message.company_id == company_id,
                Message.conversation_id == conversation_id,
            )
            .order_by(Message.created_at.asc())
            .limit(min(limit, 500))
        ).all()
    )


def _agent_reply_text(db: Session, conv: Conversation, human_text: str) -> str:
    """
    Advisory reply only. Prefer local LLM (Ollama) when available;
    fall back to deterministic consultation template.
    Never calls ToolExecutor.
    """
    agent = db.get(AgentInstance, conv.agent_instance_id)
    role = "AI Employee"
    scope = ""
    instructions = ""
    if agent is not None:
        role = (agent.configuration or {}).get("role") or agent.name or role
        scope_list = list(agent.scope or [])
        scope = ", ".join(scope_list) if scope_list else ""
        instructions = (agent.instructions or "")[:800]

    # 1) Try LLM advisory chat (no tools)
    try:
        from app.llm.base import LLMMessage
        from app.runtime.factory import create_llm_provider

        provider = create_llm_provider()
        system = (
            f"You are {role}, an AI Employee co-worker on the AI Employee Platform.\n"
            f"Your professional scope: {scope or 'general company assistance'}.\n"
            "This is advisory chat only: do NOT claim you executed tools, "
            "changed bookings, sent emails, or modified systems.\n"
            "Be concise, helpful, and professional. Answer greetings naturally.\n"
            "If the user asks for real actions, remind them to create a Task "
            "(consult or execute mode) so policy and tools can run."
        )
        if instructions:
            system += f"\nAgent instructions:\n{instructions}"

        resp = provider.chat(
            [
                LLMMessage(role="system", content=system),
                LLMMessage(role="user", content=human_text),
            ],
            temperature=0.4,
            tools=None,
        )
        content = (resp.content or "").strip()
        if content:
            return (
                f"{content}\n\n"
                "_(Chat mode: no tools executed. "
                "Use “Create task” to run with policy & tools.)_"
            )
    except Exception:
        # LLM offline / model missing — fall through to template
        pass

    # 2) Deterministic template fallback
    try:
        task = Task(
            company_id=conv.company_id,
            agent_instance_id=conv.agent_instance_id,
            title=conv.title or "Chat",
            instruction=human_text,
            mode="consult",
            status=TaskStatus.PENDING.value,
        )
        result = build_consultation_result(db, task=task)
        rec = result.get("recommendation") or result.get("rationale") or ""
        if rec:
            return (
                f"{rec}\n\n"
                "_(Chat mode: no tools executed. "
                "Use “Create task” to run with policy & tools.)_"
            )
    except Exception as exc:
        return (
            f"I received your message. "
            f"(Advisory reply unavailable: {exc})\n"
            "Create a Task if you need tool execution."
        )
    return (
        "Thanks — I noted your message. "
        "This chat cannot run tools; create a Task to execute."
    )


def post_human_message(
    db: Session,
    *,
    company_id: str,
    conversation_id: str,
    user_id: str,
    content: str,
    create_task: bool = False,
    task_mode: str = "consult",
) -> dict[str, Any]:
    conv = get_conversation(
        db, company_id=company_id, conversation_id=conversation_id
    )
    if not conv:
        raise ValueError("Conversation not found")
    if conv.user_id != user_id:
        # allow company members later; MVP: owner of conversation only
        # still allow same company with permission checked at API layer
        pass
    if conv.status != ConversationStatus.ACTIVE.value:
        raise ValueError("Conversation is not active")

    text = (content or "").strip()
    if not text:
        raise ValueError("Message content required")

    human = Message(
        company_id=company_id,
        conversation_id=conv.id,
        role=MessageRole.HUMAN.value,
        content=text,
    )
    db.add(human)
    db.flush()

    task = None
    if create_task:
        task = Task(
            company_id=company_id,
            agent_instance_id=conv.agent_instance_id,
            title=(conv.title or text)[:300],
            instruction=text,
            mode=task_mode if task_mode in ("consult", "execute") else "consult",
            status=TaskStatus.PENDING.value,
        )
        db.add(task)
        db.flush()
        human.task_id = task.id
        record_audit(
            db,
            company_id=company_id,
            user_id=user_id,
            agent_instance_id=conv.agent_instance_id,
            task_id=task.id,
            action="conversation.task_created",
            resource_type="task",
            resource_id=task.id,
            status="success",
            details={"conversation_id": conv.id, "message_id": human.id},
        )

    reply_text = _agent_reply_text(db, conv, text)
    agent_msg = Message(
        company_id=company_id,
        conversation_id=conv.id,
        role=MessageRole.AGENT.value,
        content=reply_text,
        task_id=task.id if task else None,
    )
    db.add(agent_msg)
    conv.updated_at = human.created_at  # touch
    db.flush()

    return {
        "human": human,
        "agent": agent_msg,
        "task": task,
        "conversation": conv,
    }
