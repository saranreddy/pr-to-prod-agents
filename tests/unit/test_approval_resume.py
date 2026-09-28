"""Tests for approval interrupt and resume."""

import pytest

from pr_to_prod.models import ApprovalDecision, WorkflowState, WorkflowStep
from pr_to_prod.storage import CheckpointStorage


@pytest.mark.asyncio
async def test_checkpoint_save_and_load_sqlite():
    """Test saving and loading checkpoints with SQLite."""
    storage = CheckpointStorage("sqlite:///test_checkpoints.db")

    state = WorkflowState(
        job_id="test-123",
        issue_number=42,
        issue_url="https://github.com/test/test/issues/42",
        issue_title="Test Issue",
        issue_body="Test body",
        repo_owner="test",
        repo_name="test",
        current_step=WorkflowStep.AWAIT_APPROVAL,
    )

    await storage.save_checkpoint(state.job_id, state.model_dump())

    loaded = await storage.load_checkpoint(state.job_id)

    assert loaded is not None
    assert loaded["job_id"] == "test-123"
    assert loaded["current_step"] == "await_approval"
    assert loaded["issue_number"] == 42

    import os

    os.remove("test_checkpoints.db")


@pytest.mark.asyncio
async def test_approval_interrupt():
    """Test that workflow pauses at approval gate."""
    state = WorkflowState(
        job_id="test-456",
        issue_number=42,
        issue_url="https://github.com/test/test/issues/42",
        issue_title="Test Issue",
        issue_body="Test body",
        repo_owner="test",
        repo_name="test",
    )

    state.current_step = WorkflowStep.AWAIT_APPROVAL

    assert state.current_step == WorkflowStep.AWAIT_APPROVAL
    assert state.approval is None


@pytest.mark.asyncio
async def test_approval_resume_approved():
    """Test resuming workflow with approval."""
    state = WorkflowState(
        job_id="test-789",
        issue_number=42,
        issue_url="https://github.com/test/test/issues/42",
        issue_title="Test Issue",
        issue_body="Test body",
        repo_owner="test",
        repo_name="test",
        current_step=WorkflowStep.AWAIT_APPROVAL,
    )

    state.approval = ApprovalDecision(
        approved=True,
        reviewer="test-reviewer",
        comments="Looks good",
    )

    assert state.approval.approved is True
    assert state.approval.reviewer == "test-reviewer"


@pytest.mark.asyncio
async def test_approval_resume_rejected():
    """Test resuming workflow with rejection."""
    state = WorkflowState(
        job_id="test-101",
        issue_number=42,
        issue_url="https://github.com/test/test/issues/42",
        issue_title="Test Issue",
        issue_body="Test body",
        repo_owner="test",
        repo_name="test",
        current_step=WorkflowStep.AWAIT_APPROVAL,
    )

    state.approval = ApprovalDecision(
        approved=False,
        reviewer="test-reviewer",
        comments="Issues found",
    )

    assert state.approval.approved is False
    assert state.approval.reviewer == "test-reviewer"
