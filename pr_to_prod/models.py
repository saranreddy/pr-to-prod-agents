"""Core data models for the PR-to-Production agent system."""

from datetime import UTC, datetime
from enum import StrEnum

from pydantic import BaseModel, Field


class AgentRole(StrEnum):
    """Agent roles with corresponding permissions."""

    PLANNER = "planner"
    CODER = "coder"
    REVIEWER = "reviewer"
    TESTER = "tester"
    DEPLOYER = "deployer"
    REPORTER = "reporter"


class WorkflowStep(StrEnum):
    """Steps in the PR-to-production workflow."""

    PLAN = "plan"
    CODE = "code"
    REVIEW = "review"
    TEST = "test"
    AWAIT_APPROVAL = "await_approval"
    DEPLOY = "deploy"
    REPORT = "report"
    FAILED = "failed"
    COMPLETED = "completed"


class AgentPermission(StrEnum):
    """Granular permissions for tool gateway."""

    READ_REPO = "read_repo"
    SEARCH_CODE = "search_code"
    READ_FILE = "read_file"
    WRITE_FILE = "write_file"
    PUSH_BRANCH = "push_branch"
    CREATE_PR = "create_pr"
    COMMENT_PR = "comment_pr"
    REVIEW_PR = "review_pr"
    MERGE_PR = "merge_pr"
    READ_CI = "read_ci"
    TRIGGER_DEPLOY = "trigger_deploy"
    READ_HEALTH = "read_health"
    COMMENT_ISSUE = "comment_issue"


AGENT_PERMISSIONS: dict[AgentRole, list[AgentPermission]] = {
    AgentRole.PLANNER: [
        AgentPermission.READ_REPO,
        AgentPermission.SEARCH_CODE,
        AgentPermission.READ_FILE,
    ],
    AgentRole.CODER: [
        AgentPermission.READ_REPO,
        AgentPermission.SEARCH_CODE,
        AgentPermission.READ_FILE,
        AgentPermission.WRITE_FILE,
        AgentPermission.PUSH_BRANCH,
        AgentPermission.CREATE_PR,
    ],
    AgentRole.REVIEWER: [
        AgentPermission.READ_REPO,
        AgentPermission.READ_FILE,
        AgentPermission.COMMENT_PR,
        AgentPermission.REVIEW_PR,
    ],
    AgentRole.TESTER: [
        AgentPermission.READ_REPO,
        AgentPermission.READ_FILE,
        AgentPermission.WRITE_FILE,
        AgentPermission.PUSH_BRANCH,
        AgentPermission.READ_CI,
    ],
    AgentRole.DEPLOYER: [
        AgentPermission.READ_REPO,
        AgentPermission.MERGE_PR,
        AgentPermission.TRIGGER_DEPLOY,
        AgentPermission.READ_HEALTH,
    ],
    AgentRole.REPORTER: [
        AgentPermission.READ_REPO,
        AgentPermission.COMMENT_ISSUE,
    ],
}


class Plan(BaseModel):
    """Structured plan from the planner agent."""

    summary: str
    files_to_change: list[str]
    acceptance_criteria: list[str]
    tests_needed: list[str]
    estimated_complexity: str
    risks: list[str] = Field(default_factory=list)


class CodeChange(BaseModel):
    """Code changes made by the coder agent."""

    branch_name: str
    files_changed: list[str]
    pr_number: int | None = None
    pr_url: str | None = None
    commit_sha: str | None = None


class ReviewResult(BaseModel):
    """Review result from the reviewer agent."""

    approved: bool
    comments: list[str]
    issues_found: list[str] = Field(default_factory=list)
    suggestions: list[str] = Field(default_factory=list)


class TestResult(BaseModel):
    """Test results from the tester agent."""

    passed: bool
    tests_added: list[str]
    tests_passed: int
    tests_failed: int
    failure_details: list[str] = Field(default_factory=list)
    ci_run_url: str | None = None


class DeployResult(BaseModel):
    """Deployment result from the deployer agent."""

    deployed: bool
    environment: str
    health_check_passed: bool
    rolled_back: bool = False
    error_rate: float | None = None
    deployment_url: str | None = None


class ApprovalDecision(BaseModel):
    """Human approval decision."""

    approved: bool
    reviewer: str
    comments: str | None = None
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))


class TokenUsage(BaseModel):
    """Token usage tracking."""

    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    estimated_cost_usd: float = 0.0


class WorkflowState(BaseModel):
    """Complete state for the LangGraph workflow."""

    job_id: str
    issue_number: int
    issue_url: str
    issue_title: str
    issue_body: str
    repo_owner: str
    repo_name: str
    base_branch: str = "main"

    current_step: WorkflowStep = WorkflowStep.PLAN
    error: str | None = None

    plan: Plan | None = None
    code_change: CodeChange | None = None
    review_result: ReviewResult | None = None
    test_result: TestResult | None = None
    approval: ApprovalDecision | None = None
    deploy_result: DeployResult | None = None

    retry_count_coder: int = 0
    retry_count_reviewer: int = 0
    retry_count_total: int = 0

    max_retries_coder: int = 3
    max_retries_reviewer: int = 3
    max_retries_total: int = 10

    token_usage: TokenUsage = Field(default_factory=TokenUsage)

    started_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    completed_at: datetime | None = None

    auto_approve_demo: bool = False  # For demo mode auto-approval

    messages: list[str] = Field(default_factory=list)

    model_config = {"arbitrary_types_allowed": True}

    def add_message(self, message: str) -> None:
        """Add a message to the workflow log."""
        self.messages.append(f"[{datetime.now(UTC).isoformat()}] {message}")

    def is_retry_exhausted(self) -> bool:
        """Check if retry limits are exhausted."""
        return (
            self.retry_count_coder >= self.max_retries_coder
            or self.retry_count_total >= self.max_retries_total
        )
