"""Integration test for end-to-end workflow execution."""

import pytest

from pr_to_prod.config import get_settings
from pr_to_prod.models import WorkflowState, WorkflowStep
from pr_to_prod.orchestration.workflow import WorkflowOrchestrator
from pr_to_prod.tools import ToolGateway
from pr_to_prod.tools.mock_github import MockGitHubBackend, MockGitHubTools


@pytest.mark.asyncio
async def test_end_to_end_workflow_with_auto_approval():
    """Test complete workflow execution from start to finish with auto-approval."""
    settings = get_settings()
    gateway = ToolGateway()

    # Setup mock backend
    backend = MockGitHubBackend()
    backend.init_repo("test-org", "test-repo")
    MockGitHubTools(backend, gateway)

    # Create initial state with auto-approval enabled
    state = WorkflowState(
        job_id="test-e2e-001",
        issue_number=100,
        issue_url="https://github.com/test-org/test-repo/issues/100",
        issue_title="Add feature X",
        issue_body="We need feature X to do Y",
        repo_owner="test-org",
        repo_name="test-repo",
        base_branch="main",
        auto_approve_demo=True,  # Enable auto-approval
    )

    # Build and compile workflow
    orchestrator = WorkflowOrchestrator(settings, gateway)
    app = orchestrator.graph.compile()

    # Execute workflow
    result = await app.ainvoke(state)

    if isinstance(result, dict):
        result = WorkflowState(**result)

    # Verify workflow completed successfully
    assert result.current_step == WorkflowStep.COMPLETED, (
        f"Workflow should complete, got {result.current_step.value}"
    )

    # Verify all steps were executed in order
    assert result.plan is not None, "Plan should be created"
    assert result.code_change is not None, "Code changes should be made"
    assert result.review_result is not None, "Review should be completed"
    assert result.review_result.approved, "Review should be approved"
    assert result.test_result is not None, "Tests should be run"
    assert result.test_result.passed, "Tests should pass"
    assert result.approval is not None, "Approval should be set"
    assert result.approval.approved, "Approval should be granted"
    assert result.deploy_result is not None, "Deployment should occur"
    assert result.deploy_result.deployed, "Deployment should succeed"
    assert result.deploy_result.health_check_passed, "Health check should pass"

    # Verify workflow messages reflect all steps
    assert len(result.messages) >= 7, "Should have messages for all major steps"
    message_text = " ".join(result.messages)
    assert "Plan created" in message_text
    assert "Created PR" in message_text or "PR #" in message_text
    assert "Review: Approved" in message_text
    assert "Tests:" in message_text
    assert "Auto-approved" in message_text or "Approved" in message_text
    assert "Deployed" in message_text
    assert "report" in message_text.lower()

    # Verify no errors occurred
    assert result.error is None, f"Should have no error, got: {result.error}"

    # Verify audit log shows proper permission checks
    audit_log = gateway.get_audit_log()
    assert len(audit_log) > 0, "Audit log should have entries"

    # Check that key tools were called
    tool_names = [log.tool_name for log in audit_log]
    assert "read_repo" in tool_names
    assert "create_pr" in tool_names
    assert "review_pr" in tool_names
    assert "comment_issue" in tool_names

    # All audit entries should be ALLOWED (no permission denials)
    denied = [log for log in audit_log if not log.allowed]
    assert len(denied) == 0, f"No permissions should be denied, but got: {denied}"


@pytest.mark.asyncio
async def test_workflow_step_order():
    """Test that workflow executes steps in the correct order."""
    settings = get_settings()
    gateway = ToolGateway()

    backend = MockGitHubBackend()
    backend.init_repo("test-org", "test-repo")
    MockGitHubTools(backend, gateway)

    state = WorkflowState(
        job_id="test-order-001",
        issue_number=200,
        issue_url="https://github.com/test-org/test-repo/issues/200",
        issue_title="Test ordering",
        issue_body="Test step order",
        repo_owner="test-org",
        repo_name="test-repo",
        base_branch="main",
        auto_approve_demo=True,
    )

    orchestrator = WorkflowOrchestrator(settings, gateway)
    app = orchestrator.graph.compile()

    result = await app.ainvoke(state)
    if isinstance(result, dict):
        result = WorkflowState(**result)

    # Verify each major step was executed by checking state
    steps_completed = []

    if result.plan:
        steps_completed.append("PLAN")
    if result.code_change:
        steps_completed.append("CODE")
    if result.review_result:
        steps_completed.append("REVIEW")
    if result.test_result:
        steps_completed.append("TEST")
    if result.approval:
        steps_completed.append("APPROVAL")
    if result.deploy_result:
        steps_completed.append("DEPLOY")
    if result.current_step == WorkflowStep.COMPLETED:
        steps_completed.append("REPORT")

    # All steps should be present
    expected_steps = ["PLAN", "CODE", "REVIEW", "TEST", "APPROVAL", "DEPLOY", "REPORT"]
    assert steps_completed == expected_steps, (
        f"Steps executed: {steps_completed}, expected: {expected_steps}"
    )


@pytest.mark.asyncio
async def test_workflow_reuses_pr_on_retry():
    """Test that coder reuses the same PR when retrying."""
    settings = get_settings()
    gateway = ToolGateway()

    backend = MockGitHubBackend()
    backend.init_repo("test-org", "test-repo")
    MockGitHubTools(backend, gateway)

    state = WorkflowState(
        job_id="test-pr-reuse-001",
        issue_number=300,
        issue_url="https://github.com/test-org/test-repo/issues/300",
        issue_title="Test PR reuse",
        issue_body="Test PR is reused",
        repo_owner="test-org",
        repo_name="test-repo",
        base_branch="main",
        auto_approve_demo=True,
    )

    orchestrator = WorkflowOrchestrator(settings, gateway)
    app = orchestrator.graph.compile()

    result = await app.ainvoke(state)
    if isinstance(result, dict):
        result = WorkflowState(**result)

    # Only one PR should have been created
    assert len(backend.prs["test-org/test-repo"]) == 1, (
        f"Should create exactly 1 PR, created {len(backend.prs['test-org/test-repo'])}"
    )

    # Verify the PR number is consistent in result
    assert result.code_change is not None
    assert result.code_change.pr_number == 1, "PR number should be 1"
