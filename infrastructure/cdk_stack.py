"""AWS CDK Infrastructure for PR-to-Production Agent Team.

This CDK stack defines:
- API Gateway + Lambda webhook receiver
- SQS queue with DLQ for job processing
- ECS Fargate service for orchestrator
- ECS Fargate task definition for sandbox
- Aurora Postgres for checkpoints
- Secrets Manager for agent tokens
- ECS staging service + ALB for sample app
- CloudWatch alarms and monitoring

Why CDK over Terraform:
1. Type-safe with Python integration (same language as main project)
2. Higher-level constructs (L2/L3) reduce boilerplate
3. Better AWS service integration and defaults
4. Easier to unit test infrastructure code
5. Native AWS support and faster feature adoption
"""

from aws_cdk import (
    Stack,
    Duration,
    RemovalPolicy,
    aws_apigateway as apigw,
    aws_lambda as lambda_,
    aws_sqs as sqs,
    aws_ecs as ecs,
    aws_ec2 as ec2,
    aws_rds as rds,
    aws_secretsmanager as secrets,
    aws_ecs_patterns as ecs_patterns,
    aws_cloudwatch as cloudwatch,
    aws_logs as logs,
)
from constructs import Construct


class PrToProdAgentStack(Stack):
    """CDK Stack for PR-to-Production Agent Team infrastructure."""

    def __init__(self, scope: Construct, construct_id: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        vpc = ec2.Vpc(
            self,
            "PrToProdVpc",
            max_azs=2,
            nat_gateways=1,
        )

        job_queue = sqs.Queue(
            self,
            "JobQueue",
            queue_name="pr-to-prod-jobs",
            visibility_timeout=Duration.minutes(15),
            retention_period=Duration.days(7),
            dead_letter_queue=sqs.DeadLetterQueue(
                max_receive_count=3,
                queue=sqs.Queue(
                    self,
                    "JobDLQ",
                    queue_name="pr-to-prod-jobs-dlq",
                    retention_period=Duration.days(14),
                ),
            ),
        )

        webhook_lambda = lambda_.Function(
            self,
            "WebhookHandler",
            runtime=lambda_.Runtime.PYTHON_3_11,
            handler="webhook.handler",
            code=lambda_.Code.from_asset("lambda"),
            environment={
                "JOB_QUEUE_URL": job_queue.queue_url,
            },
            timeout=Duration.seconds(30),
            memory_size=256,
        )

        job_queue.grant_send_messages(webhook_lambda)

        api = apigw.RestApi(
            self,
            "WebhookApi",
            rest_api_name="pr-to-prod-webhook",
            description="GitHub webhook receiver for PR-to-Production agents",
        )

        webhook_integration = apigw.LambdaIntegration(webhook_lambda)
        api.root.add_resource("webhook").add_resource("github").add_method(
            "POST", webhook_integration
        )

        db_cluster = rds.DatabaseCluster(
            self,
            "CheckpointDatabase",
            engine=rds.DatabaseClusterEngine.aurora_postgres(
                version=rds.AuroraPostgresEngineVersion.VER_15_3
            ),
            writer=rds.ClusterInstance.serverless_v2("Writer"),
            serverless_v2_min_capacity=0.5,
            serverless_v2_max_capacity=2,
            vpc=vpc,
            default_database_name="checkpoints",
            removal_policy=RemovalPolicy.SNAPSHOT,
        )

        cluster = ecs.Cluster(
            self,
            "PrToProdCluster",
            vpc=vpc,
            container_insights=True,
        )

        orchestrator_task_def = ecs.FargateTaskDefinition(
            self,
            "OrchestratorTask",
            memory_limit_mib=2048,
            cpu=1024,
        )

        orchestrator_task_def.add_container(
            "Orchestrator",
            image=ecs.ContainerImage.from_asset(".."),
            logging=ecs.LogDrivers.aws_logs(
                stream_prefix="orchestrator",
                log_retention=logs.RetentionDays.ONE_WEEK,
            ),
            environment={
                "DATABASE_URL": f"postgresql://user@{db_cluster.cluster_endpoint.hostname}/checkpoints",
                "SQS_QUEUE_URL": job_queue.queue_url,
            },
        )

        job_queue.grant_consume_messages(orchestrator_task_def.task_role)
        db_cluster.grant_connect(orchestrator_task_def.task_role)

        orchestrator_service = ecs.FargateService(
            self,
            "OrchestratorService",
            cluster=cluster,
            task_definition=orchestrator_task_def,
            desired_count=1,
        )

        sandbox_task_def = ecs.FargateTaskDefinition(
            self,
            "SandboxTask",
            memory_limit_mib=4096,
            cpu=2048,
        )

        sandbox_task_def.add_container(
            "Sandbox",
            image=ecs.ContainerImage.from_registry("python:3.11-slim"),
            logging=ecs.LogDrivers.aws_logs(
                stream_prefix="sandbox",
                log_retention=logs.RetentionDays.ONE_DAY,
            ),
        )

        agent_secrets = {
            "planner": self._create_secret("PlannerGitHubToken", "GitHub token for planner agent"),
            "coder": self._create_secret("CoderGitHubToken", "GitHub token for coder agent"),
            "reviewer": self._create_secret("ReviewerGitHubToken", "GitHub token for reviewer agent"),
            "tester": self._create_secret("TesterGitHubToken", "GitHub token for tester agent"),
            "deployer": self._create_secret("DeployerGitHubToken", "GitHub token for deployer agent"),
            "reporter": self._create_secret("ReporterGitHubToken", "GitHub token for reporter agent"),
        }

        for secret in agent_secrets.values():
            secret.grant_read(orchestrator_task_def.task_role)

        staging_service = ecs_patterns.ApplicationLoadBalancedFargateService(
            self,
            "StagingService",
            cluster=cluster,
            task_image_options=ecs_patterns.ApplicationLoadBalancedTaskImageOptions(
                image=ecs.ContainerImage.from_asset("../sample-app"),
                container_port=8000,
            ),
            public_load_balancer=True,
            desired_count=2,
        )

        staging_service.target_group.configure_health_check(
            path="/health",
            interval=Duration.seconds(30),
        )

        error_rate_alarm = cloudwatch.Alarm(
            self,
            "HighErrorRate",
            metric=staging_service.service.metric_cpu_utilization(),
            threshold=80,
            evaluation_periods=2,
            datapoints_to_alarm=2,
        )

    def _create_secret(self, id: str, description: str) -> secrets.Secret:
        """Create a secret for storing agent tokens."""
        return secrets.Secret(
            self,
            id,
            description=description,
            removal_policy=RemovalPolicy.RETAIN,
        )
