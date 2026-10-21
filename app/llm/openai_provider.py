
from openai import OpenAI

from app.llm.base import (
    LLMMessage,
    LLMProvider,
    LLMResponse,
)


class OpenAIProvider(LLMProvider):
    """OpenAI implementation of the common LLM interface."""

    def __init__(
        self,
        *,
        api_key: str,
        model: str,
    ) -> None:
        self.client = OpenAI(api_key=api_key)
        self.model = model

    def chat(
        self,
        messages: list[LLMMessage],
        *,
        temperature: float = 0.0,
        tools=None,
    ) -> LLMResponse:
        # This first adapter version supports text messages only.
        # Tool calling must be implemented and tested separately.
        response = self.client.chat.completions.create(
            model=self.model,
            messages=[
                {
                    "role": message.role,
                    "content": message.content,
                }
                for message in messages
            ],
            temperature=temperature,
        )

        content = response.choices[0].message.content or ""
        usage = response.usage

        return LLMResponse(
            content=content,
            model=response.model,
            raw=response,
            prompt_tokens=usage.prompt_tokens if usage else None,
            completion_tokens=(
                usage.completion_tokens if usage else None
            ),
            total_tokens=usage.total_tokens if usage else None,
        )
