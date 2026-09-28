"""Tests for the tool gateway permission enforcement."""

import pytest

from pr_to_prod.models import AgentPermission, AgentRole
from pr_to_prod.tools.gateway import ToolGateway


@pytest.fixture
def gateway():
    """Create a tool gateway for testing."""
    return ToolGateway()


@pytest.fixture
def gateway_with_tool(gateway):
    """Gateway with a registered test tool."""

    async def test_tool(value: str) -> str:
        return f"processed: {value}"

    gateway.register_tool("test_tool", AgentPermission.READ_FILE, test_tool)
    return gateway


@pytest.mark.asyncio
async def test_permission_allowed(gateway_with_tool):
    """Test that agents with correct permission can call tools."""
    result = await gateway_with_tool.call_tool(
        agent_role=AgentRole.PLANNER,
        tool_name="test_tool",
        value="test",
    )
    assert result == "processed: test"


@pytest.mark.asyncio
async def test_permission_denied(gateway_with_tool):
    """Test that agents without permission cannot call tools."""
    with pytest.raises(PermissionError, match="does not have permission"):
        await gateway_with_tool.call_tool(
            agent_role=AgentRole.REPORTER,
            tool_name="test_tool",
            value="test",
        )


@pytest.mark.asyncio
async def test_unknown_tool(gateway):
    """Test that calling unknown tool raises ValueError."""
    with pytest.raises(ValueError, match="Unknown tool"):
        await gateway.call_tool(
            agent_role=AgentRole.PLANNER,
            tool_name="nonexistent_tool",
        )


@pytest.mark.asyncio
async def test_audit_log_success(gateway_with_tool):
    """Test that successful calls are logged."""
    await gateway_with_tool.call_tool(
        agent_role=AgentRole.PLANNER,
        tool_name="test_tool",
        value="test",
    )

    logs = gateway_with_tool.get_audit_log()
    assert len(logs) == 1
    assert logs[0].allowed is True
    assert logs[0].agent_role == AgentRole.PLANNER
    assert logs[0].tool_name == "test_tool"
    assert logs[0].result == "Success"


@pytest.mark.asyncio
async def test_audit_log_denied(gateway_with_tool):
    """Test that denied calls are logged."""
    with pytest.raises(PermissionError):
        await gateway_with_tool.call_tool(
            agent_role=AgentRole.REPORTER,
            tool_name="test_tool",
            value="test",
        )

    logs = gateway_with_tool.get_audit_log()
    assert len(logs) == 1
    assert logs[0].allowed is False
    assert logs[0].error == "Permission denied"


@pytest.mark.asyncio
async def test_sensitive_params_sanitized(gateway_with_tool):
    """Test that sensitive parameters are redacted in logs."""
    await gateway_with_tool.call_tool(
        agent_role=AgentRole.PLANNER,
        tool_name="test_tool",
        value="test",
        github_token="secret123",
    )

    logs = gateway_with_tool.get_audit_log()
    assert "secret123" not in str(logs[0].params)
    assert "***REDACTED***" in str(logs[0].params)


def test_planner_permissions():
    """Test that planner has read-only permissions."""
    from pr_to_prod.models import AGENT_PERMISSIONS

    perms = AGENT_PERMISSIONS[AgentRole.PLANNER]
    assert AgentPermission.READ_FILE in perms
    assert AgentPermission.WRITE_FILE not in perms
    assert AgentPermission.MERGE_PR not in perms


def test_coder_permissions():
    """Test that coder can push branches but not merge."""
    from pr_to_prod.models import AGENT_PERMISSIONS

    perms = AGENT_PERMISSIONS[AgentRole.CODER]
    assert AgentPermission.WRITE_FILE in perms
    assert AgentPermission.PUSH_BRANCH in perms
    assert AgentPermission.MERGE_PR not in perms


def test_deployer_permissions():
    """Test that deployer can merge and deploy but not write code."""
    from pr_to_prod.models import AGENT_PERMISSIONS

    perms = AGENT_PERMISSIONS[AgentRole.DEPLOYER]
    assert AgentPermission.MERGE_PR in perms
    assert AgentPermission.TRIGGER_DEPLOY in perms
    assert AgentPermission.WRITE_FILE not in perms
