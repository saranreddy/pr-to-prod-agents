"""Tests for LLM providers."""

import pytest

from pr_to_prod.providers.base import LLMMessage
from pr_to_prod.providers.mock import MockProvider


@pytest.mark.asyncio
async def test_mock_provider_deterministic():
    """Test that mock provider generates deterministic responses."""
    provider = MockProvider(deterministic=True)

    messages = [LLMMessage(role="user", content="test input")]

    response1 = await provider.generate(messages, model="test-model")
    response2 = await provider.generate(messages, model="test-model")

    assert response1.content == response2.content


@pytest.mark.asyncio
async def test_mock_provider_plan_response():
    """Test that mock provider recognizes plan requests."""
    provider = MockProvider()

    messages = [LLMMessage(role="user", content="create a plan for this feature")]

    response = await provider.generate(messages, model="test-model")

    assert "plan" in response.content.lower()
    assert "files" in response.content.lower()


@pytest.mark.asyncio
async def test_mock_provider_code_response():
    """Test that mock provider recognizes code requests."""
    provider = MockProvider()

    messages = [LLMMessage(role="user", content="implement this feature in code")]

    response = await provider.generate(messages, model="test-model")

    assert "implementation" in response.content.lower()


@pytest.mark.asyncio
async def test_mock_provider_review_response():
    """Test that mock provider recognizes review requests."""
    provider = MockProvider()

    messages = [LLMMessage(role="user", content="review this code change")]

    response = await provider.generate(messages, model="test-model")

    assert "review" in response.content.lower()


@pytest.mark.asyncio
async def test_mock_provider_token_counting():
    """Test that mock provider counts tokens."""
    provider = MockProvider()

    messages = [
        LLMMessage(role="system", content="You are a helpful assistant"),
        LLMMessage(role="user", content="Hello world"),
    ]

    response = await provider.generate(messages, model="test-model")

    assert response.prompt_tokens > 0
    assert response.completion_tokens > 0
    assert response.total_tokens == response.prompt_tokens + response.completion_tokens


def test_mock_provider_zero_cost():
    """Test that mock provider has zero cost."""
    provider = MockProvider()

    cost = provider.estimate_cost(1000, 500, "test-model")

    assert cost == 0.0


@pytest.mark.asyncio
async def test_mock_provider_call_count():
    """Test that mock provider tracks call count."""
    provider = MockProvider()

    assert provider.call_count == 0

    await provider.generate([LLMMessage(role="user", content="test")], "model")
    assert provider.call_count == 1

    await provider.generate([LLMMessage(role="user", content="test")], "model")
    assert provider.call_count == 2
