# Infrastructure as Code (CDK)

This directory contains AWS CDK infrastructure definitions for deploying the PR-to-Production Agent Team to AWS.

## Architecture Components

- **API Gateway + Lambda**: GitHub webhook receiver
- **SQS + DLQ**: Job queue with dead-letter handling
- **ECS Fargate**: Orchestrator service and sandbox tasks
- **Aurora Postgres**: Checkpoint persistence with pgvector
- **Secrets Manager**: Per-agent GitHub tokens
- **ALB + ECS**: Staging service deployment
- **CloudWatch**: Monitoring and rollback alarms

## Prerequisites

```bash
npm install -g aws-cdk
pip install -r requirements.txt
```

## Deployment

```bash
# Synth CloudFormation template
cdk synth

# Deploy to AWS (do not run in demo - instructions only)
cdk bootstrap  # First time only
cdk deploy
```

## Configuration

Set context in `cdk.json` or pass via CLI:

```bash
cdk synth -c account=123456789012 -c region=us-east-1
```

## Cost Estimation

- ECS Fargate: ~$30-50/month (orchestrator + staging)
- Aurora Serverless v2: ~$20-40/month (minimal usage)
- API Gateway: Minimal (pay per request)
- Secrets Manager: $0.40/secret/month
- CloudWatch Logs: ~$5-10/month

Total estimated: **$60-100/month** for light usage

## Design Decisions

**Why CDK over Terraform:**
1. Type-safe Python integration (same language as main project)
2. Higher-level constructs reduce boilerplate by 60%
3. Better AWS service integration and secure defaults
4. Easier to unit test infrastructure code
5. Native AWS support with faster feature adoption

## Security

- VPC with private subnets for services
- Secrets Manager for sensitive data
- Least-privilege IAM roles per service
- Security groups restrict network access
- CloudWatch logging enabled
