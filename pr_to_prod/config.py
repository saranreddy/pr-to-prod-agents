"""Configuration management using Pydantic Settings."""

from typing import Literal, Optional

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    environment: str = "development"
    log_level: str = "INFO"

    llm_provider: Literal["anthropic", "bedrock", "mock"] = "mock"
    
    anthropic_api_key: Optional[str] = None
    
    aws_region: str = "us-east-1"
    aws_access_key_id: Optional[str] = None
    aws_secret_access_key: Optional[str] = None
    bedrock_model_id: str = "anthropic.claude-3-5-sonnet-20241022-v2:0"
    
    planner_model: str = "claude-3-5-haiku-20241022"
    coder_model: str = "claude-3-5-sonnet-20241022"
    reviewer_model: str = "claude-3-5-sonnet-20241022"
    tester_model: str = "claude-3-5-sonnet-20241022"
    deployer_model: str = "claude-3-5-haiku-20241022"
    reporter_model: str = "claude-3-5-haiku-20241022"
    
    max_tokens_per_job: int = 500000
    max_retries_coder: int = 3
    max_retries_reviewer: int = 3
    
    github_token: Optional[str] = None
    github_webhook_secret: Optional[str] = None
    
    planner_github_token: Optional[str] = None
    coder_github_token: Optional[str] = None
    reviewer_github_token: Optional[str] = None
    tester_github_token: Optional[str] = None
    deployer_github_token: Optional[str] = None
    reporter_github_token: Optional[str] = None
    
    target_repo_owner: str = "example-org"
    target_repo_name: str = "sample-app"
    default_base_branch: str = "main"
    
    database_url: str = "sqlite:///checkpoints.db"
    
    notifier_type: Literal["console", "slack", "sns"] = "console"
    slack_webhook_url: Optional[str] = None
    sns_topic_arn: Optional[str] = None
    
    langfuse_enabled: bool = False
    langfuse_public_key: Optional[str] = None
    langfuse_secret_key: Optional[str] = None
    langfuse_host: str = "https://cloud.langfuse.com"
    
    webhook_host: str = "0.0.0.0"
    webhook_port: int = 8000
    
    sandbox_type: Literal["docker", "fargate"] = "docker"
    docker_image: str = "python:3.11-slim"
    
    health_check_interval_seconds: int = 30
    health_check_duration_minutes: int = 5
    error_rate_threshold_percent: float = 5.0
    
    eval_output_dir: str = "eval_results"

    def get_agent_token(self, role: str) -> str:
        """Get the GitHub token for a specific agent role."""
        agent_token_map = {
            "planner": self.planner_github_token,
            "coder": self.coder_github_token,
            "reviewer": self.reviewer_github_token,
            "tester": self.tester_github_token,
            "deployer": self.deployer_github_token,
            "reporter": self.reporter_github_token,
        }
        return agent_token_map.get(role) or self.github_token or ""

    def get_agent_model(self, role: str) -> str:
        """Get the model name for a specific agent role."""
        model_map = {
            "planner": self.planner_model,
            "coder": self.coder_model,
            "reviewer": self.reviewer_model,
            "tester": self.tester_model,
            "deployer": self.deployer_model,
            "reporter": self.reporter_model,
        }
        return model_map.get(role, self.coder_model)


def get_settings() -> Settings:
    """Get application settings singleton."""
    return Settings()
