from __future__ import annotations

import json
from typing import Any

from app.runtime.tool_decision import AgentDecision, ToolCall


class LLMDecisionParser:
    """
    Normalize LLM responses into AgentDecision.

    Supports:
    - dictionary responses used by unit tests
    - Ollama SDK response objects
    - nested Ollama Message / ToolCall / Function objects
    """

    def parse(
        self,
        response: Any,
    ) -> AgentDecision:
        message = self._extract_message(response)

        if message is None:
            return AgentDecision(
                content=self._extract_content(response),
                tool_calls=[],
            )

        content = self._extract_content(message)
        tool_calls = self._extract_tool_calls(message)

        return AgentDecision(
            content=content,
            tool_calls=tool_calls,
        )

    def _extract_message(
        self,
        response: Any,
    ) -> Any:
        if response is None:
            return None

        if isinstance(response, dict):
            return response.get("message")

        message = getattr(
            response,
            "message",
            None,
        )

        if message is not None:
            return message

        return None

    def _extract_content(
        self,
        value: Any,
    ) -> str | None:
        if value is None:
            return None

        if isinstance(value, dict):
            content = value.get("content")

            if content is None:
                return None

            return str(content)

        content = getattr(
            value,
            "content",
            None,
        )

        if content is None:
            return None

        return str(content)

    def _extract_tool_calls(
        self,
        message: Any,
    ) -> list[ToolCall]:
        if message is None:
            return []

        if isinstance(message, dict):
            raw_tool_calls = (
                message.get("tool_calls")
                or []
            )
        else:
            raw_tool_calls = (
                getattr(
                    message,
                    "tool_calls",
                    None,
                )
                or []
            )

        return [
            parsed
            for raw_tool_call in raw_tool_calls
            if (
                parsed := self._parse_tool_call(
                    raw_tool_call
                )
            )
            is not None
        ]

    def _parse_tool_call(
        self,
        raw_tool_call: Any,
    ) -> ToolCall | None:
        function = self._extract_function(
            raw_tool_call
        )

        if function is None:
            return None

        name = self._extract_value(
            function,
            "name",
        )

        if not name:
            return None

        arguments = self._extract_value(
            function,
            "arguments",
        )

        normalized_arguments = (
            self._normalize_arguments(
                arguments
            )
        )

        return ToolCall(
            name=str(name),
            arguments=normalized_arguments,
        )

    def _extract_function(
        self,
        tool_call: Any,
    ) -> Any:
        if isinstance(tool_call, dict):
            return tool_call.get("function")

        return getattr(
            tool_call,
            "function",
            None,
        )

    def _extract_value(
        self,
        value: Any,
        key: str,
    ) -> Any:
        if value is None:
            return None

        if isinstance(value, dict):
            return value.get(key)

        return getattr(
            value,
            key,
            None,
        )

    def _normalize_arguments(
        self,
        arguments: Any,
    ) -> dict[str, Any]:
        if arguments is None:
            return {}

        if isinstance(arguments, dict):
            return arguments

        if isinstance(arguments, str):
            try:
                parsed = json.loads(arguments)
            except json.JSONDecodeError:
                return {}

            if isinstance(parsed, dict):
                return parsed

        return {}