"""Unit tests for rollback functionality."""

import pytest

from pr_to_prod.agents.deployer import DeployerAgent
from pr_to_prod.config import get_settings
from pr_to_prod.models import (
    CodeChange,
    Plan,
    ReviewResult,
    TestResult,
    WorkflowState,
)
from pr_to_prod.providers.mock import MockProvider
from pr_to_prod.tools import ToolGateway
from pr_to_prod.tools.mock_github import MockGitHubBackend, MockGitHubTools


@pytest.mark.asyncio
async def test_deployer_rolls_back_on_simulated_unhealthy():
    """Test that deployer rolls back when simulate_unhealthy flag is set."""
    gateway = ToolGateway()

    backend = MockGitHubBackend()
    backend.init_repo("test-org", "test-repo")
    MockGitHubTools(backend, gateway)

    # Pre-create the PR in the mock backend
    pr = {
        "number": 1,
        "url": "https://github.com/test-org/test-repo/pull/1",
        "title": "Test PR",
        "body": "Test",
        "head": "test-branch",
        "base": "main",
        "state": "open",
        "comments": [],
    }
    backend.prs["test-org/test-repo"] = [pr]

    # Create workflow state with simulated unhealthy flag
    state = WorkflowState(
        job_id="test-rollback-001",
        issue_number=500,
        issue_url="https://github.com/test-org/test-repo/issues/500",
        issue_title="Test rollback",
        issue_body="Test rollback functionality",
        repo_owner="test-org",
        repo_name="test-repo",
        base_branch="main",
        simulate_unhealthy=True,  # Trigger rollback
        code_change=CodeChange(
            branch_name="test-branch",
            files_changed=["app/main.py"],
            pr_number=1,
            pr_url="https://github.com/test-org/test-repo/pull/1",
        ),
        plan=Plan(
            summary="Test plan",
            files_to_change=["app/main.py"],
            acceptance_criteria=["Works"],
            tests_needed=["Test it"],
            estimated_complexity="low",
        ),
        review_result=ReviewResult(
            approved=True,
            comments=["Looks good"],
        ),
        test_result=TestResult(
            passed=True,
            tests_added=["test_it.py"],
            tests_passed=1,
            tests_failed=0,
        ),
    )

    # Execute deployer
    llm_provider = MockProvider()
    deployer = DeployerAgent(
        llm_provider=llm_provider,
        model="mock-model",
        gateway=gateway,
    )

    result = await deployer.execute(state)

    # Verify rollback occurred
    deploy_result = result["deploy_result"]
    assert deploy_result.rolled_back is True, "Deployment should be rolled back"
    assert deploy_result.health_check_passed is False, "Health check should fail"
    assert deploy_result.rollback_reason is not None, "Should have rollback reason"
    assert "Simulated unhealthy" in deploy_result.rollback_reason
    assert deploy_result.error_rate == 25.0, "Error rate should be elevated"


@pytest.mark.asyncio
async def test_deployer_succeeds_without_simulate_unhealthy():
    """Test that deployer succeeds normally when simulate_unhealthy is False."""
    gateway = ToolGateway()

    backend = MockGitHubBackend()
    backend.init_repo("test-org", "test-repo")
    MockGitHubTools(backend, gateway)

    # Pre-create the PR in the mock backend
    pr = {
        "number": 1,
        "url": "https://github.com/test-org/test-repo/pull/1",
        "title": "Test PR",
        "body": "Test",
        "head": "test-branch",
        "base": "main",
        "state": "open",
        "comments": [],
    }
    backend.prs["test-org/test-repo"] = [pr]

    state = WorkflowState(
        job_id="test-success-001",
        issue_number=600,
        issue_url="https://github.com/test-org/test-repo/issues/600",
        issue_title="Test success",
        issue_body="Test normal deployment",
        repo_owner="test-org",
        repo_name="test-repo",
        base_branch="main",
        simulate_unhealthy=False,  # Normal deployment
        code_change=CodeChange(
            branch_name="test-branch",
            files_changed=["app/main.py"],
            pr_number=1,
            pr_url="https://github.com/test-org/test-repo/pull/1",
        ),
        plan=Plan(
            summary="Test plan",
            files_to_change=["app/main.py"],
            acceptance_criteria=["Works"],
            tests_needed=["Test it"],
            estimated_complexity="low",
        ),
        review_result=ReviewResult(
            approved=True,
            comments=["Looks good"],
        ),
        test_result=TestResult(
            passed=True,
            tests_added=["test_it.py"],
            tests_passed=1,
            tests_failed=0,
        ),
    )

    llm_provider = MockProvider()
    deployer = DeployerAgent(
        llm_provider=llm_provider,
        model="mock-model",
        gateway=gateway,
    )

    result = await deployer.execute(state)

    # Verify deployment succeeded
    deploy_result = result["deploy_result"]
    assert deploy_result.rolled_back is False, "Deployment should not be rolled back"
    assert deploy_result.health_check_passed is True, "Health check should pass"
    assert deploy_result.rollback_reason is None, "Should have no rollback reason"
    assert deploy_result.error_rate == 0.1, "Error rate should be low"


@pytest.mark.asyncio
async def test_end_to_end_rollback_workflow():
    """Test complete workflow with rollback simulation."""
    from pr_to_prod.orchestration.workflow import WorkflowOrchestrator

    settings = get_settings()
    gateway = ToolGateway()

    backend = MockGitHubBackend()
    backend.init_repo("test-org", "test-repo")
    MockGitHubTools(backend, gateway)

    state = WorkflowState(
        job_id="test-e2e-rollback-001",
        issue_number=700,
        issue_url="https://github.com/test-org/test-repo/issues/700",
        issue_title="Test E2E rollback",
        issue_body="Test end-to-end rollback",
        repo_owner="test-org",
        repo_name="test-repo",
        base_branch="main",
        auto_approve_demo=True,
        simulate_unhealthy=True,  # Trigger rollback
    )

    orchestrator = WorkflowOrchestrator(settings, gateway)
    app = orchestrator.graph.compile()

    result = await app.ainvoke(state)
    if isinstance(result, dict):
        result = WorkflowState(**result)

    # Verify workflow completed despite rollback
    assert (
        result.current_step.value == "completed"
    ), f"Workflow should complete even with rollback, got {result.current_step.value}"

    # Verify rollback occurred
    assert result.deploy_result is not None
    assert result.deploy_result.rolled_back is True
    assert result.deploy_result.health_check_passed is False
    assert "Simulated unhealthy" in result.deploy_result.rollback_reason

    # Verify workflow log mentions rollback
    workflow_log = " ".join(result.messages)
    assert "Failed" in workflow_log or "failed" in workflow_log
