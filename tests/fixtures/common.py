"""Fixtures for testing."""

import pytest


@pytest.fixture
def sample_issue():
    """Sample GitHub issue for testing."""
    return {
        "number": 42,
        "title": "Add health check endpoint",
        "body": "Create a /health endpoint that returns status 200 with {status: ok}",
        "url": "https://github.com/test-org/test-repo/issues/42",
    }


@pytest.fixture
def sample_plan():
    """Sample plan for testing."""
    from pr_to_prod.models import Plan

    return Plan(
        summary="Add health check endpoint to main application",
        files_to_change=["app/main.py"],
        acceptance_criteria=[
            "GET /health returns 200",
            "Response body contains {status: ok}",
        ],
        tests_needed=["test_health_endpoint"],
        estimated_complexity="low",
        risks=[],
    )
