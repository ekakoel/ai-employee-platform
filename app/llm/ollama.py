from __future__ import annotations

from typing import Any

import ollama

from app.core.config import Settings
from app.llm.base import LLMMessage, LLMProvider, LLMResponse, LLMTool


def _msg_content(response: Any) -> str:
    """Normalize Ollama chat response (dict or object) to content string."""
    if response is None:
        return ""
    if isinstance(response, dict):
        msg = response.get("message") or {}
        if isinstance(msg, dict):
            return str(msg.get("content") or "")
        return str(getattr(msg, "content", "") or "")
    # ChatResponse-like object
    msg = getattr(response, "message", None)
    if msg is None:
        return ""
    if isinstance(msg, dict):
        return str(msg.get("content") or "")
    return str(getattr(msg, "content", "") or "")


def _token_counts(response: Any) -> tuple[int | None, int | None, int | None]:
    prompt = completion = total = None
    if isinstance(response, dict):
        prompt = response.get("prompt_eval_count")
        completion = response.get("eval_count")
    else:
        prompt = getattr(response, "prompt_eval_count", None)
        completion = getattr(response, "eval_count", None)
    if prompt is not None or completion is not None:
        total = int(prompt or 0) + int(completion or 0)
    return (
        int(prompt) if prompt is not None else None,
        int(completion) if completion is not None else None,
        int(total) if total is not None else None,
    )


class OllamaProvider(LLMProvider):
    """LLM provider implementation backed by a local Ollama server."""

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or Settings()
        self.client = ollama.Client(
            host=self.settings.ollama_base_url
        )
        self.model = self.settings.ollama_model

    def chat(
        self,
        messages: list[LLMMessage],
        *,
        temperature: float = 0.0,
        tools: list[LLMTool] | None = None,
    ) -> LLMResponse:

        payload_messages = [
            self._message_to_dict(message)
            for message in messages
        ]

        kwargs: dict[str, Any] = {
            "model": self.model,
            "messages": payload_messages,
            "options": {
                "temperature": temperature,
            },
        }

        if tools:
            kwargs["tools"] = [
                self._tool_to_dict(tool)
                for tool in tools
            ]

        response: Any = self.client.chat(**kwargs)
        content = _msg_content(response)
        prompt_tokens, completion_tokens, total_tokens = _token_counts(response)

        if total_tokens is None:
            chars = sum(len(m.content or "") for m in messages) + len(content)
            total_tokens = max(1, chars // 4)
            prompt_tokens = prompt_tokens or max(1, chars // 5)
            completion_tokens = completion_tokens or max(
                0, total_tokens - int(prompt_tokens)
            )

        return LLMResponse(
            content=content,
            model=self.model,
            raw=response,
            prompt_tokens=int(prompt_tokens or 0),
            completion_tokens=int(completion_tokens or 0),
            total_tokens=int(total_tokens or 0),
        )

    @staticmethod
    def _message_to_dict(
        message: LLMMessage,
    ) -> dict[str, Any]:

        result: dict[str, Any] = {
            "role": message.role,
            "content": message.content,
        }

        if message.tool_call_id is not None:
            result["tool_call_id"] = message.tool_call_id

        if message.tool_name is not None:
            result["tool_name"] = message.tool_name

        if message.tool_calls is not None:
            result["tool_calls"] = message.tool_calls

        return result

    @staticmethod
    def _tool_to_dict(
        tool: LLMTool,
    ) -> dict[str, Any]:

        return {
            "type": "function",
            "function": {
                "name": tool.name,
                "description": tool.description,
                "parameters": tool.parameters,
            },
        }
