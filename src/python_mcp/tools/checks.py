from fastmcp import Context

from python_mcp.app import app
from python_mcp.context import ServerContext
from python_mcp.models import CheckLevel, CheckResult
from python_mcp.runner import ToolResult, changed_python_files, resolve_paths
from python_mcp.tools.common import READ_ONLY, services

_NO_CHANGES = "No modified Python files found."


def _result(result: ToolResult) -> CheckResult:
    """Convert an internal runner result to the public MCP model."""
    metrics = result.metrics

    return CheckResult(
        output=result.output,
        exit_code=result.exit_code,
        issues=result.issues,
        fixable=result.fixable,
        warnings=result.warnings,
        saved_tokens=metrics.saved_tokens if metrics else 0,
        savings_percent=metrics.savings_percent if metrics else 0,
    )


def _resolve_targets(
    paths: list[str] | None,
    changed_only: bool,
    server: ServerContext,
) -> list[str] | None:
    """
    Resolve the target paths for a check run.

    Returns ``None`` when ``changed_only`` is set and git reports no modified
    Python files.

    Args:
        paths: User-supplied paths or glob patterns.
        changed_only: Check only git-modified Python files.
        server: Shared server services.

    Returns:
        Resolved target paths, or ``None`` for nothing to check.
    """
    if changed_only:
        changed = changed_python_files(server.project_dir)

        return changed or None

    return resolve_paths(paths or [], server.project_dir)


@app.tool(name="ruff_check", annotations=READ_ONLY)
def ruff_check(
    ctx: Context,
    paths: list[str] | None = None,
    changed_only: bool = False,
) -> CheckResult:
    """
    Run ruff linting with token-efficient output.

    Output groups issues by rule and file, dropping repetition. Use
    ``changed_only`` for fast feedback on recently edited files.

    Args:
        paths: Paths to check, with glob support (e.g. ``src/**/*.py``). Empty
            means the whole project.
        changed_only: Only check Python files modified in git (staged,
            unstaged, and untracked).
        ctx: FastMCP request context.

    Returns:
        Compact lint findings and the command exit code.
    """
    server = services(ctx)
    targets = _resolve_targets(paths, changed_only, server)

    if targets is None:
        return CheckResult(output=_NO_CHANGES, exit_code=0)

    return _result(server.runner.ruff_check(targets, server.project_dir))


@app.tool(name="ruff_format", annotations=READ_ONLY)
def ruff_format(
    ctx: Context,
    paths: list[str] | None = None,
    changed_only: bool = False,
) -> CheckResult:
    """
    Check ruff formatting without modifying files.

    Args:
        paths: Paths to check, with glob support (e.g. ``src/**/*.py``). Empty
            means the whole project.
        changed_only: Only check Python files modified in git (staged,
            unstaged, and untracked).
        ctx: FastMCP request context.

    Returns:
        Files needing formatting and the command exit code.
    """
    server = services(ctx)
    targets = _resolve_targets(paths, changed_only, server)

    if targets is None:
        return CheckResult(output=_NO_CHANGES, exit_code=0)

    return _result(server.runner.ruff_format_check(targets, server.project_dir))


@app.tool(name="ty_check", annotations=READ_ONLY)
def ty_check(
    ctx: Context,
    paths: list[str] | None = None,
    level: CheckLevel = "all",
    changed_only: bool = False,
) -> CheckResult:
    """
    Run the ty type checker with token-efficient output.

    Args:
        paths: Paths to check, with glob support (e.g. ``src/**/*.py``). Empty
            means the whole project.
        level: Severity filter: ``all``, ``error``, or ``warning``.
        changed_only: Only check Python files modified in git (staged,
            unstaged, and untracked).
        ctx: FastMCP request context.

    Returns:
        Compact diagnostics and the command exit code.
    """
    server = services(ctx)
    targets = _resolve_targets(paths, changed_only, server)

    if targets is None:
        return CheckResult(output=_NO_CHANGES, exit_code=0)

    return _result(server.runner.ty_check(targets, level, server.project_dir))
