import json
import re
from collections import Counter
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from typing import cast

from python_mcp.models import CheckLevel, DiagnosticLevel, Finding, TokenMetrics

__all__ = [
    "AGGREGATE_MIN_FILES",
    "AGGREGATE_MIN_ISSUES",
    "MAX_DETAIL_LINES",
    "Collection",
    "calculate_metrics",
    "estimate_tokens",
    "filter_ty_level",
    "format_collection",
    "format_findings",
    "format_unformatted",
    "parse_bandit",
    "parse_codespell",
    "parse_deptry",
    "parse_pytest_collect",
    "parse_pydoclint",
    "parse_ruff",
    "parse_ruff_format",
    "parse_ty",
    "parse_vulture",
]

AGGREGATE_MIN_ISSUES = 25
AGGREGATE_MIN_FILES = 6
MAX_DETAIL_LINES = 50

_TY_SEVERITY: dict[str, DiagnosticLevel] = {"major": "error", "minor": "warning"}
_BANDIT_LEVEL: dict[str, DiagnosticLevel] = {
    "HIGH": "error",
    "MEDIUM": "warning",
    "LOW": "info",
}
_DEPTREY_LEVEL: dict[str, DiagnosticLevel] = {"DEP004": "warning"}

_RUFF_CONCISE = re.compile(
    r"^([^:]+):(\d+):(\d+):\s+(\w+)\s+(\[\*\]\s+)?(.+)$",
    re.MULTILINE,
)
_TY_CONCISE = re.compile(
    r"^([^:]+):(\d+):(\d+):\s*(error|warning|info)\[([^\]]+)\]\s+(.+)$",
    re.MULTILINE,
)
_VULTURE_CONCISE = re.compile(
    r"^(.+):(\d+):\s+(.+?)(?:\s+\((\d+)% confidence\))?$", re.MULTILINE
)
_DEPTREY_CONCISE = re.compile(r"^([^:]+):(\d+):(\d+):\s+(\w+)\s+(.+)$", re.MULTILINE)
_CODESPELL_CONCISE = re.compile(r"^(.+):(\d+):\s+(.+?)\s+==>\s+(.+)$", re.MULTILINE)
_PYTEST_COLLECT_ERROR = re.compile(r"^ERROR\s+(.+)$", re.MULTILINE)
_PYDOCLINT_VIOLATION = re.compile(r"^\s+(\d+):\s+(DOC\d+):\s+(.+)$", re.MULTILINE)


@dataclass(frozen=True, slots=True)
class Collection:
    """Parsed ``pytest --collect-only`` output."""

    tests: list[str]
    errors: list[Finding]


def estimate_tokens(text: str) -> int:
    """Estimate the token count of a text using the plugin's heuristic."""
    if not text:
        return 0

    total = 0

    for segment in re.findall(r"\s+|[A-Za-z0-9_]+|[^\sA-Za-z0-9_]", text):
        if re.fullmatch(r"\s+|[A-Za-z0-9_]+", segment):
            total += max(1, -(-len(segment) // 4))
        else:
            total += len(segment)

    return total


def calculate_metrics(raw_output: str, processed_output: str) -> TokenMetrics:
    """
    Estimate the token savings of the processed output versus raw output.

    Args:
        raw_output: Output the model would have seen without processing.
        processed_output: Compact output the model actually sees.

    Returns:
        TokenMetrics: Token metrics for the run.
    """
    raw_tokens = estimate_tokens(raw_output)
    processed_tokens = estimate_tokens(processed_output)
    saved_tokens = raw_tokens - processed_tokens

    return TokenMetrics(
        raw_tokens=raw_tokens,
        processed_tokens=processed_tokens,
        saved_tokens=saved_tokens,
        savings_percent=(
            round((saved_tokens / raw_tokens) * 100) if raw_tokens > 0 else 0
        ),
    )


def parse_ruff(output: str) -> list[Finding]:
    """
    Parse ruff JSON output into findings, with a concise-text fallback.

    Args:
        output: Combined stdout and stderr of ``ruff check``.

    Returns:
        list[Finding]: Parsed lint findings, or ``[]`` when nothing was found.
    """
    try:
        return [
            Finding(
                file=item["filename"],
                line=item["location"]["row"],
                col=item["location"]["column"],
                code=item["code"],
                message=item["message"],
                fixable=(
                    isinstance(item.get("fix"), dict)
                    and item["fix"].get("applicability") in ("safe", "unsafe")
                ),
            )
            for item in json.loads(output)
        ]
    except json.JSONDecodeError, KeyError, TypeError:
        return [
            Finding(
                file=match[1],
                line=int(match[2]),
                col=int(match[3]),
                code=match[4],
                fixable=match[5] is not None,
                message=match[6].strip(),
            )
            for match in _RUFF_CONCISE.finditer(output)
        ]


def parse_ty(output: str) -> list[Finding]:
    """
    Parse ty GitLab code-quality JSON into findings.

    Falls back to parsing the concise text format for older ty versions.

    Args:
        output: Combined stdout and stderr of ``ty check``.

    Returns:
        list[Finding]: Parsed diagnostics, or ``[]`` when nothing was found.
    """
    try:
        return [
            Finding(
                file=item["location"]["path"],
                line=item["location"]["positions"]["begin"]["line"],
                col=item["location"]["positions"]["begin"]["column"],
                level=_TY_SEVERITY.get(item.get("severity", ""), "info"),
                code=item["check_name"],
                message=_ty_description(item["check_name"], item["description"]),
            )
            for item in json.loads(output)
        ]
    except json.JSONDecodeError, KeyError, TypeError:
        return [
            Finding(
                file=match[1],
                line=int(match[2]),
                col=int(match[3]),
                level=cast(DiagnosticLevel, match[4]),
                code=match[5],
                message=match[6].strip(),
            )
            for match in _TY_CONCISE.finditer(output)
        ]


def parse_vulture(output: str) -> list[Finding]:
    """Parse vulture's concise dead-code findings."""
    return [
        Finding(
            file=match[1],
            line=int(match[2]),
            message=match[3].strip(),
            confidence=int(match[4]) if match[4] else None,
        )
        for match in _VULTURE_CONCISE.finditer(output)
    ]


def parse_bandit(output: str) -> list[Finding]:
    """
    Parse bandit JSON output into security findings.

    Args:
        output: Combined stdout and stderr of ``bandit -f json``.

    Returns:
        list[Finding]: Parsed security findings, or ``[]`` when nothing was found.
    """
    try:
        data = json.loads(output)
    except json.JSONDecodeError, TypeError:
        return []

    findings: list[Finding] = []

    for item in data.get("results", []):
        severity = item.get("issue_severity")
        findings.append(
            Finding(
                file=item["filename"],
                line=item.get("line_number", 0),
                col=item.get("col_offset", 0) + 1,
                code=item.get("test_id"),
                message=item["issue_text"],
                level=_BANDIT_LEVEL.get(severity, "error"),
                severity=severity,
            )
        )

    return findings


def parse_deptry(output: str) -> list[Finding]:
    """
    Parse deptry's concise text output into dependency findings.

    Args:
        output: Combined stdout and stderr of ``deptry --no-ansi``.

    Returns:
        list[Finding]: Parsed dependency findings, or ``[]`` when nothing was
        found.
    """
    return [
        Finding(
            file=match[1],
            line=int(match[2]),
            col=int(match[3]),
            code=match[4],
            level=_DEPTREY_LEVEL.get(match[4], "error"),
            message=match[5].strip(),
        )
        for match in _DEPTREY_CONCISE.finditer(output)
    ]


def parse_codespell(output: str) -> list[Finding]:
    """
    Parse codespell's concise output into typo findings.

    Args:
        output: Combined stdout and stderr of ``codespell``.

    Returns:
        list[Finding]: Parsed typo findings, or ``[]`` when nothing was found.
    """
    return [
        Finding(
            file=match[1],
            line=int(match[2]),
            message=match[3].strip(),
            suggestion=match[4].strip(),
        )
        for match in _CODESPELL_CONCISE.finditer(output)
    ]


def parse_pydoclint(output: str) -> list[Finding]:
    """
    Parse pydoclint output into docstring violations.

    Args:
        output: Combined stdout and stderr of ``pydoclint``.

    Returns:
        list[Finding]: Parsed violations, or ``[]`` when nothing was found.
    """
    current_file: str | None = None
    findings: list[Finding] = []

    for line in output.splitlines():
        if not line.startswith((" ", "\t")):
            current_file = line.strip()
            continue
        match = _PYDOCLINT_VIOLATION.match(line)
        if match and current_file:
            findings.append(
                Finding(
                    file=current_file,
                    line=int(match[1]),
                    code=match[2],
                    message=match[3],
                )
            )

    return findings


def parse_ruff_format(output: str) -> list[str]:
    """
    Extract the files needing reformatting from ``ruff format --check``.

    Args:
        output: Combined stdout and stderr of ``ruff format --check``.

    Returns:
        list[str]: The unformatted file paths.
    """
    return [
        line.removeprefix("Would reformat: ").strip()
        for line in output.splitlines()
        if line.startswith("Would reformat: ")
    ]


def parse_pytest_collect(output: str) -> Collection:
    """
    Parse ``pytest --collect-only -q`` output into tests and collection errors.

    Args:
        output: Combined stdout and stderr of ``pytest --collect-only -q``.

    Returns:
        Collection: The collected test node IDs and any collection-error
        findings.
    """
    tests = [
        line.strip()
        for line in output.splitlines()
        if "::" in line and not line.startswith((" ", "E", "!", "-", "_"))
    ]
    errors = [
        Finding(file=match[1], message="pytest collection error")
        for match in _PYTEST_COLLECT_ERROR.finditer(output)
    ]

    return Collection(tests=tests, errors=errors)


def filter_ty_level(findings: list[Finding], level: CheckLevel) -> list[Finding]:
    """
    Filter ty diagnostics by severity.

    Args:
        findings: Parsed diagnostics.
        level: ``error`` keeps errors, ``warning`` keeps warnings and errors,
            ``all`` keeps everything.

    Returns:
        list[Finding]: The filtered diagnostics.
    """
    match level:
        case "error":
            return [finding for finding in findings if finding.level == "error"]
        case "warning":
            return [finding for finding in findings if finding.level == "warning"]
        case _:
            return findings


def format_findings(
    findings: list[Finding],
    *,
    name: str,
    empty_message: str,
    render_line: Callable[[Finding], str],
) -> str:
    """
    Format findings compactly, aggregated for large result sets.

    Args:
        findings: Findings to format.
        name: Tool label used in the header (e.g. ``ruff``).
        empty_message: Output when there are no findings.
        render_line: One-line rendering of a single finding.

    Returns:
        str: The compact, token-efficient output.
    """
    if not findings:
        return empty_message
    if _use_aggregate(findings):
        return _format_aggregate(findings, name=name, render_line=render_line)

    return _format_grouped(
        header=_header(findings, name),
        findings=findings,
        render_line=render_line,
    )


def format_unformatted(files: list[str], *, name: str) -> str:
    """
    Format the list of unformatted files compactly.

    Args:
        files: Files needing reformatting.
        name: Tool label used in the header.

    Returns:
        str: The compact output.
    """
    if not files:
        return "All files properly formatted."

    lines = [f"{name}: {len(files)} files need formatting", ""]
    lines.extend(f"  {file}" for file in sorted(files))

    return "\n".join(lines).strip()


def format_collection(collection: Collection, *, name: str, empty_message: str) -> str:
    """
    Format collected tests and collection errors compactly.

    Args:
        collection: Parsed pytest collection output.
        name: Tool label used in the header.
        empty_message: Output when nothing was collected.

    Returns:
        str: The compact output.
    """
    if collection.errors:
        lines = [f"{name}: {len(collection.errors)} collection errors", ""]
        lines.extend(
            f"  {error.file}: {error.message}"
            for error in sorted(collection.errors, key=lambda error: error.file)
        )

        return "\n".join(lines).strip()

    if not collection.tests:
        return empty_message

    lines = [f"{name}: {len(collection.tests)} tests collected", ""]
    lines.extend(f"  {test}" for test in sorted(collection.tests))

    return "\n".join(lines).strip()


def _ty_description(code: str, description: str) -> str:
    """Remove GitLab's duplicated ``<code>: `` message prefix."""
    return description.removeprefix(f"{code}: ")


def _header(findings: list[Finding], name: str) -> str:
    """Build the compact header line for a result set."""
    files = len({finding.file for finding in findings})

    return f"{name}: {len(findings)} issues in {files} files"


def _use_aggregate(findings: list[Finding]) -> bool:
    """True when the result set is large enough to warrant rollups."""
    return (
        len(findings) >= AGGREGATE_MIN_ISSUES
        or len({finding.file for finding in findings}) >= AGGREGATE_MIN_FILES
    )


def _format_grouped(
    *,
    header: str,
    findings: list[Finding],
    render_line: Callable[[Finding], str],
) -> str:
    """Format findings grouped by file, the plugin's compact layout."""
    by_file: dict[str, list[Finding]] = {}

    for finding in sorted(findings, key=lambda error: (error.file, error.line)):
        by_file.setdefault(finding.file, []).append(finding)

    out = [header, ""]

    for file in sorted(by_file):
        out.append(f"## {file}")

        for finding in by_file[file]:
            out.append(render_line(finding))
        out.append("")

    return "\n".join(out).strip()


def _format_aggregate(
    findings: list[Finding],
    *,
    name: str,
    render_line: Callable[[Finding], str],
) -> str:
    """Large-result layout: rule/file rollups plus flat diagnostic lines."""
    out = [_header(findings, name), ""]
    out.append("Top rules:")

    for key, count in _ranked_counts(_rule_key(finding) for finding in findings):
        out.append(f"  {key} ({count}x)")

    out.append("")
    out.append("Top files:")
    by_file: dict[str, list[Finding]] = {}

    for finding in findings:
        by_file.setdefault(finding.file, []).append(finding)

    for file, file_findings in _ranked_groups(by_file):
        out.append(f"  {file} ({len(file_findings)} issues)")

        for key, count in _ranked_counts(_rule_key(f) for f in file_findings):
            out.append(f"    {key} ({count})")

    out.append("")
    out.append("Findings:")
    details = sorted(findings, key=lambda error: (error.file, error.line, error.col))

    for finding in details[:MAX_DETAIL_LINES]:
        out.append(render_line(finding))

    _append_omission(out, len(details), "findings")

    return "\n".join(out).strip()


def _rule_key(finding: Finding) -> str:
    """Return the rule used for rollups, falling back to the message."""
    return finding.code or finding.message


def _level_mark(level: str) -> str:
    """Map a diagnostic level to its one-letter marker."""
    match level:
        case "error":
            return "E"
        case _:
            return "W"


def _ranked_counts(values: Iterable[str]) -> list[tuple[str, int]]:
    """Return deterministic descending counts for an iterable of strings."""
    counts = Counter(values)

    return sorted(counts.items(), key=lambda item: (-item[1], item[0]))


def _ranked_groups[T](groups: dict[str, list[T]]) -> list[tuple[str, list[T]]]:
    """Return groups ranked by size, then name."""
    return sorted(groups.items(), key=lambda item: (-len(item[1]), item[0]))


def _append_omission(lines: list[str], total: int, noun: str) -> None:
    """Add a compact pointer when detail lines were intentionally capped."""
    remaining = total - MAX_DETAIL_LINES

    if remaining > 0:
        lines.append(f"  ... +{remaining} more {noun}")
