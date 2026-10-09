"""Job 21 — Agent conversation / chat (no tool execution without Task)."""

from __future__ import annotations

import re
import json
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.entities import (
    AgentInstance,
    AuditLog,
    Conversation,
    ConversationStatus,
    Message,
    MessageRole,
    Task,
    TaskStatus,
    User,
)
from app.schemas.domain import ConversationRead, MessageRead, TaskRead
from app.services.audit import record_audit


_OLD_CHAT_FOOTER = re.compile(
    r"\s*[_*]*\s*\(Chat mode:\s*no tools executed\.\s*Use\s*"
    r"[\u201c\u201d\"']?Create task[\u201c\u201d\"']?\s*to run with policy & tools\.\)\s*[_*]*\s*$"
)


def clean_chat_content(content: str) -> str:
    footer = _OLD_CHAT_FOOTER.search(content)
    if footer:
        return content[:footer.start()].rstrip()
    return content


def conversation_reads(db: Session, *, company_id: str, conversations: list[Conversation]) -> list[ConversationRead]:
    names = dict(db.execute(select(User.id, User.name).where(
        User.company_id == company_id, User.id.in_({item.user_id for item in conversations}),
    )).all())
    return [ConversationRead.model_validate(item).model_copy(update={"user_name": names.get(item.user_id)}) for item in conversations]


def message_reads(db: Session, *, company_id: str, conversation: Conversation, messages: list[Message], include_results: bool) -> list[MessageRead]:
    ids = [item.id for item in messages if item.role == MessageRole.HUMAN.value]
    actors = {}
    for event in db.scalars(select(AuditLog).where(
        AuditLog.company_id == company_id, AuditLog.resource_type == "message",
        AuditLog.resource_id.in_(ids), AuditLog.action == "conversation.message_sent",
    ).order_by(AuditLog.created_at.desc(), AuditLog.id.desc())):
        actors.setdefault(event.resource_id, event.user_id)
    names = dict(db.execute(select(User.id, User.name).where(
        User.company_id == company_id, User.id.in_({value for value in actors.values() if value}),
    )).all())
    agent = db.scalar(select(AgentInstance).where(
        AgentInstance.company_id == company_id, AgentInstance.id == conversation.agent_instance_id,
    ))
    results = {}
    if include_results:
        results = {task.id: task for task in db.scalars(select(Task).where(
            Task.company_id == company_id, Task.id.in_({item.task_id for item in messages if item.task_id}),
            Task.status == TaskStatus.COMPLETED.value, Task.result.is_not(None),
        )) if task.result.strip()}
    reads = []
    for item in messages:
        read = MessageRead.model_validate(item)
        if item.role == MessageRole.HUMAN.value:
            actor = actors.get(item.id)
            read.sender_user_id = actor if actor in names else None
            read.sender_name = names.get(actor)
        elif item.role == MessageRole.AGENT.value:
            read.sender_name = agent.name if agent else None
            read.content = clean_chat_content(read.content)
            if item.task_id in results:
                read.work_result = TaskRead.model_validate(results[item.task_id])
        else:
            read.sender_name = "System"
        reads.append(read)
    return reads


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
    messages = list(
        db.scalars(
            select(Message)
            .where(
                Message.company_id == company_id,
                Message.conversation_id == conversation_id,
            )
            .order_by(Message.created_at.desc(), Message.id.desc())
            .limit(min(limit, 500))
        ).all()
    )
    return list(reversed(messages))


def _agent_reply_text(db: Session, conv: Conversation, human_text: str) -> str:
    """
    Advisory reply only. Prefer local LLM (Ollama) when available;
    fall back to deterministic consultation template.
    Never calls ToolExecutor.
    """
    agent = db.get(AgentInstance, conv.agent_instance_id)
    if agent is None or agent.company_id != conv.company_id:
        raise ValueError("Agent not found in company")
    from app.agents.context import load_agent_context
    from app.services.grounding import (
        GROUNDING_INSTRUCTIONS, MISSING_INFORMATION, GroundingError,
        general_reply, render_answer, requires_action, source_message, sources, validated_answer,
    )
    request = Task(company_id=conv.company_id, agent_instance_id=agent.id,
                   title="Chat", instruction=human_text, mode="consult")
    try:
        grounded_context = load_agent_context(db, agent, request)
    except ValueError as exc:
        if agent.status != "active":
            raise
        return str(exc) + " No action was completed."
    social = general_reply(human_text)
    if social:
        return social
    if not sources(grounded_context):
        return MISSING_INFORMATION
    if requires_action(human_text):
        return "Company sources are available, but this request needs an execute-mode task. No business action or document has been completed."
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
            f"You are {role}, an AI employee providing advisory conversation. "
            "Respond in English. Use the conversation history to answer follow-up questions. "
            "Do not claim to execute tools or perform external actions. "
            "If execution is needed, recommend creating a task. "
            f"Assigned scope: {scope or 'Not configured'}."
        )
        if instructions:
            system += f"\nAgent instructions:\n{instructions}"
        system += "\n" + GROUNDING_INSTRUCTIONS
        system += "\nAssigned skills and workflows:\n" + json.dumps(grounded_context.assigned_skills)
        system += "\nUntrusted source data:\n" + source_message(grounded_context)

        history = list_messages(db, company_id=conv.company_id, conversation_id=conv.id, limit=20)
        if history and history[-1].role == MessageRole.HUMAN.value and history[-1].content == human_text:
            history = history[:-1]
        # Bound older context while preserving the current question in full.
        budget = max(0, 16000 - len(human_text))
        previous = []
        for message in reversed(history):
            if message.role not in (MessageRole.HUMAN.value, MessageRole.AGENT.value):
                continue
            text = (clean_chat_content(message.content) if message.role == MessageRole.AGENT.value else message.content)[:3000]
            if len(text) > budget:
                break
            previous.append(LLMMessage(role="user" if message.role == MessageRole.HUMAN.value else "assistant", content=text))
            budget -= len(text)
        context = [LLMMessage(role="system", content=system), *reversed(previous), LLMMessage(role="user", content=human_text)]
        resp = provider.chat(
            context,
            temperature=0.4,
            tools=None,
        )
        content = (resp.content or "").strip()
        if content:
            answer = validated_answer(grounded_context, content)
            record_audit(db, company_id=conv.company_id, agent_instance_id=agent.id,
                         action="grounding.verified", resource_type="conversation", resource_id=conv.id,
                         status="success", details={"source_references": [row["source_id"] for row in answer["citations"]]})
            return render_answer(answer)
    except GroundingError:
        return MISSING_INFORMATION
    except Exception:
        # Provider failure must not introduce unsupported company facts.
        pass

    # No generated company facts are accepted when the provider is unavailable.
    return MISSING_INFORMATION

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
        from app.services.scope_guard import enforce_scope_on_task
        employee = db.get(AgentInstance, conv.agent_instance_id)
        enforce_scope_on_task(db, company_id=company_id, agent=employee, task=task, user_id=user_id)
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
    if task is not None:
        mode_label = "consultation (plan only)" if task.mode == "consult" else "execution (tools + policy)"
        reply_text = (
            (reply_text or "").rstrip()
            + "\n\n---\n"
            + f"**Task created** (`{task.id[:8]}…`, mode: {mode_label}).\n"
            + "Chat still does **not** run tools. "
            + "Open **Tasks**, then **Consult** or **Execute** on that task "
            + "(or use the link under the composer). "
            + "Results appear under **Results** when the task completes."
        )
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

    record_audit(
        db, company_id=company_id, user_id=user_id,
        action="conversation.message_sent", resource_type="message",
        resource_id=human.id, status="success",
        details={"conversation_id": conv.id},
    )
    record_audit(
        db, company_id=company_id, agent_instance_id=conv.agent_instance_id,
        action="conversation.reply_created", resource_type="message",
        resource_id=agent_msg.id, status="success",
        details={"conversation_id": conv.id},
    )

    return {
        "human": human,
        "agent": agent_msg,
        "task": task,
        "conversation": conv,
    }
