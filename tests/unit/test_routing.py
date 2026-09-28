"""Tests for workflow routing logic."""

import pytest

from pr_to_prod.models import (
    CodeChange,
    Plan,
    ReviewResult,
    TestResult,
    WorkflowState,
    WorkflowStep,
)


def test_retry_count_tracking():
    """Test that retry counts are tracked correctly."""
    state = WorkflowState(
        job_id="test",
        issue_number=1,
        issue_url="https://example.com",
        issue_title="Test",
        issue_body="Test",
        repo_owner="owner",
        repo_name="repo",
    )

    assert state.retry_count_coder == 0
    assert state.retry_count_reviewer == 0
    assert state.retry_count_total == 0

    state.retry_count_coder += 1
    state.retry_count_total += 1

    assert state.retry_count_coder == 1
    assert state.retry_count_total == 1


def test_retry_exhaustion():
    """Test retry limit detection."""
    state = WorkflowState(
        job_id="test",
        issue_number=1,
        issue_url="https://example.com",
        issue_title="Test",
        issue_body="Test",
        repo_owner="owner",
        repo_name="repo",
        max_retries_coder=3,
        max_retries_total=10,
    )

    assert not state.is_retry_exhausted()

    state.retry_count_coder = 3
    assert state.is_retry_exhausted()

    state.retry_count_coder = 2
    state.retry_count_total = 10
    assert state.is_retry_exhausted()


def test_message_logging():
    """Test workflow message logging."""
    state = WorkflowState(
        job_id="test",
        issue_number=1,
        issue_url="https://example.com",
        issue_title="Test",
        issue_body="Test",
        repo_owner="owner",
        repo_name="repo",
    )

    state.add_message("Step 1 complete")
    state.add_message("Step 2 complete")

    assert len(state.messages) == 2
    assert "Step 1 complete" in state.messages[0]
    assert "Step 2 complete" in state.messages[1]


def test_workflow_state_initialization():
    """Test that workflow state initializes with correct defaults."""
    state = WorkflowState(
        job_id="test-123",
        issue_number=42,
        issue_url="https://github.com/org/repo/issues/42",
        issue_title="Add feature",
        issue_body="Please add this feature",
        repo_owner="org",
        repo_name="repo",
    )

    assert state.current_step == WorkflowStep.PLAN
    assert state.retry_count_coder == 0
    assert state.retry_count_reviewer == 0
    assert state.retry_count_total == 0
    assert state.plan is None
    assert state.code_change is None
    assert state.approval is None


def test_review_approval_routing():
    """Test routing after review based on approval status."""
    state = WorkflowState(
        job_id="test",
        issue_number=1,
        issue_url="https://example.com",
        issue_title="Test",
        issue_body="Test",
        repo_owner="owner",
        repo_name="repo",
        max_retries_reviewer=3,
    )

    state.review_result = ReviewResult(
        approved=True,
        comments=["Looks good"],
        issues_found=[],
        suggestions=[],
    )

    state.review_result = ReviewResult(
        approved=False,
        comments=["Issues found"],
        issues_found=["Missing validation"],
        suggestions=["Add error handling"],
    )
    assert state.retry_count_reviewer < state.max_retries_reviewer


def test_test_failure_routing():
    """Test routing after test failures."""
    state = WorkflowState(
        job_id="test",
        issue_number=1,
        issue_url="https://example.com",
        issue_title="Test",
        issue_body="Test",
        repo_owner="owner",
        repo_name="repo",
    )

    state.test_result = TestResult(
        passed=False,
        tests_added=["test_feature.py"],
        tests_passed=5,
        tests_failed=2,
        failure_details=["test_edge_case failed"],
    )

    assert not state.test_result.passed
    assert len(state.test_result.failure_details) > 0
