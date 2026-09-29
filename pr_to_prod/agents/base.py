"""Base agent class."""

import logging
from typing import Any

from pr_to_prod.models import AgentRole, WorkflowState
from pr_to_prod.providers.base import BaseLLMProvider, LLMMessage
from pr_to_prod.tools.gateway import ToolGateway

logger = logging.getLogger(__name__)


class BaseAgent:
    """Base class for all specialist agents."""

    def __init__(
        self,
        role: AgentRole,
        llm_provider: BaseLLMProvider,
        model: str,
        gateway: ToolGateway,
    ):
        self.role = role
        self.llm_provider = llm_provider
        self.model = model
        self.gateway = gateway

    async def execute(self, state: WorkflowState) -> dict[str, Any]:
        """Execute the agent's task."""
        raise NotImplementedError("Subclasses must implement execute()")

    async def call_llm(self, system_prompt: str, user_prompt: str) -> str:
        """Call the LLM with system and user prompts."""
        messages = [
            LLMMessage(role="system", content=system_prompt),
            LLMMessage(role="user", content=user_prompt),
        ]

        response = await self.llm_provider.generate(
            messages=messages,
            model=self.model,
            temperature=0.7,
        )

        return response.content

    async def call_tool(self, tool_name: str, **params: Any) -> Any:
        """Call a tool through the gateway with permission checking."""
        return await self.gateway.call_tool(
            agent_role=self.role,
            tool_name=tool_name,
            **params,
        )
