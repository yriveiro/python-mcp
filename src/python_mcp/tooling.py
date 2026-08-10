from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from python_mcp.formatting import (
    calculate_metrics,
    filter_ty_level,
    format_collection,
    format_findings,
    format_unformatted,
    parse_bandit,
    parse_codespell,
    parse_deptry,
    parse_pydoclint,
    parse_pytest_collect,
    parse_ruff,
    parse_ruff_format,
    parse_ty,
    parse_vulture,
)
from python_mcp.models import CheckLevel, Finding
from python_mcp.runner import CheckTool, ProcessResult, ToolResult, relativize_paths

FindingParser = Callable[[str], list[Finding]]
FindingFilter = Callable[[list[Finding], CheckLevel], list[Finding]]
FindingRenderer = Callable[[Finding], str]


@dataclass(frozen=True, slots=True)
class FindingTool:
    """
    Specification for a tool that reports file findings.

    Args:
        name: MCP tool name.
        label: Short label used in formatted output.
        empty_message: Output used when no findings are reported.
        command_builder: Function that builds tool-specific arguments.
        parser: Function that parses raw command output.
        renderer: Function that renders one finding.
        filter_findings: Optional request-level finding filter.

    Attributes:
        name: MCP tool name.
        label: Short label used in formatted output.
        empty_message: Output used when no findings are reported.
        command_builder: Function that builds tool-specific arguments.
        parser: Function that parses raw command output.
        renderer: Function that renders one finding.
        filter_findings: Optional request-level finding filter.
    """

    name: str
    label: str
    empty_message: str
    command_builder: Callable[[list[str]], list[str]]
    parser: FindingParser
    renderer: FindingRenderer
    filter_findings: FindingFilter | None = None

    def command(self, paths: list[str]) -> list[str]:
        """Build the command arguments for this tool."""
        return self.command_builder(paths)

    def process(
        self,
        result: ProcessResult,
        cwd: str | Path,
        *,
        level: CheckLevel = "all",
    ) -> ToolResult:
        """Parse, compact, and summarize a tool result."""
        findings = self.parser(result.output)
        relativize_paths(findings, cwd)

        if self.filter_findings is not None:
            findings = self.filter_findings(findings, level)

        output = format_findings(
            findings,
            name=self.label,
            empty_message=self.empty_message,
            render_line=self.renderer,
        )

        if result.exit_code != 0 and not findings:
            output = result.output[:2000] or f"{self.label} check failed."

        return ToolResult(
            output=output,
            exit_code=result.exit_code,
            issues=len(findings),
            fixable=sum(finding.fixable for finding in findings),
            warnings=sum(finding.level == "warning" for finding in findings),
            metrics=calculate_metrics(_concise(findings), output),
        )


@dataclass(frozen=True, slots=True)
class RuffFormatTool:
    """Specification for Ruff's read-only formatting check."""

    name: str = "ruff_format"

    def command(self, paths: list[str]) -> list[str]:
        """Build the Ruff format-check command."""
        return ["ruff", "format", "--check", *paths]

    def process(
        self,
        result: ProcessResult,
        cwd: str | Path,
        *,
        level: CheckLevel = "all",
    ) -> ToolResult:
        """Format Ruff's unformatted-file output."""
        del cwd, level
        files = parse_ruff_format(result.output)
        output = format_unformatted(files, name="ruff format")

        if result.exit_code != 0 and not files:
            output = result.output[:2000] or "Ruff format check failed."

        return ToolResult(
            output=output,
            exit_code=result.exit_code,
            issues=len(files),
            metrics=calculate_metrics(result.output, output),
        )


@dataclass(frozen=True, slots=True)
class PytestCollectTool:
    """Specification for pytest's read-only test collection check."""

    name: str = "pytest_collect"

    def command(self, paths: list[str]) -> list[str]:
        """Build the pytest collection command."""
        return ["pytest", "--collect-only", "-q", *paths]

    def process(
        self,
        result: ProcessResult,
        cwd: str | Path,
        *,
        level: CheckLevel = "all",
    ) -> ToolResult:
        """Format collected tests and collection errors."""
        del level
        collection = parse_pytest_collect(result.output)
        relativize_paths(collection.errors, cwd)
        output = format_collection(
            collection,
            name="pytest",
            empty_message="No tests found.",
        )

        if result.exit_code != 0 and not collection.errors and not collection.tests:
            output = result.output[:2000] or "Pytest collection failed."

        return ToolResult(
            output=output,
            exit_code=result.exit_code,
            issues=len(collection.errors),
            metrics=calculate_metrics(result.output, output),
        )


def _ruff_command(paths: list[str]) -> list[str]:
    """Build Ruff's JSON lint command."""
    return ["ruff", "check", "--output-format", "json", *paths]


def _ty_command(paths: list[str]) -> list[str]:
    """Build ty's GitLab-output type-check command."""
    return ["ty", "check", "--output-format", "gitlab", *paths]


def _vulture_command(paths: list[str]) -> list[str]:
    """Build Vulture's dead-code command with common-directory exclusions."""
    return [
        "vulture",
        "--exclude",
        ".venv,venv,.git,__pycache__",
        *(paths or ["."]),
    ]


def _bandit_command(paths: list[str]) -> list[str]:
    """Build Bandit's quiet JSON security scan command."""
    return ["bandit", "-r", "-f", "json", "-q", *(paths or ["."])]


def _deptry_command(paths: list[str]) -> list[str]:
    """Build deptry's ANSI-free dependency scan command."""
    return ["deptry", "--no-ansi", *(paths or ["."])]


def _codespell_command(paths: list[str]) -> list[str]:
    """Build codespell's typo scan command."""
    return ["codespell", *paths]


def _pydoclint_command(paths: list[str]) -> list[str]:
    """Build pydoclint's docstring check command."""
    return ["pydoclint", *paths]


def _render_ruff(finding: Finding) -> str:
    """Render a Ruff finding."""
    fix = "*" if finding.fixable else ""

    return f"  L{finding.line}:{finding.col} [{finding.code}{fix}] {finding.message}"


def _render_ty(finding: Finding) -> str:
    """Render a ty diagnostic."""
    level = "E" if finding.level == "error" else "W"

    return f"  L{finding.line}:{finding.col} [{level}:{finding.code}] {finding.message}"


def _render_vulture(finding: Finding) -> str:
    """Render a Vulture finding."""
    confidence = f" ({finding.confidence}% confidence)" if finding.confidence else ""

    return f"  L{finding.line} {finding.message}{confidence}"


def _render_bandit(finding: Finding) -> str:
    """Render a Bandit finding."""
    severity = f" {finding.severity}" if finding.severity else ""

    return f"  L{finding.line} [{finding.code}{severity}] {finding.message}"


def _render_deptry(finding: Finding) -> str:
    """Render a deptry finding."""
    return f"  L{finding.line}:{finding.col} [{finding.code}] {finding.message}"


def _render_codespell(finding: Finding) -> str:
    """Render a codespell finding."""
    suggestion = f" ==> {finding.suggestion}" if finding.suggestion else ""

    return f"  L{finding.line} {finding.message}{suggestion}"


def _render_pydoclint(finding: Finding) -> str:
    """Render a pydoclint finding."""
    return f"  L{finding.line} [{finding.code}] {finding.message}"


def _concise(findings: list[Finding]) -> str:
    """Build a compact raw-equivalent string for token-savings metrics."""
    lines = [
        f"{finding.file}:{finding.line}:{finding.col}: "
        f"{finding.code or ''} {finding.message}".strip()
        for finding in findings
    ]

    if findings:
        lines.append(f"Found {len(findings)} issues.")

    return "\n".join(lines)


TOOLS: dict[str, CheckTool] = {
    "ruff_check": FindingTool(
        name="ruff_check",
        label="ruff",
        empty_message="No lint issues found.",
        command_builder=_ruff_command,
        parser=parse_ruff,
        renderer=_render_ruff,
    ),
    "ruff_format": RuffFormatTool(),
    "ty_check": FindingTool(
        name="ty_check",
        label="ty",
        empty_message="No type errors found.",
        command_builder=_ty_command,
        parser=parse_ty,
        renderer=_render_ty,
        filter_findings=filter_ty_level,
    ),
    "vulture_check": FindingTool(
        name="vulture_check",
        label="vulture",
        empty_message="No dead code found.",
        command_builder=_vulture_command,
        parser=parse_vulture,
        renderer=_render_vulture,
    ),
    "bandit_check": FindingTool(
        name="bandit_check",
        label="bandit",
        empty_message="No security issues found.",
        command_builder=_bandit_command,
        parser=parse_bandit,
        renderer=_render_bandit,
    ),
    "deptry_check": FindingTool(
        name="deptry_check",
        label="deptry",
        empty_message="No dependency issues found.",
        command_builder=_deptry_command,
        parser=parse_deptry,
        renderer=_render_deptry,
    ),
    "pytest_collect": PytestCollectTool(),
    "codespell_check": FindingTool(
        name="codespell_check",
        label="codespell",
        empty_message="No spelling issues found.",
        command_builder=_codespell_command,
        parser=parse_codespell,
        renderer=_render_codespell,
    ),
    "pydoclint_check": FindingTool(
        name="pydoclint_check",
        label="pydoclint",
        empty_message="No docstring issues found.",
        command_builder=_pydoclint_command,
        parser=parse_pydoclint,
        renderer=_render_pydoclint,
    ),
}
