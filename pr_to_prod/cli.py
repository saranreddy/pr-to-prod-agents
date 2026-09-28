"""CLI interface for PR-to-Production agent system."""

import asyncio
import logging
import uuid

import typer
from rich.console import Console
from rich.logging import RichHandler

from pr_to_prod.config import get_settings
from pr_to_prod.models import ApprovalDecision, WorkflowState, WorkflowStep
from pr_to_prod.notifiers import create_notifier
from pr_to_prod.orchestration import WorkflowOrchestrator
from pr_to_prod.storage import CheckpointStorage
from pr_to_prod.tools import MockGitHubBackend, MockGitHubTools, ToolGateway

app = typer.Typer(help="PR-to-Production Agent Team CLI")
console = Console()

logging.basicConfig(
    level=logging.INFO,
    format="%(message)s",
    handlers=[RichHandler(rich_tracebacks=True, console=console)],
)
logger = logging.getLogger(__name__)


@app.command()
def run(
    issue_number: int = typer.Option(..., "--issue", help="GitHub issue number"),
    repo_owner: str | None = typer.Option(None, "--owner", help="Repository owner"),
    repo_name: str | None = typer.Option(None, "--repo", help="Repository name"),
    mock: bool = typer.Option(False, "--mock", help="Use mock GitHub backend"),
) -> None:
    """
    Start a PR-to-production workflow for a GitHub issue.
    """
    settings = get_settings()

    owner = repo_owner or settings.target_repo_owner
    repo = repo_name or settings.target_repo_name

    console.print(f"[bold blue]Starting workflow for issue #{issue_number}[/bold blue]")
    console.print(f"Repository: {owner}/{repo}")
    console.print(f"Mode: {'Mock' if mock else 'Real GitHub'}")

    asyncio.run(_run_workflow(issue_number, owner, repo, mock))


async def _run_workflow(
    issue_number: int,
    owner: str,
    repo: str,
    use_mock: bool,
) -> None:
    """Run the workflow asynchronously."""
    settings = get_settings()
    gateway = ToolGateway()

    if use_mock:
        backend = MockGitHubBackend()
        backend.init_repo(owner, repo)
        MockGitHubTools(backend, gateway)
    else:
        from pr_to_prod.tools.github_tools import GitHubTools

        token = settings.github_token
        if not token:
            console.print("[red]Error: GITHUB_TOKEN is required for real mode[/red]")
            raise typer.Exit(1)

        GitHubTools(token, gateway)

    job_id = f"job-{uuid.uuid4().hex[:8]}"

    state = WorkflowState(
        job_id=job_id,
        issue_number=issue_number,
        issue_url=f"https://github.com/{owner}/{repo}/issues/{issue_number}",
        issue_title="Add new feature",
        issue_body="Please add a new feature to the application.",
        repo_owner=owner,
        repo_name=repo,
        base_branch=settings.default_base_branch,
        max_retries_coder=settings.max_retries_coder,
        max_retries_reviewer=settings.max_retries_reviewer,
    )

    orchestrator = WorkflowOrchestrator(settings, gateway)

    app_compiled = orchestrator.graph.compile()

    console.print(f"[green]Job {job_id} started[/green]")

    result_or_dict = await app_compiled.ainvoke(state)

    if isinstance(result_or_dict, dict):
        result = WorkflowState(**result_or_dict)
    else:
        result = result_or_dict

    console.print("\n[bold]Workflow Result:[/bold]")
    console.print(f"Status: {result.current_step.value}")
    console.print(f"Messages: {len(result.messages)}")

    for message in result.messages:
        console.print(f"  - {message}")

    if result.current_step == WorkflowStep.AWAIT_APPROVAL:
        notifier = create_notifier(
            settings.notifier_type,
            webhook_url=settings.slack_webhook_url,
            topic_arn=settings.sns_topic_arn,
        )
        await notifier.send_approval_request(result)


@app.command()
def demo(
    mock: bool = typer.Option(True, "--mock/--real", help="Use mock mode"),
) -> None:
    """
    Run an end-to-end demo of the workflow.
    """
    console.print("[bold green]Running PR-to-Production Demo[/bold green]\n")

    settings = get_settings()
    if not mock and not settings.github_token:
        console.print("[red]Error: GITHUB_TOKEN required for real mode[/red]")
        raise typer.Exit(1)

    asyncio.run(_run_demo(mock))


async def _run_demo(use_mock: bool) -> None:
    """Run the demo workflow."""
    settings = get_settings()
    gateway = ToolGateway()

    backend = MockGitHubBackend()
    backend.init_repo("example-org", "sample-app")
    MockGitHubTools(backend, gateway)

    job_id = f"demo-{uuid.uuid4().hex[:8]}"

    state = WorkflowState(
        job_id=job_id,
        issue_number=42,
        issue_url="https://github.com/example-org/sample-app/issues/42",
        issue_title="Add health check endpoint",
        issue_body="Add a /health endpoint that returns status 200 with {status: ok}",
        repo_owner="example-org",
        repo_name="sample-app",
        base_branch="main",
        auto_approve_demo=True,  # Enable auto-approval for demo
    )

    orchestrator = WorkflowOrchestrator(settings, gateway)
    app_compiled = orchestrator.graph.compile()

    console.print(f"[cyan]Demo Job: {job_id}[/cyan]\n")

    result = await app_compiled.ainvoke(state)

    if isinstance(result, dict):
        result = WorkflowState(**result)

    console.print("\n[bold green]Demo Workflow Complete![/bold green]\n")
    console.print(f"Final Status: {result.current_step.value}")
    console.print(f"Steps Executed: {len(result.messages)}")

    console.print("\n[bold]Workflow Log:[/bold]")
    for msg in result.messages:
        console.print(f"  {msg}")

    console.print("\n[bold]Audit Log:[/bold]")
    for log in gateway.get_audit_log()[:10]:
        console.print(f"  {log}")


@app.command()
def resume(
    job_id: str = typer.Option(..., "--job-id", help="Job ID to resume"),
    approve: bool = typer.Option(False, "--approve", help="Approve the workflow"),
    reject: bool = typer.Option(False, "--reject", help="Reject the workflow"),
    reviewer: str = typer.Option("human", "--reviewer", help="Reviewer name"),
) -> None:
    """
    Resume a paused workflow with an approval decision.
    """
    if not approve and not reject:
        console.print("[red]Error: Must specify --approve or --reject[/red]")
        raise typer.Exit(1)

    if approve and reject:
        console.print("[red]Error: Cannot both approve and reject[/red]")
        raise typer.Exit(1)

    console.print(f"[bold]Resuming job {job_id}[/bold]")
    console.print(f"Decision: {'✅ APPROVED' if approve else '❌ REJECTED'}")
    console.print(f"Reviewer: {reviewer}")

    console.print("\n[yellow]Note: Resume functionality requires checkpoint persistence[/yellow]")
    console.print(
        "[yellow]This is a placeholder - full implementation would load from database[/yellow]"
    )


async def _resume_workflow(job_id: str, approve: bool, reviewer: str) -> None:
    """Resume a paused workflow."""
    settings = get_settings()
    storage = CheckpointStorage(settings.database_url)

    state_dict = await storage.load_checkpoint(job_id)

    if not state_dict:
        console.print(f"[red]Error: No checkpoint found for job {job_id}[/red]")
        raise typer.Exit(1)

    state = WorkflowState(**state_dict)

    if state.current_step != WorkflowStep.AWAIT_APPROVAL:
        console.print(
            f"[yellow]Warning: Job is at step {state.current_step.value}, not awaiting approval[/yellow]"
        )

    state.approval = ApprovalDecision(
        approved=approve,
        reviewer=reviewer,
        comments="Approval via CLI resume",
    )

    gateway = ToolGateway()

    if "mock" in settings.llm_provider or not settings.github_token:
        backend = MockGitHubBackend()
        backend.init_repo(state.repo_owner, state.repo_name)
        MockGitHubTools(backend, gateway)
    else:
        from pr_to_prod.tools.github_tools import GitHubTools

        GitHubTools(settings.github_token, gateway)

    orchestrator = WorkflowOrchestrator(settings, gateway)
    app_compiled = orchestrator.graph.compile()

    console.print(f"\n[green]Resuming workflow for job {job_id}...[/green]")

    result_or_dict = await app_compiled.ainvoke(state)

    if isinstance(result_or_dict, dict):
        result = WorkflowState(**result_or_dict)
    else:
        result = result_or_dict

    console.print("\n[bold]Workflow Result:[/bold]")
    console.print(f"Status: {result.current_step.value}")

    for message in result.messages[-5:]:
        console.print(f"  {message}")


if __name__ == "__main__":
    app()
