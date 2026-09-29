"""Mock GitHub backend for testing without real GitHub API."""

import logging
from typing import Any

from pr_to_prod.models import AgentPermission
from pr_to_prod.tools.gateway import ToolGateway

logger = logging.getLogger(__name__)


class MockGitHubBackend:
    """Mock GitHub backend that simulates API responses."""

    def __init__(self) -> None:
        self.repos: dict[str, dict[str, Any]] = {}
        self.files: dict[str, dict[str, str]] = {}
        self.branches: dict[str, list[str]] = {}
        self.prs: dict[str, list[dict[str, Any]]] = {}
        self.pr_counter = 1
        self.issues: dict[str, dict[int, list[dict[str, Any]]]] = {}

    def init_repo(self, owner: str, repo: str, default_branch: str = "main") -> None:
        """Initialize a mock repository."""
        key = f"{owner}/{repo}"
        self.repos[key] = {
            "name": repo,
            "full_name": key,
            "description": f"Mock repository {repo}",
            "default_branch": default_branch,
            "language": "Python",
        }
        self.branches[key] = [default_branch]
        self.files[key] = {
            "README.md": "# Sample App\n\nThis is a mock repository.",
            "app/main.py": "# Main application file\n\ndef main():\n    pass\n",
        }
        self.prs[key] = []
        self.issues[key] = {}


class MockGitHubTools:
    """Mock GitHub tools for testing."""

    def __init__(self, backend: MockGitHubBackend, gateway: ToolGateway):
        self.backend = backend
        self.gateway = gateway
        self._register_tools()

    def _register_tools(self) -> None:
        """Register all GitHub tools with the gateway."""
        self.gateway.register_tool("read_repo", AgentPermission.READ_REPO, self.read_repo)
        self.gateway.register_tool("search_code", AgentPermission.SEARCH_CODE, self.search_code)
        self.gateway.register_tool("read_file", AgentPermission.READ_FILE, self.read_file)
        self.gateway.register_tool("write_file", AgentPermission.WRITE_FILE, self.write_file)
        self.gateway.register_tool("push_branch", AgentPermission.PUSH_BRANCH, self.push_branch)
        self.gateway.register_tool("create_pr", AgentPermission.CREATE_PR, self.create_pr)
        self.gateway.register_tool("comment_pr", AgentPermission.COMMENT_PR, self.comment_pr)
        self.gateway.register_tool("review_pr", AgentPermission.REVIEW_PR, self.review_pr)
        self.gateway.register_tool("merge_pr", AgentPermission.MERGE_PR, self.merge_pr)
        self.gateway.register_tool("read_ci", AgentPermission.READ_CI, self.read_ci_status)
        self.gateway.register_tool(
            "comment_issue", AgentPermission.COMMENT_ISSUE, self.comment_issue
        )

    async def read_repo(self, owner: str, repo: str) -> dict[str, Any]:
        """Read repository metadata."""
        key = f"{owner}/{repo}"
        if key not in self.backend.repos:
            raise ValueError(f"Repository {key} not found")
        return self.backend.repos[key].copy()

    async def search_code(self, owner: str, repo: str, query: str) -> list[dict[str, Any]]:
        """Search code in repository."""
        key = f"{owner}/{repo}"
        if key not in self.backend.files:
            return []

        results = []
        for path, content in self.backend.files[key].items():
            if query.lower() in content.lower() or query.lower() in path.lower():
                results.append(
                    {
                        "path": path,
                        "score": 1.0,
                        "sha": "mock-sha-" + path.replace("/", "-"),
                    }
                )
        return results

    async def read_file(self, owner: str, repo: str, path: str, ref: str = "main") -> str:
        """Read file content from repository."""
        key = f"{owner}/{repo}"
        if key not in self.backend.files:
            raise ValueError(f"Repository {key} not found")
        if path not in self.backend.files[key]:
            raise ValueError(f"File {path} not found")
        return self.backend.files[key][path]

    async def write_file(
        self,
        owner: str,
        repo: str,
        path: str,
        content: str,
        branch: str,
        message: str,
    ) -> dict[str, Any]:
        """Write file to repository."""
        key = f"{owner}/{repo}"
        if key not in self.backend.files:
            raise ValueError(f"Repository {key} not found")

        self.backend.files[key][path] = content
        logger.info(f"Mock: wrote file {path} to branch {branch}")

        return {
            "path": path,
            "sha": f"mock-sha-{path}-{len(content)}",
            "message": message,
        }

    async def push_branch(
        self, owner: str, repo: str, branch: str, base_branch: str = "main"
    ) -> dict[str, Any]:
        """Create a new branch."""
        key = f"{owner}/{repo}"
        if key not in self.backend.branches:
            raise ValueError(f"Repository {key} not found")

        if branch not in self.backend.branches[key]:
            self.backend.branches[key].append(branch)
            logger.info(f"Mock: created branch {branch}")

        return {
            "branch": branch,
            "sha": f"mock-sha-{branch}",
        }

    async def create_pr(
        self,
        owner: str,
        repo: str,
        title: str,
        body: str,
        head: str,
        base: str = "main",
    ) -> dict[str, Any]:
        """Create a pull request."""
        key = f"{owner}/{repo}"
        if key not in self.backend.prs:
            raise ValueError(f"Repository {key} not found")

        pr_number = self.backend.pr_counter
        self.backend.pr_counter += 1

        pr = {
            "number": pr_number,
            "url": f"https://github.com/{owner}/{repo}/pull/{pr_number}",
            "title": title,
            "body": body,
            "head": head,
            "base": base,
            "state": "open",
            "comments": [],
        }
        self.backend.prs[key].append(pr)
        logger.info(f"Mock: created PR #{pr_number}")

        return {
            "number": pr_number,
            "url": pr["url"],
            "title": title,
            "state": "open",
        }

    async def comment_pr(
        self, owner: str, repo: str, pr_number: int, comment: str
    ) -> dict[str, Any]:
        """Add a comment to a pull request."""
        key = f"{owner}/{repo}"
        pr = self._find_pr(key, pr_number)

        comment_obj = {
            "id": len(pr["comments"]) + 1,
            "body": comment,
        }
        pr["comments"].append(comment_obj)
        logger.info(f"Mock: added comment to PR #{pr_number}")

        return {
            "id": comment_obj["id"],
            "url": f"{pr['url']}#issuecomment-{comment_obj['id']}",
        }

    async def review_pr(
        self,
        owner: str,
        repo: str,
        pr_number: int,
        event: str,
        body: str | None = None,
    ) -> dict[str, Any]:
        """Submit a review on a pull request."""
        key = f"{owner}/{repo}"
        pr = self._find_pr(key, pr_number)

        review_id = len(pr.get("reviews", [])) + 1
        if "reviews" not in pr:
            pr["reviews"] = []

        pr["reviews"].append(
            {
                "id": review_id,
                "event": event,
                "body": body or "",
            }
        )
        logger.info(f"Mock: submitted {event} review on PR #{pr_number}")

        return {
            "id": review_id,
            "state": event,
        }

    async def merge_pr(
        self, owner: str, repo: str, pr_number: int, merge_method: str = "merge"
    ) -> dict[str, Any]:
        """Merge a pull request."""
        key = f"{owner}/{repo}"
        pr = self._find_pr(key, pr_number)

        pr["state"] = "closed"
        pr["merged"] = True
        logger.info(f"Mock: merged PR #{pr_number}")

        return {
            "merged": True,
            "sha": f"mock-merge-sha-{pr_number}",
            "message": "Pull request merged successfully",
        }

    async def read_ci_status(self, owner: str, repo: str, ref: str) -> dict[str, Any]:
        """Get CI status for a reference."""
        logger.info(f"Mock: reading CI status for {ref}")
        return {
            "state": "success",
            "total_count": 2,
            "statuses": [
                {
                    "context": "tests",
                    "state": "success",
                    "description": "All tests passed",
                },
                {
                    "context": "lint",
                    "state": "success",
                    "description": "Linting passed",
                },
            ],
        }

    async def comment_issue(
        self, owner: str, repo: str, issue_number: int, comment: str
    ) -> dict[str, Any]:
        """Add a comment to an issue."""
        key = f"{owner}/{repo}"
        if key not in self.backend.issues:
            self.backend.issues[key] = {}
        if issue_number not in self.backend.issues[key]:
            self.backend.issues[key][issue_number] = []

        comment_obj = {
            "id": len(self.backend.issues[key][issue_number]) + 1,
            "body": comment,
        }
        self.backend.issues[key][issue_number].append(comment_obj)
        logger.info(f"Mock: added comment to issue #{issue_number}")

        return {
            "id": comment_obj["id"],
            "url": f"https://github.com/{owner}/{repo}/issues/{issue_number}#issuecomment-{comment_obj['id']}",
        }

    def _find_pr(self, key: str, pr_number: int) -> dict[str, Any]:
        """Find a PR by number."""
        if key not in self.backend.prs:
            raise ValueError(f"Repository {key} not found")

        for pr in self.backend.prs[key]:
            if pr["number"] == pr_number:
                return pr

        raise ValueError(f"PR #{pr_number} not found")
