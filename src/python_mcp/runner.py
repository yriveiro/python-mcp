import glob
import logging
import os
import shlex
import subprocess
from pathlib import Path

from pydantic import BaseModel

from python_mcp.errors import ToolNotFoundError
from python_mcp.formatting import (
    calculate_metrics,
    filter_ty_level,
    format_ruff_check,
    format_ruff_format,
    format_ty_check,
    parse_ruff_check,
    parse_ruff_format,
    parse_ty_check,
)
from python_mcp.models import CheckLevel, RuffError, TokenMetrics, TyError

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


class ToolRunner:
    """
    Execute ruff and ty using the project's configured environment.

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

    def ruff_check(self, paths: list[str], cwd: str | Path) -> ToolResult:
        """Run ruff check and compact its structured JSON output."""
        command = [
            *self.command_prefix,
            "ruff",
            "check",
            "--output-format",
            "json",
            *paths,
        ]
        result = self._run(command, cwd)
        errors = parse_ruff_check(result.output)
        _relativize_paths(errors, cwd)
        output = format_ruff_check(errors)

        if result.exit_code != 0 and not errors:
            output = result.output[:2000] or "Ruff check failed."

        raw = _ruff_concise(errors)
        metrics = calculate_metrics(raw, output)

        return ToolResult(
            output=output,
            exit_code=result.exit_code,
            issues=len(errors),
            fixable=sum(error.fixable for error in errors),
            metrics=metrics,
        )

    def ruff_format_check(self, paths: list[str], cwd: str | Path) -> ToolResult:
        """Run ruff format in check mode and compact its output."""
        command = [*self.command_prefix, "ruff", "format", "--check", *paths]
        result = self._run(command, cwd)
        files = parse_ruff_format(result.output)
        output = format_ruff_format(files)

        if result.exit_code != 0 and not files:
            output = result.output[:2000] or "Ruff format check failed."

        return ToolResult(
            output=output,
            exit_code=result.exit_code,
            issues=len(files),
            metrics=calculate_metrics(result.output, output),
        )

    def ty_check(
        self,
        paths: list[str],
        level: CheckLevel,
        cwd: str | Path,
    ) -> ToolResult:
        """Run ty with GitLab JSON output and filter by severity."""
        command = [
            *self.command_prefix,
            "ty",
            "check",
            "--output-format",
            "gitlab",
            *paths,
        ]
        result = self._run(command, cwd)
        all_errors = parse_ty_check(result.output)
        _relativize_paths(all_errors, cwd)
        errors = filter_ty_level(all_errors, level)
        output = format_ty_check(errors)

        if result.exit_code != 0 and not all_errors:
            output = result.output[:2000] or "Ty check failed."

        raw = _ty_concise(all_errors)

        return ToolResult(
            output=output,
            exit_code=result.exit_code,
            issues=len(errors),
            warnings=sum(error.level == "warning" for error in errors),
            metrics=calculate_metrics(raw, output),
        )

    def _run(self, command: list[str], cwd: str | Path) -> ProcessResult:
        """Run a command and capture output without raising on exit codes."""
        try:
            result = subprocess.run(
                command,
                capture_output=True,
                text=True,
                check=False,
                cwd=str(cwd),
                timeout=self.command_timeout,
            )
        except FileNotFoundError as e:
            raise ToolNotFoundError(
                f"Executable not found: {command[0]}. "
                "Install uv or set PYTHON_MCP_COMMAND_PREFIX to the project tooling."
            ) from e
        except subprocess.TimeoutExpired as e:
            logger.error(
                "command timed out after %s seconds: %s",
                self.command_timeout,
                command,
            )
            raise ToolNotFoundError(
                f"Command timed out after {self.command_timeout} seconds: "
                f"{' '.join(command)}"
            ) from e
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


def _run_git(command: list[str], cwd: str | Path) -> str | None:
    """Run a git command, returning stdout or ``None`` when it fails."""
    try:
        result = subprocess.run(
            command,
            capture_output=True,
            text=True,
            check=False,
            cwd=str(cwd),
        )
    except FileNotFoundError, OSError:
        return None

    return result.stdout if result.returncode == 0 else None


def _relativize_paths(errors: list[RuffError] | list[TyError], cwd: str | Path) -> None:
    """Make absolute diagnostic paths relative to the checked project."""
    root = Path(cwd).resolve()

    for error in errors:
        path = Path(error.file)

        if path.is_absolute():
            try:
                error.file = os.fspath(path.resolve().relative_to(root))
            except ValueError:
                error.file = os.fspath(path)


def _ruff_concise(errors: list[RuffError]) -> str:
    """Reconstruct concise ruff output for savings comparison."""
    lines = [
        f"{error.file}:{error.line}:{error.col}: {error.code} "
        f"{'[*] ' if error.fixable else ''}{error.message}"
        for error in errors
    ]

    if errors:
        lines.append(f"Found {len(errors)} errors.")

    return "\n".join(lines)


def _ty_concise(errors: list[TyError]) -> str:
    """Reconstruct concise ty output for savings comparison."""
    lines = [
        f"{error.file}:{error.line}:{error.col}: {error.level}[{error.code}] "
        f"{error.message}"
        for error in errors
    ]

    if errors:
        lines.append(f"Found {len(errors)} diagnostics")

    return "\n".join(lines)
