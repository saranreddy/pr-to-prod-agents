# Architecture Documentation

## Table of Contents

1. [System Overview](#system-overview)
2. [Agent Architecture](#agent-architecture)
3. [Orchestration Layer](#orchestration-layer)
4. [Tool Gateway](#tool-gateway)
5. [LLM Provider Layer](#llm-provider-layer)
6. [Data Flow](#data-flow)
7. [Security Model](#security-model)
8. [Deployment Architecture](#deployment-architecture)
9. [Failure Handling](#failure-handling)
10. [Design Decisions](#design-decisions)

## System Overview

The PR-to-Production Agent Team is a multi-agent system that automates the complete software delivery pipeline from issue to deployed code. It follows a **supervisor pattern** with specialized agents, each having minimal permissions necessary for their role.

### Core Principles

1. **Least Privilege**: Each agent has only the permissions it needs
2. **Auditability**: Every tool call is logged with timestamp, agent, and outcome
3. **Resumability**: Workflow state is checkpointed for crash recovery
4. **Human Control**: Mandatory approval gate before deployment
5. **Determinism**: Mock mode enables reproducible testing

### High-Level Flow

```
GitHub Issue → Webhook → Queue → Orchestrator → [Agents] → Approval → Deploy → Report
```

## Agent Architecture

### Base Agent

All agents inherit from `BaseAgent`:

```python
class BaseAgent:
    role: AgentRole
    llm_provider: BaseLLMProvider
    model: str
    gateway: ToolGateway
    
    async def execute(state: WorkflowState) -> dict
    async def call_llm(system_prompt, user_prompt) -> str
    async def call_tool(tool_name, **params) -> Any
```

### Agent Roles

#### 1. Planner Agent (Read-Only)

**Purpose**: Analyze the issue and create a structured implementation plan.

**Permissions**:
- `READ_REPO`: Get repository metadata
- `SEARCH_CODE`: Search codebase for relevant files
- `READ_FILE`: Read file contents

**Outputs**: `Plan` object with:
- Summary of changes
- Files to modify
- Acceptance criteria
- Tests needed
- Estimated complexity
- Potential risks

**Why separate?**: Planning doesn't need write access. Enforcing read-only prevents accidental modifications.

#### 2. Coder Agent (Push to agent/* only)

**Purpose**: Implement the planned changes and create a PR.

**Permissions**:
- `READ_REPO`, `SEARCH_CODE`, `READ_FILE` (inherited)
- `WRITE_FILE`: Modify code
- `PUSH_BRANCH`: Create and push to `agent/*` branches
- `CREATE_PR`: Open draft pull requests

**Outputs**: `CodeChange` object with:
- Branch name
- Files changed
- PR number and URL
- Commit SHA

**Branch Naming**: `agent/issue-<number>-<slug>` ensures traceability.

**Why restricted?**: Cannot merge PRs or push to main, limiting damage from errors.

#### 3. Reviewer Agent (Comment-Only)

**Purpose**: Review code changes against quality standards and the plan.

**Permissions**:
- `READ_REPO`, `READ_FILE`
- `COMMENT_PR`: Add review comments
- `REVIEW_PR`: Submit approve/request changes

**Outputs**: `ReviewResult` object with:
- Approved (boolean)
- General comments
- Issues found
- Suggestions

**Review Loop**: If not approved, workflow returns to Coder (max 3 rounds).

**Why comment-only?**: Reviewer shouldn't modify code, only critique.

#### 4. Tester Agent (Push tests + read CI)

**Purpose**: Write acceptance tests and validate CI results.

**Permissions**:
- `READ_REPO`, `READ_FILE`, `WRITE_FILE`
- `PUSH_BRANCH`: Push test files to the PR branch
- `READ_CI`: Check CI status

**Outputs**: `TestResult` object with:
- Passed (boolean)
- Tests added
- Tests passed/failed counts
- Failure details
- CI run URL

**Test Naming**: `tests/test_issue_<number>_<index>.py` for traceability.

**Why separate from Coder?**: Testing is a distinct concern; separate agent provides clear responsibility.

#### 5. Deployer Agent (Merge + deploy)

**Purpose**: Merge the PR, deploy to staging, monitor health.

**Permissions**:
- `READ_REPO`
- `MERGE_PR`: Merge approved PRs
- `TRIGGER_DEPLOY`: Start deployment workflow
- `READ_HEALTH`: Check health metrics

**Outputs**: `DeployResult` object with:
- Deployed (boolean)
- Environment
- Health check passed
- Rolled back (if health failed)
- Error rate
- Deployment URL

**Health Monitoring**:
- Polls `/health` endpoint every 30s for 5 minutes
- Checks error rate < 5%
- Auto-rollback if threshold exceeded

**Why deploy permissions only?**: Deployer should never modify code, only ship it.

#### 6. Reporter Agent (Issue comments)

**Purpose**: Summarize workflow results back to the issue.

**Permissions**:
- `READ_REPO`
- `COMMENT_ISSUE`: Post to GitHub issues

**Outputs**: Summary report with:
- Workflow status
- PR link
- Deployment status
- Token usage and cost
- Retry count

**Why last?**: Ensures complete information for the summary.

## Orchestration Layer

### LangGraph Supervisor

The orchestrator uses LangGraph's `StateGraph` with typed state and conditional routing.

#### State Management

```python
class WorkflowState(BaseModel):
    job_id: str
    issue_number: int
    current_step: WorkflowStep
    
    plan: Optional[Plan]
    code_change: Optional[CodeChange]
    review_result: Optional[ReviewResult]
    test_result: Optional[TestResult]
    approval: Optional[ApprovalDecision]
    deploy_result: Optional[DeployResult]
    
    retry_count_coder: int
    retry_count_reviewer: int
    retry_count_total: int
    
    token_usage: TokenUsage
    messages: list[str]
```

#### Graph Structure

```
Plan → Code → Review → Test → Await Approval → Deploy → Report → END
          ↑      ↓        ↓
          └──────┴────────┘
       (retry loops, max 3 rounds)
```

#### Conditional Routing

Each step has a router function that decides the next step:

```python
def _after_review_router(state: WorkflowState) -> Literal["test", "code", "failed"]:
    if state.error:
        return "failed"
    if state.review_result.approved:
        return "test"
    elif state.retry_count_reviewer < state.max_retries_reviewer:
        state.retry_count_reviewer += 1
        return "code"
    else:
        return "failed"
```

#### Human-in-the-Loop

The `await_approval` node pauses execution:

1. Orchestrator reaches approval gate
2. Notifier sends summary (Slack/SNS/Console)
3. Workflow state saved to database
4. Human reviews and decides (approve/reject)
5. CLI `resume` command loads state and continues

**Implementation**:
- LangGraph's interrupt mechanism
- Durable state in Postgres/SQLite
- Resume by job ID

## Tool Gateway

The Tool Gateway enforces least-privilege access with a permission-based registry.

### Architecture

```python
class ToolGateway:
    tools: dict[str, tuple[AgentPermission, Callable]]
    audit_logs: list[AuditLog]
    
    def register_tool(name, permission, handler)
    async def call_tool(agent_role, tool_name, **params)
```

### Permission Check Flow

1. Agent calls `gateway.call_tool(role, tool_name, **params)`
2. Gateway looks up required permission for tool
3. Checks if agent role has that permission
4. If denied: logs and raises `PermissionError`
5. If allowed: executes tool, logs result
6. Returns result to agent

### Audit Logging

Every call generates an `AuditLog` entry:

```python
class AuditLog:
    timestamp: datetime
    agent_role: AgentRole
    tool_name: str
    permission: AgentPermission
    allowed: bool
    params: dict  # Sanitized (secrets redacted)
    result: Optional[str]
    error: Optional[str]
```

Logs can be exported for compliance and debugging.

### Mock vs Real Tools

The gateway is agnostic to tool implementation:

- **Mock**: `MockGitHubTools` simulates API responses (for testing)
- **Real**: `GitHubTools` calls actual GitHub API (for production)

Both register with the same gateway interface.

## LLM Provider Layer

### Provider Interface

```python
class BaseLLMProvider(ABC):
    async def generate(messages, model, temperature, max_tokens) -> LLMResponse
    def estimate_cost(prompt_tokens, completion_tokens, model) -> float
```

### Implementations

#### 1. Anthropic Provider

- Uses `AsyncAnthropic` client
- Maps messages to Claude API format
- Tracks usage and estimates cost

#### 2. Bedrock Provider

- Uses boto3 with bedrock-runtime
- Supports Claude models on AWS
- JSON body construction for Bedrock format

#### 3. Mock Provider

- Deterministic responses based on prompt keywords
- Zero cost (testing)
- Simulates token counting
- Enables offline development

### Model Selection

Each agent can use a different model:

```python
settings = get_settings()
model = settings.get_agent_model("coder")  # e.g., claude-3-5-sonnet
```

**Cost optimization**: Strong models (Sonnet) for coder/reviewer, cheaper models (Haiku) for planner/reporter.

## Data Flow

### Webhook Trigger

```
GitHub Issue (label: agent:build)
  → Webhook POST to API Gateway
  → Lambda validates signature
  → Message to SQS queue
  → Orchestrator polls queue
  → New WorkflowState created
  → Graph execution begins
```

### CLI Trigger

```
pr-to-prod run --issue 42
  → WorkflowState created directly
  → Graph execution begins
```

### Checkpoint Persistence

```
[Step Complete]
  → State serialized
  → Written to database (job_id as key)
  → Checkpoint ID stored

[Crash/Resume]
  → Load state by job_id
  → Deserialize WorkflowState
  → Resume from last completed step
```

Database schema:

```sql
CREATE TABLE checkpoints (
    job_id TEXT PRIMARY KEY,
    state JSONB,
    step TEXT,
    updated_at TIMESTAMP
);
```

## Security Model

### Principle: Defense in Depth

1. **Network**: VPC with private subnets for services
2. **Authentication**: GitHub tokens in Secrets Manager
3. **Authorization**: Tool Gateway enforces permissions
4. **Audit**: All actions logged with timestamps
5. **Isolation**: Sandbox tasks run in ephemeral Fargate containers

### Separate GitHub Apps (Production)

Each agent should use a distinct GitHub App:

| Agent | Permissions | Token Scope |
|-------|------------|-------------|
| Planner | Repository: Read-only | Metadata, contents |
| Coder | Repository: Write (agent/* only) | Contents, pull requests |
| Reviewer | Pull requests: Read, comment | Pull requests (comment) |
| Tester | Repository: Write, Checks: Read | Contents, checks |
| Deployer | Pull requests: Write, Actions: Write | Pull requests (merge), workflows |
| Reporter | Issues: Write | Issues (comment) |

**Why separate?**: If one token leaks, blast radius is limited to that agent's capabilities.

### Secret Management

- **Development**: `.env` file (gitignored)
- **Production**: AWS Secrets Manager
  - Secrets rotated regularly
  - IAM roles grant read access per agent
  - Secrets injected as environment variables at runtime

## Deployment Architecture

### AWS Components

#### Entry Point
- **API Gateway**: HTTPS endpoint for webhooks
- **Lambda**: Webhook validation and SQS publishing

#### Processing
- **SQS Queue**: Decouples webhook from orchestrator
- **Dead Letter Queue**: Failed jobs for manual inspection
- **ECS Fargate Service**: Long-running orchestrator (polls SQS)

#### Data
- **Aurora Postgres Serverless v2**: Checkpoint persistence
- **pgvector extension**: Future semantic search support

#### Sandbox
- **ECS Fargate Task**: Ephemeral container per coding session
- **Restricted egress**: Only GitHub and approved services
- **No production credentials**: Isolated environment

#### Deployment Target
- **Application Load Balancer**: Public endpoint for staging
- **ECS Fargate Service**: Sample app (multiple tasks)
- **Health checks**: ALB targets /health endpoint

#### Monitoring
- **CloudWatch Logs**: Centralized logging
- **CloudWatch Alarms**: Error rate > 5% triggers SNS
- **X-Ray**: Distributed tracing (optional)

### Cost Breakdown

| Component | Estimated Monthly Cost |
|-----------|----------------------|
| ECS Fargate (orchestrator + staging) | $30-50 |
| Aurora Serverless v2 (0.5-2 ACU) | $20-40 |
| API Gateway (per request) | $1-5 |
| Secrets Manager (6 secrets) | $2.40 |
| CloudWatch Logs | $5-10 |
| **Total** | **$60-105** |

## Failure Handling

### Retry Strategy

#### Coder Failures
- **Max**: 3 retries
- **Trigger**: Tests fail, linting fails
- **Action**: Re-code with failure logs as context

#### Reviewer Rejections
- **Max**: 3 rounds
- **Trigger**: Reviewer requests changes
- **Action**: Increment counter, return to Coder

#### Test Failures
- **Max**: Total retry cap (10)
- **Trigger**: CI tests fail
- **Action**: Return to Coder with failure details

#### Total Retry Cap
- **Max**: 10 across all steps
- **Action**: Stop workflow, escalate to human

### Rollback Strategy

#### Deployment Health Check Failed
1. Monitor error rate and response times
2. If error rate > 5% or health endpoint fails:
   - Log failure
   - Trigger rollback
   - Restore previous version
   - Mark deploy as rolled back
3. Reporter includes rollback details in summary

#### Manual Rollback
Human can reject at approval gate:
- Workflow marked as rejected
- No deployment occurs
- Summary posted with rejection reason

## Design Decisions

### Why LangGraph?

**Alternatives considered**: LangChain LCEL, CrewAI, AutoGPT

**Why LangGraph**:
- Native supervisor pattern support
- Stateful workflows with checkpoints
- Built-in interrupt for human-in-the-loop
- Conditional routing without complex orchestration code
- Production-ready (used at scale by Anthropic, LangChain)

**Trade-offs**:
- More boilerplate than simple chains
- Learning curve for graph concepts
- But: Flexibility and resumability worth it

### Why Separate Agents?

**Alternatives considered**: Single agent with all tools

**Why separate**:
- **Security**: Least privilege enforced at agent level
- **Testing**: Each agent testable in isolation
- **Observability**: Clear which agent did what
- **Cost**: Different models per agent (strong for coder, cheap for reporter)
- **Failure isolation**: One agent failure doesn't corrupt entire workflow

**Trade-offs**:
- More complexity in orchestration
- More API calls between agents
- But: Modularity and security worth it

### Why Mock Provider?

**Alternatives considered**: Only real LLMs

**Why mock**:
- **Offline dev**: No API keys needed
- **CI/CD**: Tests run without billing
- **Determinism**: Reproducible results for evaluation
- **Fast**: No network latency
- **Demo**: Full workflow demo without costs

**Trade-offs**:
- Mock responses are simplistic
- Doesn't catch real LLM errors
- But: Essential for development and testing

### Why CDK over Terraform?

**Terraform pros**:
- Cloud-agnostic (multi-cloud support)
- Mature ecosystem, large community
- State management built-in

**CDK pros**:
- Type-safe Python (same language as app)
- L2/L3 constructs (less boilerplate)
- Unit testable infrastructure
- Faster AWS feature adoption

**Decision**: CDK because:
1. This is AWS-only (not multi-cloud)
2. Python type safety catches errors
3. 60% less code vs Terraform
4. Team already knows Python

## Extension Points

### Adding a New Agent

1. Create class inheriting `BaseAgent`
2. Define `execute(state)` method
3. Add role to `AgentRole` enum
4. Define permissions in `AGENT_PERMISSIONS`
5. Register in orchestrator graph
6. Add routing logic

### Adding a New Tool

1. Implement async function: `async def tool(**params) -> result`
2. Register with gateway: `gateway.register_tool(name, permission, handler)`
3. Agents call via: `await self.call_tool(name, **params)`

### Custom Notifier

1. Inherit `BaseNotifier`
2. Implement `async def send_approval_request(state)`
3. Register in `create_notifier()` factory

### Custom LLM Provider

1. Inherit `BaseLLMProvider`
2. Implement `async def generate(...)` and `estimate_cost(...)`
3. Register in `create_llm_provider()` factory

## Performance Considerations

### Token Budget

- Set `MAX_TOKENS_PER_JOB` to control costs
- Track usage in `WorkflowState.token_usage`
- Abort if budget exceeded

### Latency

- Typical workflow: 1-3 minutes (mock mode)
- Real mode: 3-10 minutes depending on LLM latency
- Bottleneck: LLM API calls (sequential by design)

### Parallelization

Future: Run Coder and Tester in parallel after initial implementation. Requires:
- Graph modification for parallel nodes
- Merge logic for results
- Conflict detection

## Observability

### Logging

- Structured logs with context (job_id, agent_role, step)
- Log levels: DEBUG (tool calls), INFO (step completion), ERROR (failures)
- CloudWatch Logs in AWS, stdout in local

### Metrics

Key metrics to track:
- Jobs per hour
- Pass rate (by complexity)
- Average retries
- Average duration
- Cost per job
- Token usage

### Tracing

- Langfuse integration (optional)
- Traces include: agent name, LLM calls, tool calls, cost
- Dashboard shows cost breakdown and performance

## Testing Strategy

### Unit Tests

- **Gateway**: Permission enforcement, audit logging
- **Routing**: Conditional logic, retry limits
- **Providers**: Mock responses, token counting
- **Agents**: Isolated execution (mocked tools)

### Integration Tests

- **End-to-end**: Full workflow with mock backends
- **GitHub**: Real API calls (optional, requires token)
- **Database**: Checkpoint save/restore

### Evaluation

- 20 sample issues with known complexity
- Run with mock provider
- Metrics: pass rate, tokens, cost, retries
- Regression detection

---

**Document Version**: 1.0  
**Last Updated**: 2026-09-28  
**Authors**: PR-to-Production Team
