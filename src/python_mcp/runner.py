import glob
import logging
import os
import shlex
import subprocess  # nosec B404
from pathlib import Path
from typing import Protocol

from pydantic import BaseModel

from python_mcp.errors import ToolNotFoundError
from python_mcp.models import CheckLevel, Finding, TokenMetrics

logger = logging.getLogger(__name__)


class ProcessResult(BaseModel):
    """Raw output and exit code from a subprocess."""

    output: str
    exit_code: int


class ToolResult(BaseModel):
    """Formatted result returned by one tool execution."""

    output: str
    exit_code: int
    issues: int = 0
    fixable: int = 0
    warnings: int = 0
    metrics: TokenMetrics | None = None


class CheckTool(Protocol):
    """Interface implemented by a read-only code-quality check."""

    @property
    def name(self) -> str:
        """Return the MCP tool name."""
        ...

    def command(self, paths: list[str]) -> list[str]:
        """Build the executable arguments for the target paths."""
        ...

    def process(
        self,
        result: ProcessResult,
        cwd: str | Path,
        *,
        level: CheckLevel = "all",
    ) -> ToolResult:
        """Convert raw command output into a compact tool result."""
        ...


class ToolRunner:
    """
    Execute configured code-quality tools in the project's environment.

    Args:
        command_prefix: Prefix for tool invocations, usually ``"uv run"``.
        command_timeout: Timeout in seconds for each command.
    """

    def __init__(
        self,
        command_prefix: str = "uv run",
        command_timeout: float | None = None,
    ):
        self.command_prefix = shlex.split(command_prefix)
        self.command_timeout = command_timeout

    def run(
        self,
        tool: CheckTool,
        paths: list[str],
        cwd: str | Path,
        *,
        level: CheckLevel = "all",
    ) -> ToolResult:
        """
        Execute a check tool and process its output.

        Args:
            tool: Tool implementation to execute.
            paths: Paths passed to the tool.
            cwd: Project directory used as the subprocess working directory.
            level: Optional diagnostic severity filter.

        Returns:
            ToolResult: Compact output and execution metadata.
        """
        command = [*self.command_prefix, *tool.command(paths)]
        result = self._run(command, cwd)

        return tool.process(result, cwd, level=level)

    def _run(self, command: list[str], cwd: str | Path) -> ProcessResult:
        """Run a command and capture output without raising on exit codes."""
        try:
            result = subprocess.run(  # nosec B603
                command,
                capture_output=True,
                text=True,
                check=False,
                cwd=str(cwd),
                timeout=self.command_timeout,
            )
        except FileNotFoundError as error:
            raise ToolNotFoundError(
                f"Executable not found: {command[0]}. "
                "Install uv or set PYTHON_MCP_COMMAND_PREFIX to the project tooling."
            ) from error
        except subprocess.TimeoutExpired as error:
            logger.error(
                "command timed out after %s seconds: %s",
                self.command_timeout,
                command,
            )
            raise ToolNotFoundError(
                f"Command timed out after {self.command_timeout} seconds: "
                f"{' '.join(command)}"
            ) from error

        return ProcessResult(
            output=(result.stdout + result.stderr).strip(),
            exit_code=result.returncode,
        )


def changed_python_files(cwd: str | Path) -> list[str]:
    """List staged, unstaged, and untracked Python files in a git repository."""
    patterns = ("*.py", "*.pyi")
    tracked = _run_git(["git", "diff", "--name-only", "HEAD", "--", *patterns], cwd)
    if tracked is None:
        return []

    files = tracked.splitlines()
    untracked = _run_git(
        ["git", "ls-files", "--others", "--exclude-standard", *patterns], cwd
    )
    if untracked:
        files.extend(untracked.splitlines())

    return list(dict.fromkeys(file for file in files if file))


def resolve_paths(paths: list[str], cwd: str | Path) -> list[str]:
    """Expand glob patterns into concrete paths."""
    resolved: list[str] = []

    for pattern in paths:
        if any(char in pattern for char in "*?["):
            resolved.extend(glob.glob(pattern, root_dir=str(cwd), recursive=True))
        elif pattern:
            resolved.append(pattern)

    return resolved


def relativize_paths(findings: list[Finding], cwd: str | Path) -> None:
    """Make absolute diagnostic paths relative to the checked project."""
    root = Path(cwd).resolve()

    for finding in findings:
        path = Path(finding.file)

        if path.is_absolute():
            try:
                finding.file = os.fspath(path.resolve().relative_to(root))
            except ValueError:
                finding.file = os.fspath(path)


def _run_git(command: list[str], cwd: str | Path) -> str | None:
    """Run a git command, returning stdout or ``None`` when it fails."""
    try:
        result = subprocess.run(  # nosec B603
            command,
            capture_output=True,
            text=True,
            check=False,
            cwd=str(cwd),
        )
    except FileNotFoundError, OSError:
        return None

    return result.stdout if result.returncode == 0 else None
