"""Reporter agent - summarizes the workflow results."""

import logging
from typing import Any

from pr_to_prod.agents.base import BaseAgent
from pr_to_prod.models import AgentRole, WorkflowState

logger = logging.getLogger(__name__)


class ReporterAgent(BaseAgent):
    """
    Reporter agent with permission to comment on issues.
    Summarizes the entire workflow and reports results.
    """

    def __init__(self, *args: Any, **kwargs: Any):
        super().__init__(AgentRole.REPORTER, *args, **kwargs)

    async def execute(self, state: WorkflowState) -> dict[str, Any]:
        """Generate and post a summary report."""
        logger.info(f"Reporter: Creating summary for issue #{state.issue_number}")

        system_prompt = """You are a technical writer creating clear, concise summaries.
Summarize the workflow execution in a professional tone.
Include key metrics and outcomes.
"""

        user_prompt = f"""Create a summary report for this workflow:

**Issue:** #{state.issue_number} - {state.issue_title}

**Plan:** {state.plan.summary if state.plan else 'N/A'}

**Code Changes:**
- Branch: {state.code_change.branch_name if state.code_change else 'N/A'}
- Files: {len(state.code_change.files_changed) if state.code_change else 0}
- PR: #{state.code_change.pr_number if state.code_change else 'N/A'}

**Review:** {"Approved" if state.review_result and state.review_result.approved else "N/A"}

**Tests:** {"Passed" if state.test_result and state.test_result.passed else "N/A"}

**Deployment:** {"Successful" if state.deploy_result and state.deploy_result.deployed else "N/A"}

**Token Usage:** {state.token_usage.total_tokens} tokens (${state.token_usage.estimated_cost_usd:.2f})

**Retries:** {state.retry_count_total}

Create a concise summary comment.
"""

        summary = await self.call_llm(system_prompt, user_prompt)

        report = f"""## 🤖 PR-to-Production Workflow Summary

{summary}

---

### Metrics
- **Total Tokens:** {state.token_usage.total_tokens:,}
- **Estimated Cost:** ${state.token_usage.estimated_cost_usd:.2f}
- **Retries:** {state.retry_count_total}
- **Duration:** {(state.completed_at - state.started_at).total_seconds():.0f}s

### Links
{f"- **Pull Request:** {state.code_change.pr_url}" if state.code_change else ""}
{f"- **Deployment:** {state.deploy_result.deployment_url}" if state.deploy_result else ""}

*Automated by PR-to-Production Agent Team*
"""

        await self.call_tool(
            "comment_issue",
            owner=state.repo_owner,
            repo=state.repo_name,
            issue_number=state.issue_number,
            comment=report,
        )

        logger.info(f"Reporter: Posted summary to issue #{state.issue_number}")

        return {"report_posted": True}
