"""Coder agent - implements the changes."""

import logging
from typing import Any

from pr_to_prod.agents.base import BaseAgent
from pr_to_prod.models import AgentRole, CodeChange, WorkflowState

logger = logging.getLogger(__name__)


class CoderAgent(BaseAgent):
    """
    Coder agent with permission to push to agent/* branches.
    Implements the planned changes and creates a PR.
    """

    def __init__(self, *args: Any, **kwargs: Any):
        super().__init__(AgentRole.CODER, *args, **kwargs)

    async def execute(self, state: WorkflowState) -> dict[str, Any]:
        """Implement the planned changes."""
        logger.info(f"Coder: Implementing changes for issue #{state.issue_number}")

        if not state.plan:
            raise ValueError("No plan available for coder agent")

        # Reuse existing branch and PR if available
        if state.code_change:
            branch_name = state.code_change.branch_name
            pr_number = state.code_change.pr_number
            pr_url = state.code_change.pr_url
            logger.info(f"Coder: Reusing existing branch {branch_name} and PR #{pr_number}")
        else:
            branch_name = f"agent/issue-{state.issue_number}-{state.issue_title[:30].lower().replace(' ', '-')}"
            branch_name = "".join(c for c in branch_name if c.isalnum() or c in ["-", "/"])

            await self.call_tool(
                "push_branch",
                owner=state.repo_owner,
                repo=state.repo_name,
                branch=branch_name,
                base_branch=state.base_branch,
            )

        files_changed = []
        for file_path in state.plan.files_to_change[:3]:
            try:
                existing_content = await self.call_tool(
                    "read_file",
                    owner=state.repo_owner,
                    repo=state.repo_name,
                    path=file_path,
                    ref=state.base_branch,
                )
            except Exception as e:
                logger.warning(f"Could not read {file_path}: {e}")
                existing_content = ""

            system_prompt = """You are an expert software engineer implementing features.
Write clean, maintainable code that follows best practices.
Preserve existing code structure and style.
"""

            user_prompt = f"""Implement changes for: {state.issue_title}

Plan: {state.plan.summary}

File: {file_path}
Existing content:
```
{existing_content}
```

Provide the complete updated file content.
Only output the code, no explanations.
"""

            new_content = await self.call_llm(system_prompt, user_prompt)

            if "```" in new_content:
                parts = new_content.split("```")
                for i, part in enumerate(parts):
                    if i % 2 == 1:
                        if "\n" in part:
                            new_content = part.split("\n", 1)[1].rsplit("\n", 1)[0]
                            break

            await self.call_tool(
                "write_file",
                owner=state.repo_owner,
                repo=state.repo_name,
                path=file_path,
                content=new_content,
                branch=branch_name,
                message=f"Implement: {state.issue_title}",
            )

            files_changed.append(file_path)
            logger.info(f"Coder: Updated {file_path}")

        pr_title = f"[Agent] {state.issue_title}"
        pr_body = f"""Automated PR created by PR-to-Production Agent Team

## Related Issue
Closes #{state.issue_number}

## Plan
{state.plan.summary}

## Files Changed
{chr(10).join(f'- {f}' for f in files_changed)}

## Acceptance Criteria
{chr(10).join(f'- [ ] {c}' for c in state.plan.acceptance_criteria)}
"""

        # Only create PR if this is the first time
        if not state.code_change:
            pr_info = await self.call_tool(
                "create_pr",
                owner=state.repo_owner,
                repo=state.repo_name,
                title=pr_title,
                body=pr_body,
                head=branch_name,
                base=state.base_branch,
            )
            pr_number = pr_info["number"]
            pr_url = pr_info["url"]
            logger.info(f"Coder: Created PR #{pr_number}")

        code_change = CodeChange(
            branch_name=branch_name,
            files_changed=files_changed,
            pr_number=pr_number,
            pr_url=pr_url,
        )

        logger.info(f"Coder: Updated {len(files_changed)} files on PR #{pr_number}")

        return {"code_change": code_change}
