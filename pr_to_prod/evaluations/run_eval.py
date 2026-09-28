"""Evaluation harness for PR-to-Production agent system."""

import asyncio
import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from rich.console import Console
from rich.table import Table

from pr_to_prod.config import get_settings
from pr_to_prod.evaluations.sample_issues import SAMPLE_ISSUES
from pr_to_prod.models import WorkflowState, WorkflowStep
from pr_to_prod.orchestration import WorkflowOrchestrator
from pr_to_prod.tools import MockGitHubBackend, MockGitHubTools, ToolGateway

logger = logging.getLogger(__name__)
console = Console()


class EvaluationResult:
    """Result of evaluating a single issue."""

    def __init__(
        self,
        issue_number: int,
        issue_title: str,
        complexity: str,
        success: bool,
        final_step: str,
        duration_seconds: float,
        retries: int,
        tokens_used: int,
        cost_usd: float,
        error: str | None = None,
    ):
        self.issue_number = issue_number
        self.issue_title = issue_title
        self.complexity = complexity
        self.success = success
        self.final_step = final_step
        self.duration_seconds = duration_seconds
        self.retries = retries
        self.tokens_used = tokens_used
        self.cost_usd = cost_usd
        self.error = error


class EvaluationHarness:
    """Harness for running evaluation against sample issues."""

    def __init__(self, provider: str = "mock", output_dir: str = "eval_results"):
        self.provider = provider
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(exist_ok=True)

    async def run_evaluation(
        self, issue_numbers: list[int] | None = None
    ) -> list[EvaluationResult]:
        """Run evaluation on specified or all issues."""
        console.print("[bold cyan]PR-to-Production Evaluation Harness[/bold cyan]\n")
        console.print(f"Provider: {self.provider}")
        console.print(f"Output: {self.output_dir}\n")

        issues_to_eval = SAMPLE_ISSUES
        if issue_numbers:
            issues_to_eval = [i for i in SAMPLE_ISSUES if i["number"] in issue_numbers]

        console.print(f"Evaluating {len(issues_to_eval)} issues...\n")

        results = []
        for idx, issue in enumerate(issues_to_eval, 1):
            console.print(
                f"[{idx}/{len(issues_to_eval)}] Issue #{issue['number']}: {issue['title']}"
            )

            try:
                result = await self._evaluate_issue(issue)
                results.append(result)

                status = "✅" if result.success else "❌"
                console.print(
                    f"  {status} {result.final_step} "
                    f"({result.duration_seconds:.1f}s, {result.tokens_used} tokens)\n"
                )

            except Exception as e:
                logger.error(f"Evaluation failed for issue #{issue['number']}: {e}")
                results.append(
                    EvaluationResult(
                        issue_number=int(str(issue.get("number", 0))),
                        issue_title=str(issue.get("title", "")),
                        complexity=str(issue.get("complexity", "medium")),
                        success=False,
                        final_step="ERROR",
                        duration_seconds=0,
                        retries=0,
                        tokens_used=0,
                        cost_usd=0,
                        error=str(e),
                    )
                )
                console.print(f"  ❌ ERROR: {e}\n")

        self._save_results(results)
        self._print_summary(results)

        return results

    async def _evaluate_issue(self, issue: dict[str, Any]) -> EvaluationResult:
        """Evaluate a single issue."""
        settings = get_settings()
        gateway = ToolGateway()  # type: ignore[no-untyped-call]

        backend = MockGitHubBackend()
        backend.init_repo("example-org", "sample-app")
        MockGitHubTools(backend, gateway)

        state = WorkflowState(
            job_id=f"eval-{issue['number']}",
            issue_number=issue["number"],
            issue_url=f"https://github.com/example-org/sample-app/issues/{issue['number']}",
            issue_title=issue["title"],
            issue_body=issue["body"],
            repo_owner="example-org",
            repo_name="sample-app",
        )

        orchestrator = WorkflowOrchestrator(settings, gateway)
        app_compiled = orchestrator.graph.compile()

        start_time = datetime.now(timezone.utc)
        result_state_or_dict = await app_compiled.ainvoke(state)
        end_time = datetime.now(timezone.utc)

        duration = (end_time - start_time).total_seconds()
        
        # Handle both dict and WorkflowState returns from LangGraph
        if isinstance(result_state_or_dict, dict):
            current_step_str = result_state_or_dict.get("current_step", "FAILED")
            success = current_step_str in ["await_approval", "completed"]
            final_step = current_step_str
            retry_count = result_state_or_dict.get("retry_count_total", 0)
            token_usage_data = result_state_or_dict.get("token_usage", {})
            tokens_used = token_usage_data.get("total_tokens", 0) if isinstance(token_usage_data, dict) else 0
            cost_usd = token_usage_data.get("estimated_cost_usd", 0.0) if isinstance(token_usage_data, dict) else 0.0
            error = result_state_or_dict.get("error")
        else:
            # WorkflowState object
            success = result_state_or_dict.current_step in [
                WorkflowStep.AWAIT_APPROVAL,
                WorkflowStep.COMPLETED,
            ]
            final_step = result_state_or_dict.current_step.value
            retry_count = result_state_or_dict.retry_count_total
            tokens_used = result_state_or_dict.token_usage.total_tokens if result_state_or_dict.token_usage else 0
            cost_usd = result_state_or_dict.token_usage.estimated_cost_usd if result_state_or_dict.token_usage else 0.0
            error = result_state_or_dict.error

        return EvaluationResult(
            issue_number=int(str(issue.get("number", 0))),
            issue_title=str(issue.get("title", "")),
            complexity=str(issue.get("complexity", "medium")),
            success=success,
            final_step=final_step,
            duration_seconds=duration,
            retries=retry_count,
            tokens_used=tokens_used,
            cost_usd=cost_usd,
            error=error,
        )

    def _save_results(self, results: list[EvaluationResult]) -> None:
        """Save results to JSON file."""
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        output_file = self.output_dir / f"eval_results_{timestamp}.json"

        data = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "provider": self.provider,
            "total_issues": len(results),
            "passed": sum(1 for r in results if r.success),
            "failed": sum(1 for r in results if not r.success),
            "pass_rate": sum(1 for r in results if r.success) / len(results) * 100,
            "total_tokens": sum(r.tokens_used for r in results),
            "total_cost": sum(r.cost_usd for r in results),
            "average_duration": sum(r.duration_seconds for r in results) / len(results),
            "results": [
                {
                    "issue_number": r.issue_number,
                    "title": r.issue_title,
                    "complexity": r.complexity,
                    "success": r.success,
                    "final_step": r.final_step,
                    "duration_seconds": r.duration_seconds,
                    "retries": r.retries,
                    "tokens_used": r.tokens_used,
                    "cost_usd": r.cost_usd,
                    "error": r.error,
                }
                for r in results
            ],
        }

        output_file.write_text(json.dumps(data, indent=2))
        console.print(f"\n[green]Results saved to: {output_file}[/green]")

    def _print_summary(self, results: list[EvaluationResult]) -> None:
        """Print evaluation summary."""
        passed = sum(1 for r in results if r.success)
        failed = sum(1 for r in results if not r.success)
        pass_rate = passed / len(results) * 100

        total_tokens = sum(r.tokens_used for r in results)
        total_cost = sum(r.cost_usd for r in results)
        avg_duration = sum(r.duration_seconds for r in results) / len(results)

        console.print("\n[bold]Evaluation Summary[/bold]")
        console.print(f"Total Issues:    {len(results)}")
        console.print(f"Passed:          {passed} ({pass_rate:.1f}%)")
        console.print(f"Failed:          {failed}")
        console.print(f"Total Tokens:    {total_tokens:,}")
        console.print(f"Total Cost:      ${total_cost:.2f}")
        console.print(f"Avg Duration:    {avg_duration:.1f}s")

        by_complexity: dict[str, list[EvaluationResult]] = {
        "low": [],
        "medium": [],
        "high": [],
    }
        for r in results:
            by_complexity[r.complexity].append(r)

        table = Table(title="\nResults by Complexity")
        table.add_column("Complexity")
        table.add_column("Total")
        table.add_column("Passed")
        table.add_column("Pass Rate")

        for complexity in ["low", "medium", "high"]:
            issues = by_complexity[complexity]
            if issues:
                passed_count = sum(1 for i in issues if i.success)
                rate = passed_count / len(issues) * 100
                table.add_row(
                    complexity.capitalize(),
                    str(len(issues)),
                    str(passed_count),
                    f"{rate:.1f}%",
                )

        console.print(table)


async def main(provider: str = "mock", issues: list[int] | None = None) -> None:
    """Run evaluation harness."""
    harness = EvaluationHarness(provider=provider)
    await harness.run_evaluation(issue_numbers=issues)


if __name__ == "__main__":
    import sys

    provider = sys.argv[1] if len(sys.argv) > 1 else "mock"
    asyncio.run(main(provider=provider))
