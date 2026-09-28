"""Sandbox execution environment for running untrusted code safely."""

import logging
import subprocess
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class SandboxResult:
    """Result from sandbox execution."""

    stdout: str
    stderr: str
    exit_code: int
    timed_out: bool = False
    error: str | None = None


class BaseSandboxRunner(ABC):
    """Abstract base class for sandbox runners."""

    @abstractmethod
    async def run(
        self,
        command: list[str],
        workdir: str,
        timeout: int = 300,
        **kwargs: Any,
    ) -> SandboxResult:
        """Run a command in the sandbox."""
        pass

    @abstractmethod
    def is_available(self) -> bool:
        """Check if this sandbox runner is available."""
        pass


class DockerSandboxRunner(BaseSandboxRunner):
    """
    Docker-based sandbox runner for secure command execution.

    Runs commands in isolated containers with:
    - No network access by default
    - Memory and CPU limits
    - Mounted workdir (read-only or read-write)
    - Time limits
    - No host credential passthrough
    """

    def __init__(
        self,
        image: str = "python:3.11-slim",
        memory_limit: str = "512m",
        cpu_limit: str = "1.0",
        network: str = "none",
    ):
        self.image = image
        self.memory_limit = memory_limit
        self.cpu_limit = cpu_limit
        self.network = network

    def is_available(self) -> bool:
        """Check if Docker is available."""
        try:
            result = subprocess.run(
                ["docker", "info"],
                capture_output=True,
                timeout=5,
            )
            return result.returncode == 0
        except (FileNotFoundError, subprocess.TimeoutExpired):
            return False

    async def run(
        self,
        command: list[str],
        workdir: str,
        timeout: int = 300,
        **kwargs: Any,
    ) -> SandboxResult:
        """
        Run command in Docker container.

        Args:
            command: Command to execute (list of args)
            workdir: Working directory to mount
            timeout: Timeout in seconds
            **kwargs: Additional docker run arguments

        Returns:
            SandboxResult with stdout, stderr, exit_code
        """
        if not self.is_available():
            raise RuntimeError("Docker is not available")

        # Build docker run command
        docker_cmd = [
            "docker",
            "run",
            "--rm",  # Remove container after run
            f"--memory={self.memory_limit}",
            f"--cpus={self.cpu_limit}",
            f"--network={self.network}",
            f"--volume={workdir}:/workspace:rw",
            "--workdir=/workspace",
            "--user=nobody",  # Run as unprivileged user
            self.image,
        ] + command

        logger.info(f"Docker sandbox: Running command in container (timeout={timeout}s)")

        try:
            result = subprocess.run(
                docker_cmd,
                capture_output=True,
                timeout=timeout,
                text=True,
            )

            return SandboxResult(
                stdout=result.stdout,
                stderr=result.stderr,
                exit_code=result.returncode,
            )

        except subprocess.TimeoutExpired:
            logger.warning(f"Docker sandbox: Command timed out after {timeout}s")
            return SandboxResult(
                stdout="",
                stderr=f"Command timed out after {timeout}s",
                exit_code=124,  # Standard timeout exit code
                timed_out=True,
            )

        except Exception as e:
            logger.error(f"Docker sandbox error: {e}")
            return SandboxResult(
                stdout="",
                stderr=str(e),
                exit_code=1,
                error=str(e),
            )


class SubprocessSandboxRunner(BaseSandboxRunner):
    """
    Fallback subprocess runner for local execution.

    WARNING: This runs commands directly on the host with minimal isolation.
    Use only when Docker is not available and commands are trusted.
    """

    def __init__(self) -> None:
        logger.warning(
            "SubprocessSandboxRunner: Using local subprocess execution. "
            "Commands will run on host with minimal isolation!"
        )

    def is_available(self) -> bool:
        """Subprocess is always available."""
        return True

    async def run(
        self,
        command: list[str],
        workdir: str,
        timeout: int = 300,
        **kwargs: Any,
    ) -> SandboxResult:
        """
        Run command as local subprocess.

        Args:
            command: Command to execute
            workdir: Working directory
            timeout: Timeout in seconds
            **kwargs: Ignored

        Returns:
            SandboxResult with stdout, stderr, exit_code
        """
        logger.warning(f"Subprocess sandbox: Running command on host (cwd={workdir})")

        try:
            result = subprocess.run(
                command,
                capture_output=True,
                timeout=timeout,
                cwd=workdir,
                text=True,
            )

            return SandboxResult(
                stdout=result.stdout,
                stderr=result.stderr,
                exit_code=result.returncode,
            )

        except subprocess.TimeoutExpired:
            logger.warning(f"Subprocess sandbox: Command timed out after {timeout}s")
            return SandboxResult(
                stdout="",
                stderr=f"Command timed out after {timeout}s",
                exit_code=124,
                timed_out=True,
            )

        except Exception as e:
            logger.error(f"Subprocess sandbox error: {e}")
            return SandboxResult(
                stdout="",
                stderr=str(e),
                exit_code=1,
                error=str(e),
            )


def get_sandbox_runner() -> BaseSandboxRunner:
    """
    Get the best available sandbox runner.

    Prefers Docker but falls back to subprocess if Docker is unavailable.

    Returns:
        BaseSandboxRunner instance (Docker or Subprocess)
    """
    docker_runner = DockerSandboxRunner()

    if docker_runner.is_available():
        logger.info("Using Docker sandbox runner")
        return docker_runner
    else:
        logger.warning(
            "Docker not available. Falling back to subprocess runner. "
            "This provides minimal isolation!"
        )
        return SubprocessSandboxRunner()
