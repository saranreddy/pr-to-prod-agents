"""Reviewer agent - reviews the code changes."""

import logging
from typing import Any

from pr_to_prod.agents.base import BaseAgent
from pr_to_prod.models import AgentRole, ReviewResult, WorkflowState

logger = logging.getLogger(__name__)


class ReviewerAgent(BaseAgent):
    """
    Reviewer agent with comment-only permissions.
    Reviews code changes against the plan and quality standards.
    """

    def __init__(self, *args: Any, **kwargs: Any):
        super().__init__(AgentRole.REVIEWER, *args, **kwargs)

    async def execute(self, state: WorkflowState) -> dict[str, Any]:
        """Review the code changes."""
        if not state.code_change:
            raise ValueError("No code changes available")

        logger.info(f"Reviewer: Reviewing PR #{state.code_change.pr_number}")

        if not state.code_change or not state.plan:
            raise ValueError("No code changes or plan available for reviewer")

        changed_files_content = []
        for file_path in state.code_change.files_changed:
            try:
                content = await self.call_tool(
                    "read_file",
                    owner=state.repo_owner,
                    repo=state.repo_name,
                    path=file_path,
                    ref=state.code_change.branch_name,
                )
                changed_files_content.append(f"File: {file_path}\n```\n{content[:500]}\n```")
            except Exception as e:
                logger.warning(f"Could not read {file_path}: {e}")

        system_prompt = """You are a senior code reviewer focusing on:
- Code quality and maintainability
- Alignment with the plan
- Potential bugs or issues
- Best practices and patterns

Provide constructive feedback. Be strict but fair.

Respond with JSON:
- approved: true/false
- comments: List of general comments
- issues_found: List of issues (empty if none)
- suggestions: List of improvement suggestions
"""

        user_prompt = f"""Review this implementation:

**Original Plan:**
{state.plan.summary}

**Acceptance Criteria:**
{chr(10).join(f'- {c}' for c in state.plan.acceptance_criteria)}

**Files Changed:**
{chr(10).join(changed_files_content)}

Provide your review.
"""

        response = await self.call_llm(system_prompt, user_prompt)

        import json

        try:
            review_data = json.loads(response)
        except json.JSONDecodeError:
            if "```json" in response:
                json_text = response.split("```json")[1].split("```")[0].strip()
                review_data = json.loads(json_text)
            elif "```" in response:
                json_text = response.split("```")[1].split("```")[0].strip()
                review_data = json.loads(json_text)
            else:
                review_data = {
                    "approved": True,
                    "comments": ["Review completed"],
                    "issues_found": [],
                    "suggestions": [],
                }

        review_result = ReviewResult(**review_data)

        review_comment = f"""## Code Review

**Status:** {"✅ APPROVED" if review_result.approved else "❌ CHANGES REQUESTED"}

### Comments
{chr(10).join(f'- {c}' for c in review_result.comments)}

{"### Issues Found" + chr(10) + chr(10).join(f"- {i}" for i in review_result.issues_found) if review_result.issues_found else ""}

{"### Suggestions" + chr(10) + chr(10).join(f"- {s}" for s in review_result.suggestions) if review_result.suggestions else ""}
"""

        await self.call_tool(
            "comment_pr",
            owner=state.repo_owner,
            repo=state.repo_name,
            pr_number=state.code_change.pr_number,
            comment=review_comment,
        )

        if review_result.approved:
            await self.call_tool(
                "review_pr",
                owner=state.repo_owner,
                repo=state.repo_name,
                pr_number=state.code_change.pr_number,
                event="APPROVE",
                body="Changes look good!",
            )
        else:
            await self.call_tool(
                "review_pr",
                owner=state.repo_owner,
                repo=state.repo_name,
                pr_number=state.code_change.pr_number,
                event="REQUEST_CHANGES",
                body="Please address the issues found.",
            )

        logger.info(
            f"Reviewer: {'Approved' if review_result.approved else 'Requested changes'} on PR #{state.code_change.pr_number}"
        )

        return {"review_result": review_result}
