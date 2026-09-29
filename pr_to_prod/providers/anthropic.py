"""Anthropic LLM provider using the Anthropic API."""

import logging
from typing import Any

from anthropic import AsyncAnthropic

from pr_to_prod.providers.base import BaseLLMProvider, LLMMessage, LLMResponse

logger = logging.getLogger(__name__)


class AnthropicProvider(BaseLLMProvider):
    """Anthropic Claude provider."""

    PRICING = {
        "claude-3-5-sonnet-20241022": {"input": 3.0 / 1_000_000, "output": 15.0 / 1_000_000},
        "claude-3-5-haiku-20241022": {"input": 0.8 / 1_000_000, "output": 4.0 / 1_000_000},
        "claude-3-opus-20240229": {"input": 15.0 / 1_000_000, "output": 75.0 / 1_000_000},
    }

    def __init__(self, api_key: str):
        self.client = AsyncAnthropic(api_key=api_key)

    async def generate(
        self,
        messages: list[LLMMessage],
        model: str,
        temperature: float = 0.7,
        max_tokens: int = 4096,
        **kwargs: Any,
    ) -> LLMResponse:
        """Generate a response using Anthropic's API."""
        system_messages = [m.content for m in messages if m.role == "system"]
        system = "\n\n".join(system_messages) if system_messages else None

        conversation_messages = [
            {"role": m.role, "content": m.content}
            for m in messages
            if m.role in ["user", "assistant"]
        ]

        kwargs_filtered = {**kwargs}
        if system:
            kwargs_filtered["system"] = system

        response = await self.client.messages.create(
            model=model,
            max_tokens=max_tokens,
            messages=conversation_messages,  # type: ignore[arg-type]
            **kwargs_filtered,
        )

        content = ""
        if response.content:
            content = response.content[0].text if hasattr(response.content[0], "text") else ""

        return LLMResponse(
            content=content,
            prompt_tokens=response.usage.input_tokens,
            completion_tokens=response.usage.output_tokens,
            total_tokens=response.usage.input_tokens + response.usage.output_tokens,
            model=model,
            finish_reason=response.stop_reason,
        )

    def estimate_cost(self, prompt_tokens: int, completion_tokens: int, model: str) -> float:
        """Estimate cost based on Anthropic pricing."""
        pricing = self.PRICING.get(model, self.PRICING["claude-3-5-sonnet-20241022"])
        input_cost = prompt_tokens * pricing["input"]
        output_cost = completion_tokens * pricing["output"]
        return input_cost + output_cost
