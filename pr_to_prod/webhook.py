"""FastAPI webhook receiver for GitHub events."""

import hashlib
import hmac
import logging
from typing import Any

from fastapi import FastAPI, Header, HTTPException, Request
from pydantic import BaseModel

from pr_to_prod.config import get_settings

logger = logging.getLogger(__name__)

app = FastAPI(title="PR-to-Production Webhook Receiver")


class WebhookPayload(BaseModel):
    """GitHub webhook payload."""

    action: str
    issue: dict[str, Any] | None = None
    repository: dict[str, Any] | None = None


def verify_signature(payload: bytes, signature: str, secret: str) -> bool:
    """Verify GitHub webhook signature."""
    if not secret:
        logger.warning("No webhook secret configured, skipping verification")
        return True

    expected_signature = "sha256=" + hmac.new(secret.encode(), payload, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected_signature, signature)


@app.get("/health")
async def health() -> dict[str, str]:
    """Health check endpoint."""
    return {"status": "healthy"}


@app.post("/webhook/github")
async def github_webhook(
    request: Request,
    x_github_event: str = Header(...),
    x_hub_signature_256: str | None = Header(None),
) -> dict[str, str]:
    """
    Handle GitHub webhook events.

    Listens for issue events with the 'agent:build' label.
    """
    settings = get_settings()

    body = await request.body()

    if settings.github_webhook_secret and x_hub_signature_256:
        if not verify_signature(body, x_hub_signature_256, settings.github_webhook_secret):
            logger.error("Invalid webhook signature")
            raise HTTPException(status_code=401, detail="Invalid signature")

    payload = await request.json()

    logger.info(f"Received {x_github_event} event")

    if x_github_event == "issues":
        action = payload.get("action")
        issue = payload.get("issue", {})
        labels = [label["name"] for label in issue.get("labels", [])]

        if action in ["opened", "labeled"] and "agent:build" in labels:
            issue_number = issue.get("number")
            repo = payload.get("repository", {})
            repo_owner = repo.get("owner", {}).get("login")
            repo_name = repo.get("name")

            logger.info(
                f"Triggering workflow for issue #{issue_number} in {repo_owner}/{repo_name}"
            )

            return {
                "status": "queued",
                "message": f"Workflow triggered for issue #{issue_number}",
            }

    return {"status": "ignored", "message": "Event does not match trigger conditions"}


@app.post("/api/trigger")
async def trigger_workflow(
    issue_number: int,
    repo_owner: str,
    repo_name: str,
) -> dict[str, str]:
    """
    Manual API endpoint to trigger a workflow.
    """
    logger.info(f"Manual trigger for issue #{issue_number} in {repo_owner}/{repo_name}")

    return {
        "status": "queued",
        "message": f"Workflow triggered for issue #{issue_number}",
        "job_id": f"job-{issue_number}-manual",
    }


if __name__ == "__main__":
    import uvicorn

    settings = get_settings()
    uvicorn.run(
        app,
        host=settings.webhook_host,
        port=settings.webhook_port,
        log_level=settings.log_level.lower(),
    )
