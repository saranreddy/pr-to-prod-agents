"""AWS Bedrock LLM provider."""

import json
import logging
from typing import Any

import boto3

from pr_to_prod.providers.base import BaseLLMProvider, LLMMessage, LLMResponse

logger = logging.getLogger(__name__)


class BedrockProvider(BaseLLMProvider):
    """AWS Bedrock provider for Claude models."""

    PRICING = {
        "anthropic.claude-3-5-sonnet-20241022-v2:0": {
            "input": 3.0 / 1_000_000,
            "output": 15.0 / 1_000_000,
        },
        "anthropic.claude-3-5-haiku-20241022-v1:0": {
            "input": 0.8 / 1_000_000,
            "output": 4.0 / 1_000_000,
        },
    }

    def __init__(
        self,
        region: str = "us-east-1",
        aws_access_key_id: str | None = None,
        aws_secret_access_key: str | None = None,
    ):
        session_kwargs = {"region_name": region}
        if aws_access_key_id and aws_secret_access_key:
            session_kwargs["aws_access_key_id"] = aws_access_key_id
            session_kwargs["aws_secret_access_key"] = aws_secret_access_key

        self.client = boto3.client("bedrock-runtime", **session_kwargs)
        self.region = region

    async def generate(
        self,
        messages: list[LLMMessage],
        model: str,
        temperature: float = 0.7,
        max_tokens: int = 4096,
        **kwargs: Any,
    ) -> LLMResponse:
        """Generate a response using AWS Bedrock."""
        system_messages = [m.content for m in messages if m.role == "system"]
        system = "\n\n".join(system_messages) if system_messages else None

        conversation_messages = [
            {"role": m.role, "content": m.content}
            for m in messages
            if m.role in ["user", "assistant"]
        ]

        body = {
            "anthropic_version": "bedrock-2023-05-31",
            "max_tokens": max_tokens,
            "temperature": temperature,
            "messages": conversation_messages,
        }

        if system:
            body["system"] = system

        response = self.client.invoke_model(
            modelId=model,
            body=json.dumps(body),
        )

        response_body = json.loads(response["body"].read())

        content = ""
        if response_body.get("content"):
            content = response_body["content"][0].get("text", "")

        usage = response_body.get("usage", {})
        prompt_tokens = usage.get("input_tokens", 0)
        completion_tokens = usage.get("output_tokens", 0)

        return LLMResponse(
            content=content,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=prompt_tokens + completion_tokens,
            model=model,
            finish_reason=response_body.get("stop_reason"),
        )

    def estimate_cost(self, prompt_tokens: int, completion_tokens: int, model: str) -> float:
        """Estimate cost based on Bedrock pricing."""
        pricing = self.PRICING.get(
            model, self.PRICING["anthropic.claude-3-5-sonnet-20241022-v2:0"]
        )
        input_cost = prompt_tokens * pricing["input"]
        output_cost = completion_tokens * pricing["output"]
        return input_cost + output_cost
