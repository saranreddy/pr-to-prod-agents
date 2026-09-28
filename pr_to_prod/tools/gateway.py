"""Tool gateway with permission enforcement and audit logging."""

import logging
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

from pr_to_prod.models import AGENT_PERMISSIONS, AgentPermission, AgentRole

logger = logging.getLogger(__name__)


class AuditLog:
    """Audit log entry for tool usage."""

    def __init__(
        self,
        timestamp: datetime,
        agent_role: AgentRole,
        tool_name: str,
        permission: AgentPermission,
        allowed: bool,
        params: dict[str, Any],
        result: str | None = None,
        error: str | None = None,
    ):
        self.timestamp = timestamp
        self.agent_role = agent_role
        self.tool_name = tool_name
        self.permission = permission
        self.allowed = allowed
        self.params = params
        self.result = result
        self.error = error

    def __str__(self) -> str:
        status = "ALLOWED" if self.allowed else "DENIED"
        return (
            f"[{self.timestamp.isoformat()}] {status} - "
            f"{self.agent_role.value} called {self.tool_name} "
            f"(permission: {self.permission.value})"
        )


class ToolGateway:
    """
    Central gateway for all tool calls with permission enforcement.

    This ensures least-privilege access: each agent can only use tools
    that match their assigned permissions.
    """

    def __init__(self):
        self.audit_logs: list[AuditLog] = []
        self.tools: dict[str, tuple[AgentPermission, Callable]] = {}

    def register_tool(
        self,
        name: str,
        permission: AgentPermission,
        handler: Callable,
    ) -> None:
        """Register a tool with its required permission."""
        self.tools[name] = (permission, handler)
        logger.debug(f"Registered tool '{name}' requiring permission '{permission.value}'")

    def check_permission(self, agent_role: AgentRole, permission: AgentPermission) -> bool:
        """Check if an agent role has a specific permission."""
        allowed_permissions = AGENT_PERMISSIONS.get(agent_role, [])
        return permission in allowed_permissions

    async def call_tool(
        self,
        agent_role: AgentRole,
        tool_name: str,
        **params: Any,
    ) -> Any:
        """
        Call a tool with permission checking and audit logging.

        Args:
            agent_role: The role of the agent making the call
            tool_name: Name of the tool to call
            **params: Tool parameters

        Returns:
            Tool execution result

        Raises:
            PermissionError: If the agent doesn't have permission
            ValueError: If the tool doesn't exist
        """
        if tool_name not in self.tools:
            error = f"Unknown tool: {tool_name}"
            logger.error(error)
            raise ValueError(error)

        required_permission, handler = self.tools[tool_name]

        allowed = self.check_permission(agent_role, required_permission)

        timestamp = datetime.now(UTC)

        if not allowed:
            audit_entry = AuditLog(
                timestamp=timestamp,
                agent_role=agent_role,
                tool_name=tool_name,
                permission=required_permission,
                allowed=False,
                params=self._sanitize_params(params),
                error="Permission denied",
            )
            self.audit_logs.append(audit_entry)
            logger.warning(str(audit_entry))

            raise PermissionError(
                f"Agent role '{agent_role.value}' does not have permission "
                f"'{required_permission.value}' required for tool '{tool_name}'"
            )

        try:
            result = await handler(**params)

            audit_entry = AuditLog(
                timestamp=timestamp,
                agent_role=agent_role,
                tool_name=tool_name,
                permission=required_permission,
                allowed=True,
                params=self._sanitize_params(params),
                result="Success",
            )
            self.audit_logs.append(audit_entry)
            logger.info(str(audit_entry))

            return result

        except Exception as e:
            audit_entry = AuditLog(
                timestamp=timestamp,
                agent_role=agent_role,
                tool_name=tool_name,
                permission=required_permission,
                allowed=True,
                params=self._sanitize_params(params),
                error=str(e),
            )
            self.audit_logs.append(audit_entry)
            logger.error(f"{audit_entry} - Error: {e}")
            raise

    def _sanitize_params(self, params: dict[str, Any]) -> dict[str, Any]:
        """Sanitize parameters for logging (remove sensitive data)."""
        sanitized = {}
        for key, value in params.items():
            if any(
                sensitive in key.lower() for sensitive in ["token", "secret", "password", "key"]
            ):
                sanitized[key] = "***REDACTED***"
            elif isinstance(value, str) and len(value) > 100:
                sanitized[key] = value[:100] + "..."
            else:
                sanitized[key] = value
        return sanitized

    def get_audit_log(self) -> list[AuditLog]:
        """Get the complete audit log."""
        return self.audit_logs

    def export_audit_log(self) -> list[dict[str, Any]]:
        """Export audit log as a list of dictionaries."""
        return [
            {
                "timestamp": log.timestamp.isoformat(),
                "agent_role": log.agent_role.value,
                "tool_name": log.tool_name,
                "permission": log.permission.value,
                "allowed": log.allowed,
                "params": log.params,
                "result": log.result,
                "error": log.error,
            }
            for log in self.audit_logs
        ]
