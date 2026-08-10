from fastmcp import Context

from python_mcp.app import app
from python_mcp.context import ServerContext
from python_mcp.models import CheckLevel, CheckResult
from python_mcp.runner import ToolResult, changed_python_files, resolve_paths
from python_mcp.tooling import TOOLS
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

    Args:
        paths: User-supplied paths or glob patterns.
        changed_only: Whether to limit the check to modified Python files.
        server: Shared server services.

    Returns:
        list[str] | None: Resolved target paths, or ``None`` when there are
        no changed files.
    """
    if changed_only:
        changed = changed_python_files(server.project_dir)

        return changed or None

    return resolve_paths(paths or [], server.project_dir)


def _check(
    ctx: Context,
    tool_name: str,
    paths: list[str] | None,
    changed_only: bool,
    *,
    level: CheckLevel = "all",
) -> CheckResult:
    """Resolve targets and run a registered check tool."""
    server = services(ctx)
    targets = _resolve_targets(paths, changed_only, server)

    if targets is None:
        return CheckResult(output=_NO_CHANGES, exit_code=0)

    return _result(
        server.runner.run(
            TOOLS[tool_name],
            targets,
            server.project_dir,
            level=level,
        )
    )


@app.tool(name="ruff_check", annotations=READ_ONLY)
def ruff_check(
    ctx: Context,
    paths: list[str] | None = None,
    changed_only: bool = False,
) -> CheckResult:
    """
    Run ruff linting with token-efficient output.

    Args:
        ctx: FastMCP request context.
        paths: Paths to check, with glob support. Empty means the whole
            project.
        changed_only: Only check Python files modified in git.

    Returns:
        CheckResult: The compact check findings and exit code.
    """
    return _check(ctx, "ruff_check", paths, changed_only)


@app.tool(name="ruff_format", annotations=READ_ONLY)
def ruff_format(
    ctx: Context,
    paths: list[str] | None = None,
    changed_only: bool = False,
) -> CheckResult:
    """Check Ruff formatting without modifying files."""
    return _check(ctx, "ruff_format", paths, changed_only)


@app.tool(name="ty_check", annotations=READ_ONLY)
def ty_check(
    ctx: Context,
    paths: list[str] | None = None,
    level: CheckLevel = "all",
    changed_only: bool = False,
) -> CheckResult:
    """Run ty type checking with an optional severity filter."""
    return _check(ctx, "ty_check", paths, changed_only, level=level)


@app.tool(name="vulture_check", annotations=READ_ONLY)
def vulture_check(
    ctx: Context,
    paths: list[str] | None = None,
    changed_only: bool = False,
) -> CheckResult:
    """Find unused Python code with Vulture's dead-code analysis."""
    return _check(ctx, "vulture_check", paths, changed_only)


@app.tool(name="bandit_check", annotations=READ_ONLY)
def bandit_check(
    ctx: Context,
    paths: list[str] | None = None,
    changed_only: bool = False,
) -> CheckResult:
    """Scan Python code for common security problems with Bandit."""
    return _check(ctx, "bandit_check", paths, changed_only)


@app.tool(name="deptry_check", annotations=READ_ONLY)
def deptry_check(
    ctx: Context,
    paths: list[str] | None = None,
    changed_only: bool = False,
) -> CheckResult:
    """Find missing, unused, obsolete, and misplaced dependencies."""
    return _check(ctx, "deptry_check", paths, changed_only)


@app.tool(name="pytest_collect", annotations=READ_ONLY)
def pytest_collect(
    ctx: Context,
    paths: list[str] | None = None,
    changed_only: bool = False,
) -> CheckResult:
    """Collect pytest tests without executing them."""
    return _check(ctx, "pytest_collect", paths, changed_only)


@app.tool(name="codespell_check", annotations=READ_ONLY)
def codespell_check(
    ctx: Context,
    paths: list[str] | None = None,
    changed_only: bool = False,
) -> CheckResult:
    """Find likely spelling mistakes in project text and source files."""
    return _check(ctx, "codespell_check", paths, changed_only)


@app.tool(name="pydoclint_check", annotations=READ_ONLY)
def pydoclint_check(
    ctx: Context,
    paths: list[str] | None = None,
    changed_only: bool = False,
) -> CheckResult:
    """Check docstrings against function signatures with pydoclint."""
    return _check(ctx, "pydoclint_check", paths, changed_only)
