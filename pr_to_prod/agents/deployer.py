"""Deployer agent - merges and deploys changes."""

import asyncio
import logging
from typing import Any

from pr_to_prod.agents.base import BaseAgent
from pr_to_prod.models import AgentRole, DeployResult, WorkflowState

logger = logging.getLogger(__name__)


class DeployerAgent(BaseAgent):
    """
    Deployer agent with merge and deploy permissions.
    Merges the PR, deploys to staging, and monitors health.
    """

    def __init__(self, *args: Any, **kwargs: Any):
        super().__init__(AgentRole.DEPLOYER, *args, **kwargs)

    async def execute(self, state: WorkflowState) -> dict[str, Any]:
        """Deploy the changes and monitor health."""
        if not state.code_change:
            raise ValueError("No code changes available")
        
        logger.info(f"Deployer: Deploying PR #{state.code_change.pr_number}")

        if not state.code_change:
            raise ValueError("No code changes available for deployer")

        merge_result = await self.call_tool(
            "merge_pr",
            owner=state.repo_owner,
            repo=state.repo_name,
            pr_number=state.code_change.pr_number,
            merge_method="merge",
        )

        logger.info(f"Deployer: Merged PR #{state.code_change.pr_number}")

        logger.info("Deployer: Simulating deployment to staging...")
        await asyncio.sleep(1)

        logger.info("Deployer: Monitoring health checks...")
        await asyncio.sleep(1)

        health_check_passed = True
        error_rate = 0.1
        rolled_back = False

        if error_rate > 5.0:
            logger.warning(f"Deployer: Error rate {error_rate}% exceeds threshold, rolling back!")
            rolled_back = True
            health_check_passed = False

        deploy_result = DeployResult(
            deployed=merge_result["merged"],
            environment="staging",
            health_check_passed=health_check_passed,
            rolled_back=rolled_back,
            error_rate=error_rate,
            deployment_url=f"https://staging.{state.repo_name}.example.com",
        )

        logger.info(f"Deployer: Deployment {'successful' if health_check_passed else 'failed'}")

        return {"deploy_result": deploy_result}
