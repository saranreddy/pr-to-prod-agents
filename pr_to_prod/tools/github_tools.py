"""GitHub tools for repository operations."""

import logging
from typing import Any, Optional

from github import Github
from github.GithubException import GithubException

from pr_to_prod.models import AgentPermission
from pr_to_prod.tools.gateway import ToolGateway

logger = logging.getLogger(__name__)


class GitHubTools:
    """Tools for interacting with GitHub."""

    def __init__(self, token: str, gateway: ToolGateway):
        self.github = Github(token)
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
        try:
            repository = self.github.get_repo(f"{owner}/{repo}")
            return {
                "name": repository.name,
                "full_name": repository.full_name,
                "description": repository.description,
                "default_branch": repository.default_branch,
                "language": repository.language,
            }
        except GithubException as e:
            logger.error(f"Failed to read repo: {e}")
            raise

    async def search_code(self, owner: str, repo: str, query: str) -> list[dict[str, Any]]:
        """Search code in repository."""
        try:
            search_query = f"{query} repo:{owner}/{repo}"
            results = self.github.search_code(search_query)
            return [
                {"path": item.path, "score": item.score, "sha": item.sha}
                for item in list(results)[:20]
            ]
        except GithubException as e:
            logger.error(f"Failed to search code: {e}")
            raise

    async def read_file(self, owner: str, repo: str, path: str, ref: str = "main") -> str:
        """Read file content from repository."""
        try:
            repository = self.github.get_repo(f"{owner}/{repo}")
            file_content = repository.get_contents(path, ref=ref)
            if isinstance(file_content, list):
                raise ValueError(f"Path {path} is a directory, not a file")
            return file_content.decoded_content.decode("utf-8")
        except GithubException as e:
            logger.error(f"Failed to read file {path}: {e}")
            raise

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
        try:
            repository = self.github.get_repo(f"{owner}/{repo}")
            
            try:
                file_content = repository.get_contents(path, ref=branch)
                if isinstance(file_content, list):
                    raise ValueError(f"Path {path} is a directory")
                result = repository.update_file(
                    path=path,
                    message=message,
                    content=content,
                    sha=file_content.sha,
                    branch=branch,
                )
            except GithubException as e:
                if e.status == 404:
                    result = repository.create_file(
                        path=path,
                        message=message,
                        content=content,
                        branch=branch,
                    )
                else:
                    raise

            return {
                "path": path,
                "sha": result["commit"].sha,
                "message": message,
            }
        except GithubException as e:
            logger.error(f"Failed to write file {path}: {e}")
            raise

    async def push_branch(
        self, owner: str, repo: str, branch: str, base_branch: str = "main"
    ) -> dict[str, Any]:
        """Create a new branch."""
        try:
            repository = self.github.get_repo(f"{owner}/{repo}")
            base_ref = repository.get_git_ref(f"heads/{base_branch}")
            ref = repository.create_git_ref(f"refs/heads/{branch}", base_ref.object.sha)
            return {
                "branch": branch,
                "sha": ref.object.sha,
            }
        except GithubException as e:
            if e.status == 422:
                logger.info(f"Branch {branch} already exists")
                return {"branch": branch, "sha": "exists"}
            logger.error(f"Failed to create branch {branch}: {e}")
            raise

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
        try:
            repository = self.github.get_repo(f"{owner}/{repo}")
            pr = repository.create_pull(title=title, body=body, head=head, base=base, draft=True)
            return {
                "number": pr.number,
                "url": pr.html_url,
                "title": pr.title,
                "state": pr.state,
            }
        except GithubException as e:
            logger.error(f"Failed to create PR: {e}")
            raise

    async def comment_pr(
        self, owner: str, repo: str, pr_number: int, comment: str
    ) -> dict[str, Any]:
        """Add a comment to a pull request."""
        try:
            repository = self.github.get_repo(f"{owner}/{repo}")
            pr = repository.get_pull(pr_number)
            comment_obj = pr.create_issue_comment(comment)
            return {
                "id": comment_obj.id,
                "url": comment_obj.html_url,
            }
        except GithubException as e:
            logger.error(f"Failed to comment on PR {pr_number}: {e}")
            raise

    async def review_pr(
        self,
        owner: str,
        repo: str,
        pr_number: int,
        event: str,
        body: Optional[str] = None,
    ) -> dict[str, Any]:
        """Submit a review on a pull request."""
        try:
            repository = self.github.get_repo(f"{owner}/{repo}")
            pr = repository.get_pull(pr_number)
            review = pr.create_review(body=body or "", event=event)
            return {
                "id": review.id,
                "state": review.state,
            }
        except GithubException as e:
            logger.error(f"Failed to review PR {pr_number}: {e}")
            raise

    async def merge_pr(
        self, owner: str, repo: str, pr_number: int, merge_method: str = "merge"
    ) -> dict[str, Any]:
        """Merge a pull request."""
        try:
            repository = self.github.get_repo(f"{owner}/{repo}")
            pr = repository.get_pull(pr_number)
            result = pr.merge(merge_method=merge_method)
            return {
                "merged": result.merged,
                "sha": result.sha,
                "message": result.message,
            }
        except GithubException as e:
            logger.error(f"Failed to merge PR {pr_number}: {e}")
            raise

    async def read_ci_status(
        self, owner: str, repo: str, ref: str
    ) -> dict[str, Any]:
        """Get CI status for a reference."""
        try:
            repository = self.github.get_repo(f"{owner}/{repo}")
            commit = repository.get_commit(ref)
            status = commit.get_combined_status()
            return {
                "state": status.state,
                "total_count": status.total_count,
                "statuses": [
                    {
                        "context": s.context,
                        "state": s.state,
                        "description": s.description,
                    }
                    for s in status.statuses
                ],
            }
        except GithubException as e:
            logger.error(f"Failed to read CI status for {ref}: {e}")
            raise

    async def comment_issue(
        self, owner: str, repo: str, issue_number: int, comment: str
    ) -> dict[str, Any]:
        """Add a comment to an issue."""
        try:
            repository = self.github.get_repo(f"{owner}/{repo}")
            issue = repository.get_issue(issue_number)
            comment_obj = issue.create_comment(comment)
            return {
                "id": comment_obj.id,
                "url": comment_obj.html_url,
            }
        except GithubException as e:
            logger.error(f"Failed to comment on issue {issue_number}: {e}")
            raise
