"""Planner agent - creates the implementation plan."""

import json
import logging
from typing import Any

from pr_to_prod.agents.base import BaseAgent
from pr_to_prod.models import AgentRole, Plan, WorkflowState

logger = logging.getLogger(__name__)


class PlannerAgent(BaseAgent):
    """
    Planner agent with read-only access.
    Analyzes the issue and creates a structured plan.
    """

    def __init__(self, *args: Any, **kwargs: Any):
        super().__init__(AgentRole.PLANNER, *args, **kwargs)

    async def execute(self, state: WorkflowState) -> dict[str, Any]:
        """Create a plan for implementing the issue."""
        logger.info(f"Planner: Creating plan for issue #{state.issue_number}")

        repo_info = await self.call_tool(
            "read_repo",
            owner=state.repo_owner,
            repo=state.repo_name,
        )

        code_search_results = await self.call_tool(
            "search_code",
            owner=state.repo_owner,
            repo=state.repo_name,
            query="main",
        )

        system_prompt = """You are a software architect creating implementation plans.
Your job is to analyze a GitHub issue and create a detailed, structured plan.

You have READ-ONLY access to the repository.
Focus on:
- Which files need to be changed
- Clear acceptance criteria
- Required tests
- Potential risks

Respond with a JSON object containing:
- summary: Brief overview of the changes
- files_to_change: List of file paths
- acceptance_criteria: List of criteria
- tests_needed: List of test descriptions
- estimated_complexity: "low", "medium", or "high"
- risks: List of potential risks
"""

        user_prompt = f"""Issue #{state.issue_number}: {state.issue_title}

{state.issue_body}

Repository: {repo_info['full_name']}
Default branch: {repo_info['default_branch']}
Language: {repo_info['language']}

Found {len(code_search_results)} relevant code files.

Create a detailed implementation plan.
"""

        response = await self.call_llm(system_prompt, user_prompt)

        try:
            plan_data = json.loads(response)
        except json.JSONDecodeError:
            if "```json" in response:
                json_text = response.split("```json")[1].split("```")[0].strip()
                plan_data = json.loads(json_text)
            elif "```" in response:
                json_text = response.split("```")[1].split("```")[0].strip()
                plan_data = json.loads(json_text)
            else:
                plan_data = {
                    "summary": response[:200],
                    "files_to_change": ["app/main.py"],
                    "acceptance_criteria": ["Feature implemented"],
                    "tests_needed": ["Unit tests"],
                    "estimated_complexity": "medium",
                    "risks": [],
                }

        plan = Plan(**plan_data)
        
        logger.info(f"Planner: Created plan with {len(plan.files_to_change)} files to change")

        return {"plan": plan}
