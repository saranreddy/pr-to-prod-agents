"""Notifier implementations for human approval requests."""

import logging
from abc import ABC, abstractmethod
from typing import Any

import httpx

from pr_to_prod.models import WorkflowState

logger = logging.getLogger(__name__)


class BaseNotifier(ABC):
    """Base class for notifiers."""

    @abstractmethod
    async def send_approval_request(self, state: WorkflowState) -> None:
        """Send an approval request to a human."""
        pass


class ConsoleNotifier(BaseNotifier):
    """Console notifier that prints to stdout."""

    async def send_approval_request(self, state: WorkflowState) -> None:
        """Print approval request to console."""
        print("\n" + "=" * 80)
        print("🚨 HUMAN APPROVAL REQUIRED")
        print("=" * 80)
        print(f"\nJob ID: {state.job_id}")
        print(f"Issue: #{state.issue_number} - {state.issue_title}")
        print(f"\nPlan Summary: {state.plan.summary if state.plan else 'N/A'}")
        print(f"\nPR: {state.code_change.pr_url if state.code_change else 'N/A'}")
        print(f"Files Changed: {len(state.code_change.files_changed) if state.code_change else 0}")
        print(
            f"Review: {'Approved' if state.review_result and state.review_result.approved else 'N/A'}"
        )
        print(f"Tests: {'Passed' if state.test_result and state.test_result.passed else 'N/A'}")
        print(f"\nTo approve: pr-to-prod resume --job-id {state.job_id} --approve")
        print(f"To reject:  pr-to-prod resume --job-id {state.job_id} --reject")
        print("=" * 80 + "\n")


class SlackNotifier(BaseNotifier):
    """Slack notifier using webhook."""

    def __init__(self, webhook_url: str):
        self.webhook_url = webhook_url

    async def send_approval_request(self, state: WorkflowState) -> None:
        """Send approval request to Slack."""
        message = {
            "text": "🚨 Human Approval Required",
            "blocks": [
                {
                    "type": "header",
                    "text": {"type": "plain_text", "text": "🚨 Human Approval Required"},
                },
                {
                    "type": "section",
                    "fields": [
                        {"type": "mrkdwn", "text": f"*Job ID:*\n{state.job_id}"},
                        {
                            "type": "mrkdwn",
                            "text": f"*Issue:*\n#{state.issue_number} - {state.issue_title}",
                        },
                        {
                            "type": "mrkdwn",
                            "text": (
                                f"*PR:*\n<{state.code_change.pr_url}|View PR>"
                                if state.code_change
                                else "*PR:*\nN/A"
                            ),
                        },
                        {
                            "type": "mrkdwn",
                            "text": f"*Files Changed:*\n{len(state.code_change.files_changed) if state.code_change else 0}",
                        },
                    ],
                },
                {
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": f"*Plan:*\n{state.plan.summary if state.plan else 'N/A'}",
                    },
                },
                {
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": f"```\npr-to-prod resume --job-id {state.job_id} --approve\n```",
                    },
                },
            ],
        }

        async with httpx.AsyncClient() as client:
            response = await client.post(self.webhook_url, json=message)
            response.raise_for_status()
            logger.info(f"Sent approval request to Slack for job {state.job_id}")


class SNSNotifier(BaseNotifier):
    """SNS notifier for AWS environments."""

    def __init__(self, topic_arn: str):
        self.topic_arn = topic_arn
        try:
            import boto3

            self.sns = boto3.client("sns")
        except ImportError:
            raise ImportError("boto3 is required for SNS notifier")

    async def send_approval_request(self, state: WorkflowState) -> None:
        """Send approval request via SNS."""
        subject = f"Approval Required: Issue #{state.issue_number}"

        message = f"""
Human Approval Required

Job ID: {state.job_id}
Issue: #{state.issue_number} - {state.issue_title}
PR: {state.code_change.pr_url if state.code_change else 'N/A'}
Files Changed: {len(state.code_change.files_changed) if state.code_change else 0}

Plan: {state.plan.summary if state.plan else 'N/A'}

Review: {'Approved' if state.review_result and state.review_result.approved else 'N/A'}
Tests: {'Passed' if state.test_result and state.test_result.passed else 'N/A'}

To approve: pr-to-prod resume --job-id {state.job_id} --approve
To reject:  pr-to-prod resume --job-id {state.job_id} --reject
"""

        self.sns.publish(
            TopicArn=self.topic_arn,
            Subject=subject,
            Message=message,
        )
        logger.info(f"Sent approval request to SNS for job {state.job_id}")


def create_notifier(notifier_type: str, **kwargs: Any) -> BaseNotifier:
    """Create a notifier based on configuration."""
    if notifier_type == "console":
        return ConsoleNotifier()
    elif notifier_type == "slack":
        webhook_url = kwargs.get("webhook_url")
        if not webhook_url:
            raise ValueError("webhook_url is required for Slack notifier")
        return SlackNotifier(webhook_url)
    elif notifier_type == "sns":
        topic_arn = kwargs.get("topic_arn")
        if not topic_arn:
            raise ValueError("topic_arn is required for SNS notifier")
        return SNSNotifier(topic_arn)
    else:
        raise ValueError(f"Unknown notifier type: {notifier_type}")
