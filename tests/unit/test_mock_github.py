"""Tests for mock GitHub backend."""

import pytest

from pr_to_prod.models import AgentRole
from pr_to_prod.tools.gateway import ToolGateway
from pr_to_prod.tools.mock_github import MockGitHubBackend, MockGitHubTools


@pytest.fixture
def github_backend():
    """Create a mock GitHub backend."""
    backend = MockGitHubBackend()
    backend.init_repo("test-org", "test-repo")
    return backend


@pytest.fixture
def github_tools(github_backend):
    """Create mock GitHub tools."""
    gateway = ToolGateway()
    tools = MockGitHubTools(github_backend, gateway)
    return tools, gateway


@pytest.mark.asyncio
async def test_read_repo(github_tools):
    """Test reading repository info."""
    tools, gateway = github_tools

    result = await gateway.call_tool(
        AgentRole.PLANNER,
        "read_repo",
        owner="test-org",
        repo="test-repo",
    )

    assert result["name"] == "test-repo"
    assert result["full_name"] == "test-org/test-repo"


@pytest.mark.asyncio
async def test_read_file(github_tools):
    """Test reading a file."""
    tools, gateway = github_tools

    content = await gateway.call_tool(
        AgentRole.PLANNER,
        "read_file",
        owner="test-org",
        repo="test-repo",
        path="README.md",
    )

    assert "Sample App" in content


@pytest.mark.asyncio
async def test_write_file(github_tools):
    """Test writing a file."""
    tools, gateway = github_tools

    result = await gateway.call_tool(
        AgentRole.CODER,
        "write_file",
        owner="test-org",
        repo="test-repo",
        path="test.py",
        content="print('hello')",
        branch="main",
        message="Add test file",
    )

    assert result["path"] == "test.py"

    content = await gateway.call_tool(
        AgentRole.CODER,
        "read_file",
        owner="test-org",
        repo="test-repo",
        path="test.py",
    )

    assert content == "print('hello')"


@pytest.mark.asyncio
async def test_create_branch(github_tools):
    """Test creating a branch."""
    tools, gateway = github_tools

    result = await gateway.call_tool(
        AgentRole.CODER,
        "push_branch",
        owner="test-org",
        repo="test-repo",
        branch="feature/test",
    )

    assert result["branch"] == "feature/test"


@pytest.mark.asyncio
async def test_create_pr(github_tools):
    """Test creating a pull request."""
    tools, gateway = github_tools

    await gateway.call_tool(
        AgentRole.CODER,
        "push_branch",
        owner="test-org",
        repo="test-repo",
        branch="feature/test",
    )

    result = await gateway.call_tool(
        AgentRole.CODER,
        "create_pr",
        owner="test-org",
        repo="test-repo",
        title="Test PR",
        body="Test description",
        head="feature/test",
        base="main",
    )

    assert result["number"] == 1
    assert result["title"] == "Test PR"
    assert "test-org/test-repo/pull/1" in result["url"]


@pytest.mark.asyncio
async def test_comment_pr(github_tools):
    """Test commenting on a PR."""
    tools, gateway = github_tools

    await gateway.call_tool(
        AgentRole.CODER,
        "push_branch",
        owner="test-org",
        repo="test-repo",
        branch="feature/test",
    )

    pr = await gateway.call_tool(
        AgentRole.CODER,
        "create_pr",
        owner="test-org",
        repo="test-repo",
        title="Test PR",
        body="Test",
        head="feature/test",
        base="main",
    )

    result = await gateway.call_tool(
        AgentRole.REVIEWER,
        "comment_pr",
        owner="test-org",
        repo="test-repo",
        pr_number=pr["number"],
        comment="Looks good!",
    )

    assert result["id"] == 1


@pytest.mark.asyncio
async def test_merge_pr(github_tools):
    """Test merging a PR."""
    tools, gateway = github_tools

    await gateway.call_tool(
        AgentRole.CODER,
        "push_branch",
        owner="test-org",
        repo="test-repo",
        branch="feature/test",
    )

    pr = await gateway.call_tool(
        AgentRole.CODER,
        "create_pr",
        owner="test-org",
        repo="test-repo",
        title="Test PR",
        body="Test",
        head="feature/test",
        base="main",
    )

    result = await gateway.call_tool(
        AgentRole.DEPLOYER,
        "merge_pr",
        owner="test-org",
        repo="test-repo",
        pr_number=pr["number"],
    )

    assert result["merged"] is True


@pytest.mark.asyncio
async def test_ci_status(github_tools):
    """Test reading CI status."""
    tools, gateway = github_tools

    result = await gateway.call_tool(
        AgentRole.TESTER,
        "read_ci",
        owner="test-org",
        repo="test-repo",
        ref="main",
    )

    assert result["state"] == "success"
    assert len(result["statuses"]) > 0
