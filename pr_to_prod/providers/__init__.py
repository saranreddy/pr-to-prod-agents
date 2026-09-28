"""LLM provider factory."""

import logging

from pr_to_prod.config import Settings
from pr_to_prod.providers.anthropic import AnthropicProvider
from pr_to_prod.providers.base import BaseLLMProvider
from pr_to_prod.providers.bedrock import BedrockProvider
from pr_to_prod.providers.mock import MockProvider

logger = logging.getLogger(__name__)


def create_llm_provider(settings: Settings) -> BaseLLMProvider:
    """Create an LLM provider based on configuration."""
    if settings.llm_provider == "anthropic":
        if not settings.anthropic_api_key:
            raise ValueError("ANTHROPIC_API_KEY is required for anthropic provider")
        logger.info("Using Anthropic LLM provider")
        return AnthropicProvider(api_key=settings.anthropic_api_key)

    elif settings.llm_provider == "bedrock":
        logger.info(f"Using AWS Bedrock LLM provider in region {settings.aws_region}")
        return BedrockProvider(
            region=settings.aws_region,
            aws_access_key_id=settings.aws_access_key_id,
            aws_secret_access_key=settings.aws_secret_access_key,
        )

    elif settings.llm_provider == "mock":
        logger.info("Using Mock LLM provider (offline mode)")
        return MockProvider(deterministic=True)

    else:
        raise ValueError(f"Unknown LLM provider: {settings.llm_provider}")
