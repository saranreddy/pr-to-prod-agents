"""Unit tests for sandbox runner."""

from unittest.mock import MagicMock, patch

import pytest

from pr_to_prod.sandbox.runner import (
    DockerSandboxRunner,
    SandboxResult,
    SubprocessSandboxRunner,
    get_sandbox_runner,
)


def test_docker_runner_is_available_when_docker_works():
    """Test Docker availability check when docker info succeeds."""
    runner = DockerSandboxRunner()

    with patch("subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=0)
        assert runner.is_available() is True


def test_docker_runner_not_available_when_docker_missing():
    """Test Docker availability check when docker command not found."""
    runner = DockerSandboxRunner()

    with patch("subprocess.run", side_effect=FileNotFoundError):
        assert runner.is_available() is False


def test_docker_runner_not_available_when_docker_fails():
    """Test Docker availability check when docker info fails."""
    runner = DockerSandboxRunner()

    with patch("subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=1)
        assert runner.is_available() is False


@pytest.mark.asyncio
async def test_docker_runner_executes_command():
    """Test Docker runner executes command successfully."""
    runner = DockerSandboxRunner()

    with patch("subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout="hello",
            stderr="",
        )

        with patch.object(runner, "is_available", return_value=True):
            result = await runner.run(
                command=["echo", "hello"],
                workdir="/tmp/test",
            )

        assert result.exit_code == 0
        assert result.stdout == "hello"
        assert result.timed_out is False
        assert result.error is None

        # Verify docker command was constructed correctly
        call_args = mock_run.call_args[0][0]
        assert "docker" in call_args
        assert "--rm" in call_args
        assert "--network=none" in call_args


@pytest.mark.asyncio
async def test_docker_runner_handles_timeout():
    """Test Docker runner handles command timeout."""
    runner = DockerSandboxRunner()

    with patch("subprocess.run") as mock_run:
        import subprocess

        mock_run.side_effect = subprocess.TimeoutExpired(cmd="test", timeout=10)

        with patch.object(runner, "is_available", return_value=True):
            result = await runner.run(
                command=["sleep", "1000"],
                workdir="/tmp/test",
                timeout=1,
            )

        assert result.exit_code == 124
        assert result.timed_out is True
        assert "timed out" in result.stderr.lower()


@pytest.mark.asyncio
async def test_docker_runner_raises_when_unavailable():
    """Test Docker runner raises error when Docker not available."""
    runner = DockerSandboxRunner()

    with patch.object(runner, "is_available", return_value=False):
        with pytest.raises(RuntimeError, match="Docker is not available"):
            await runner.run(command=["echo", "test"], workdir="/tmp")


def test_subprocess_runner_is_always_available():
    """Test subprocess runner is always available."""
    runner = SubprocessSandboxRunner()
    assert runner.is_available() is True


@pytest.mark.asyncio
async def test_subprocess_runner_executes_command():
    """Test subprocess runner executes command successfully."""
    runner = SubprocessSandboxRunner()

    with patch("subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout="output",
            stderr="",
        )

        result = await runner.run(
            command=["echo", "output"],
            workdir="/tmp/test",
        )

        assert result.exit_code == 0
        assert result.stdout == "output"
        assert result.timed_out is False


@pytest.mark.asyncio
async def test_subprocess_runner_handles_timeout():
    """Test subprocess runner handles timeout."""
    runner = SubprocessSandboxRunner()

    with patch("subprocess.run") as mock_run:
        import subprocess

        mock_run.side_effect = subprocess.TimeoutExpired(cmd="test", timeout=5)

        result = await runner.run(
            command=["sleep", "1000"],
            workdir="/tmp/test",
            timeout=1,
        )

        assert result.exit_code == 124
        assert result.timed_out is True


def test_get_sandbox_runner_returns_docker_when_available():
    """Test get_sandbox_runner returns Docker when available."""
    with patch.object(DockerSandboxRunner, "is_available", return_value=True):
        runner = get_sandbox_runner()
        assert isinstance(runner, DockerSandboxRunner)


def test_get_sandbox_runner_falls_back_to_subprocess():
    """Test get_sandbox_runner falls back to subprocess when Docker unavailable."""
    with patch.object(DockerSandboxRunner, "is_available", return_value=False):
        runner = get_sandbox_runner()
        assert isinstance(runner, SubprocessSandboxRunner)
