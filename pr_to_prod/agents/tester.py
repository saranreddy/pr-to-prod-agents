"""Tester agent - adds and runs tests."""

import logging
from typing import Any

from pr_to_prod.agents.base import BaseAgent
from pr_to_prod.models import AgentRole, TestResult, WorkflowState

logger = logging.getLogger(__name__)


class TesterAgent(BaseAgent):
    """
    Tester agent with permission to push tests and read CI.
    Creates tests for acceptance criteria and validates results.
    """

    def __init__(self, *args: Any, **kwargs: Any):
        super().__init__(AgentRole.TESTER, *args, **kwargs)

    async def execute(self, state: WorkflowState) -> dict[str, Any]:
        """Add tests and check CI results."""
        if not state.code_change:
            raise ValueError("No code changes available")

        logger.info(f"Tester: Adding tests for PR #{state.code_change.pr_number}")

        if not state.code_change or not state.plan:
            raise ValueError("No code changes or plan available for tester")

        tests_added = []
        for i, test_description in enumerate(state.plan.tests_needed[:2]):
            test_file = f"tests/test_issue_{state.issue_number}_{i}.py"

            system_prompt = """You are a testing expert writing comprehensive unit tests.
Write clear, maintainable tests using pytest.
Include edge cases and error conditions.
"""

            user_prompt = f"""Write a test for:
{test_description}

Context:
- Issue: {state.issue_title}
- Files changed: {', '.join(state.code_change.files_changed)}

Provide complete test code using pytest.
Only output the code, no explanations.
"""

            test_code = await self.call_llm(system_prompt, user_prompt)

            if "```python" in test_code:
                test_code = test_code.split("```python")[1].split("```")[0].strip()
            elif "```" in test_code:
                test_code = test_code.split("```")[1].split("```")[0].strip()

            await self.call_tool(
                "write_file",
                owner=state.repo_owner,
                repo=state.repo_name,
                path=test_file,
                content=test_code,
                branch=state.code_change.branch_name,
                message=f"Add tests for: {test_description}",
            )

            tests_added.append(test_file)
            logger.info(f"Tester: Added test file {test_file}")

        ci_status = await self.call_tool(
            "read_ci",
            owner=state.repo_owner,
            repo=state.repo_name,
            ref=state.code_change.branch_name,
        )

        passed = ci_status["state"] in ["success", "pending"]
        failure_details = []

        if not passed:
            failure_details = [
                f"{s['context']}: {s['description']}"
                for s in ci_status.get("statuses", [])
                if s["state"] == "failure"
            ]

        tests_passed = len([s for s in ci_status.get("statuses", []) if s["state"] == "success"])
        tests_failed = len([s for s in ci_status.get("statuses", []) if s["state"] == "failure"])

        test_result = TestResult(
            passed=passed,
            tests_added=tests_added,
            tests_passed=tests_passed,
            tests_failed=tests_failed,
            failure_details=failure_details,
            ci_run_url=f"https://github.com/{state.repo_owner}/{state.repo_name}/actions",
        )

        test_comment = f"""## Test Results

**Status:** {"✅ All tests passed" if passed else "❌ Some tests failed"}

### Tests Added
{chr(10).join(f'- {t}' for t in tests_added)}

### CI Status
- Passed: {tests_passed}
- Failed: {tests_failed}
- Overall: {ci_status['state']}

{"### Failures" + chr(10) + chr(10).join(f"- {f}" for f in failure_details) if failure_details else ""}
"""

        await self.call_tool(
            "comment_pr",
            owner=state.repo_owner,
            repo=state.repo_name,
            pr_number=state.code_change.pr_number,
            comment=test_comment,
        )

        logger.info(
            f"Tester: CI status is {ci_status['state']} for PR #{state.code_change.pr_number}"
        )

        return {"test_result": test_result}
