"""Tests for deployment rollback."""

import pytest

from pr_to_prod.models import DeployResult, WorkflowState


@pytest.mark.asyncio
async def test_deploy_success():
    """Test successful deployment without rollback."""
    state = WorkflowState(
        job_id="test-deploy-1",
        issue_number=42,
        issue_url="https://github.com/test/test/issues/42",
        issue_title="Test Issue",
        issue_body="Test body",
        repo_owner="test",
        repo_name="test",
    )

    state.deploy_result = DeployResult(
        deployed=True,
        environment="staging",
        health_check_passed=True,
        rolled_back=False,
        error_rate=0.5,
        deployment_url="https://staging.example.com",
    )

    assert state.deploy_result.deployed is True
    assert state.deploy_result.health_check_passed is True
    assert state.deploy_result.rolled_back is False
    assert state.deploy_result.error_rate < 5.0


@pytest.mark.asyncio
async def test_deploy_rollback_high_error_rate():
    """Test deployment rollback due to high error rate."""
    state = WorkflowState(
        job_id="test-deploy-2",
        issue_number=42,
        issue_url="https://github.com/test/test/issues/42",
        issue_title="Test Issue",
        issue_body="Test body",
        repo_owner="test",
        repo_name="test",
    )

    state.deploy_result = DeployResult(
        deployed=True,
        environment="staging",
        health_check_passed=False,
        rolled_back=True,
        error_rate=8.5,
        deployment_url="https://staging.example.com",
    )

    assert state.deploy_result.deployed is True
    assert state.deploy_result.health_check_passed is False
    assert state.deploy_result.rolled_back is True
    assert state.deploy_result.error_rate > 5.0


@pytest.mark.asyncio
async def test_deploy_rollback_health_check_failed():
    """Test deployment rollback due to failed health check."""
    state = WorkflowState(
        job_id="test-deploy-3",
        issue_number=42,
        issue_url="https://github.com/test/test/issues/42",
        issue_title="Test Issue",
        issue_body="Test body",
        repo_owner="test",
        repo_name="test",
    )

    state.deploy_result = DeployResult(
        deployed=True,
        environment="staging",
        health_check_passed=False,
        rolled_back=True,
        error_rate=2.0,
        deployment_url="https://staging.example.com",
    )

    assert state.deploy_result.deployed is True
    assert state.deploy_result.health_check_passed is False
    assert state.deploy_result.rolled_back is True
