# PR-to-Production Agent Team

[![CI](https://github.com/your-org/pr-to-prod-agents/actions/workflows/ci.yml/badge.svg)](https://github.com/your-org/pr-to-prod-agents/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

Enterprise-grade multi-agent system that automates the complete PR-to-production workflow. A GitHub issue labeled `agent:build` triggers a team of specialist AI agents that plan, code, review, test, and deploy changes with human approval gates.

![Architecture Diagram](docs/architecture.dot)

## Overview

When you label a GitHub issue with `agent:build`, this system:

1. **Plans** the implementation (Planner agent - read-only)
2. **Codes** the changes on an agent branch (Coder agent - push only)
3. **Reviews** the PR against quality standards (Reviewer agent - comment only)
4. **Tests** with acceptance criteria (Tester agent - push tests, read CI)
5. **Awaits human approval** (durable interrupt with notification)
6. **Deploys** to staging and monitors health (Deployer agent - merge & deploy)
7. **Reports** results back to the issue (Reporter agent - comment only)

Each agent has **least-privilege permissions** enforced by a tool gateway with audit logging. Retry logic handles failures, and human approval gates provide control before deployment.

## Features

- 🤖 **Six Specialist Agents** with role-based permissions
- 🔒 **Tool Gateway** with audit logging and permission enforcement
- 🔄 **LangGraph Orchestration** with supervisor pattern and conditional routing
- 💾 **Checkpoint Persistence** (SQLite/Postgres) for resumable workflows
- 🎯 **Human-in-the-Loop** approval with pluggable notifications (Slack/SNS/Console)
- 🧪 **Mock LLM Provider** for offline testing and deterministic evaluation
- 📊 **Evaluation Harness** with 20 sample issues and pass rate tracking
- ☁️ **AWS Infrastructure** (CDK) with API Gateway, ECS Fargate, Aurora Postgres
- 📝 **Sample App** (FastAPI Notes API) for demonstrations

## Architecture

See [docs/architecture.md](docs/architecture.md) for detailed design documentation.

### Agent Roles and Permissions

| Agent | Role | Permissions |
|-------|------|-------------|
| **Planner** | Create implementation plan | Read repo, search code, read files |
| **Coder** | Implement changes | Write files, push to agent/* branches, create PRs |
| **Reviewer** | Code review | Read files, comment on PRs, submit reviews |
| **Tester** | Write tests | Write files, push to branches, read CI status |
| **Deployer** | Deploy and monitor | Merge PRs, trigger deploys, read health checks |
| **Reporter** | Summarize results | Comment on issues |

## Quick Start

### Prerequisites

- Python 3.11+
- (Optional) GitHub Personal Access Token for real mode
- (Optional) Anthropic API key or AWS credentials for real LLM providers

### Installation

```bash
# Clone the repository
git clone https://github.com/your-org/pr-to-prod-agents.git
cd pr-to-prod-agents

# Install dependencies
pip install -e ".[dev]"

# Copy environment template
cp .env.example .env
```

### Run the Demo (Mock Mode)

```bash
# Run end-to-end demo with mock LLM and GitHub
pr-to-prod demo --mock

# Or using make
make demo
```

This runs the full workflow (plan → code → review → test → approval → deploy → report) with simulated backends, printing a readable trace.

### Run with Real GitHub (Optional)

```bash
# Set your GitHub token in .env
# GITHUB_TOKEN=ghp_your_token_here

# Run against a real issue
pr-to-prod run --issue 42 --owner your-org --repo your-repo
```

## Configuration

Edit `.env` or set environment variables:

```bash
# LLM Provider
LLM_PROVIDER=mock  # mock, anthropic, or bedrock

# Anthropic (if using)
ANTHROPIC_API_KEY=sk-ant-xxxxx

# AWS Bedrock (if using)
AWS_REGION=us-east-1
BEDROCK_MODEL_ID=anthropic.claude-3-5-sonnet-20241022-v2:0

# GitHub
GITHUB_TOKEN=ghp_xxxxx

# Database (checkpoint persistence)
DATABASE_URL=sqlite:///checkpoints.db
# Or: postgresql://user:pass@host/db

# Notifications
NOTIFIER_TYPE=console  # console, slack, sns
SLACK_WEBHOOK_URL=https://hooks.slack.com/...
```

## Development

```bash
# Run tests
make test

# Format code
make format

# Lint
make lint

# Type check
make type-check

# Run evaluation
make eval
```

## Evaluation

The system includes an evaluation harness with 20 sample issues:

```bash
# Run evaluation with mock provider
python -m pr_to_prod.evaluations.run_eval --provider mock

# Results saved to eval_results/ with:
# - Pass rate by complexity
# - Token usage and cost
# - Retry counts
# - Average duration
```

Example output:
```
Evaluation Summary
Total Issues:    20
Passed:          18 (90.0%)
Failed:          2
Total Tokens:    150,000
Total Cost:      $0.00 (mock)
Avg Duration:    12.3s
```

## AWS Deployment

**Note: Do not run these commands - instructions only. No actual deployment is performed.**

```bash
# Install CDK
npm install -g aws-cdk

# Bootstrap CDK (first time only)
cd infrastructure
cdk bootstrap

# Synth CloudFormation template
cdk synth

# Deploy to AWS
# cdk deploy  # (NOT RUN IN DEMO)
```

This creates:
- API Gateway + Lambda for GitHub webhooks
- SQS queue for job processing
- ECS Fargate service for orchestrator
- Aurora Postgres for checkpoints
- Secrets Manager for per-agent tokens
- ECS + ALB for staging deployment
- CloudWatch alarms for monitoring

Estimated cost: **$60-100/month** for light usage.

### GitHub App Setup (Production)

For production, create separate GitHub Apps for each agent role:

1. **Planner App**: Read-only repository access
2. **Coder App**: Read/write code, create PRs (restrict to agent/* branches)
3. **Reviewer App**: Pull request review permissions
4. **Tester App**: Read/write code, read checks
5. **Deployer App**: Merge PRs, trigger workflows
6. **Reporter App**: Issue comment permissions

Store tokens in AWS Secrets Manager and configure:

```bash
PLANNER_GITHUB_TOKEN=ghp_readonly_xxxxx
CODER_GITHUB_TOKEN=ghp_push_agent_xxxxx
REVIEWER_GITHUB_TOKEN=ghp_comment_xxxxx
# ... etc
```

## How It Works

### Workflow Steps

1. **Trigger**: GitHub webhook or CLI starts a job
2. **Plan**: Planner reads issue and repo, creates structured plan
3. **Code**: Coder implements changes on `agent/<issue>-<slug>` branch
4. **Review**: Reviewer checks code quality (up to 3 rounds)
5. **Test**: Tester adds tests and reads CI results
6. **Approval**: System pauses and notifies human
7. **Deploy**: Deployer merges, deploys, monitors health
8. **Report**: Reporter posts summary to issue

### Retry Logic

- **Coder retries**: Max 3 (e.g., if tests fail)
- **Reviewer rounds**: Max 3 (changes requested → re-code)
- **Total retries**: Max 10 across all steps
- Retry cap hit → escalate to human with failure summary

### Rollback

If deployment health checks fail:
- Error rate > 5%: Auto-rollback triggered
- Previous version restored
- Incident reported in summary

## Project Structure

```
pr-to-prod-agents/
├── pr_to_prod/
│   ├── agents/              # Six specialist agents
│   ├── orchestration/       # LangGraph supervisor
│   ├── tools/               # Tool gateway + GitHub tools
│   ├── providers/           # LLM providers (Anthropic, Bedrock, Mock)
│   ├── models.py            # Pydantic data models
│   ├── config.py            # Settings management
│   ├── cli.py               # CLI interface
│   ├── webhook.py           # FastAPI webhook receiver
│   ├── notifiers.py         # Approval notifications
│   └── evaluations/         # Evaluation harness
├── tests/
│   ├── unit/                # Unit tests
│   └── integration/         # Integration tests
├── sample-app/              # Target app for demos
│   ├── app/main.py          # FastAPI notes API
│   └── tests/               # Sample app tests
├── infrastructure/          # AWS CDK stack
│   ├── cdk_stack.py         # Infrastructure definition
│   └── README.md            # Deployment guide
├── docs/
│   ├── architecture.md      # Detailed design docs
│   └── architecture.dot     # Architecture diagram
├── .github/workflows/       # CI for main project
├── pyproject.toml           # Python project config
├── .env.example             # Environment template
└── README.md                # This file
```

## Design Decisions

### Why LangGraph?
- Native support for supervisor patterns and conditional routing
- Checkpoint persistence for resumable workflows
- Built-in interrupt mechanism for human-in-the-loop

### Why Mock Provider?
- Enables offline development and testing
- Deterministic responses for reliable evaluation
- Zero cost for CI/CD pipelines
- Full workflow validation without API keys

### Why CDK over Terraform?
- Type-safe Python (same language as main project)
- Higher-level constructs (60% less boilerplate)
- Better AWS integration and secure defaults
- Easier to unit test infrastructure

### Why Least Privilege?
- Security: Limits blast radius if an agent is compromised
- Safety: Prevents accidental destructive operations
- Audit: Clear trail of which agent did what
- Production ready: Maps to separate GitHub Apps

## Known Limitations & Future Work

### Current Limitations

1. **Checkpoint Resume**: Resume command is a placeholder - full state restoration needs database queries
2. **Observability**: Langfuse integration exists but is minimal (set `LANGFUSE_ENABLED=true`)
3. **Sandbox Isolation**: Docker/Fargate mentioned but not fully implemented for coder execution
4. **MCP Servers**: GitHub tools are not yet exposed as MCP servers
5. **Real GitHub API**: Some advanced features (e.g., draft PR conversion) need refinement

### Roadmap

- [ ] Full checkpoint resume from database
- [ ] Rich Langfuse tracing with cost breakdown
- [ ] Sandboxed code execution (Docker/gVisor)
- [ ] MCP server for GitHub tools
- [ ] Multi-repo support
- [ ] Custom agent roles
- [ ] Web dashboard for job monitoring
- [ ] Parallel test execution
- [ ] Advanced rollback strategies

## Testing

```bash
# Run all tests
pytest

# Run with coverage
pytest --cov=pr_to_prod --cov-report=html

# Run specific test
pytest tests/unit/test_gateway.py -v

# Run integration tests
pytest tests/integration/ -v
```

## Contributing

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/amazing-feature`)
3. Make your changes with tests
4. Run `make test lint format type-check`
5. Commit your changes
6. Push to your branch
7. Open a Pull Request

## License

MIT License - see [LICENSE](LICENSE) file for details.

## Acknowledgments

- Built with [LangGraph](https://github.com/langchain-ai/langgraph) for orchestration
- Powered by [Anthropic Claude](https://www.anthropic.com/) for agent intelligence
- Infrastructure as code with [AWS CDK](https://aws.amazon.com/cdk/)
- Inspired by [AutoGPT](https://github.com/Significant-Gravitas/AutoGPT) and [MetaGPT](https://github.com/geekan/MetaGPT)

---

**Note**: This is a demonstration project showing enterprise multi-agent patterns. Do not deploy to production without security review, rate limiting, cost controls, and proper GitHub App configuration.
