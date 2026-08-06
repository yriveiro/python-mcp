import json
import re
from collections import Counter
from collections.abc import Callable, Iterable, Sequence
from typing import Any, cast

from python_mcp.models import (
    CheckLevel,
    DiagnosticLevel,
    RuffError,
    TokenMetrics,
    TyError,
)

__all__ = [
    "AGGREGATE_MIN_FILES",
    "AGGREGATE_MIN_ISSUES",
    "MAX_DETAIL_LINES",
    "calculate_metrics",
    "estimate_tokens",
    "filter_ty_level",
    "format_ruff_check",
    "format_ruff_format",
    "format_ty_check",
    "parse_ruff_check",
    "parse_ruff_format",
    "parse_ty_check",
]

AGGREGATE_MIN_ISSUES = 25
AGGREGATE_MIN_FILES = 6
MAX_DETAIL_LINES = 50

_TY_SEVERITY: dict[str, DiagnosticLevel] = {"major": "error", "minor": "warning"}

_RUFF_CONCISE = re.compile(
    r"^([^:]+):(\d+):(\d+):\s+(\w+)\s+(\[\*\]\s+)?(.+)$",
    re.MULTILINE,
)
_TY_CONCISE = re.compile(
    r"^([^:]+):(\d+):(\d+):\s*(error|warning|info)\[([^\]]+)\]\s+(.+)$",
    re.MULTILINE,
)


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
        Token metrics for the run.
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


def parse_ruff_check(output: str) -> list[RuffError]:
    """
    Parse ruff JSON output into findings, with a concise-text fallback.

    Args:
        output: Combined stdout and stderr of ``ruff check``.

    Returns:
        Parsed lint findings, or ``[]`` when nothing was found.
    """
    try:
        return [
            RuffError(
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
            RuffError(
                file=match[1],
                line=int(match[2]),
                col=int(match[3]),
                code=match[4],
                fixable=match[5] is not None,
                message=match[6].strip(),
            )
            for match in _RUFF_CONCISE.finditer(output)
        ]


def parse_ty_check(output: str) -> list[TyError]:
    """
    Parse ty GitLab code-quality JSON into diagnostics.

    Falls back to parsing the concise text format for older ty versions.

    Args:
        output: Combined stdout and stderr of ``ty check``.

    Returns:
        Parsed diagnostics, or ``[]`` when nothing was found.
    """
    try:
        return [
            TyError(
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
            TyError(
                file=match[1],
                line=int(match[2]),
                col=int(match[3]),
                level=cast(DiagnosticLevel, match[4]),
                code=match[5],
                message=match[6].strip(),
            )
            for match in _TY_CONCISE.finditer(output)
        ]


def parse_ruff_format(output: str) -> list[str]:
    """
    Extract the files needing reformatting from ``ruff format --check``.

    Args:
        output: Combined stdout and stderr of ``ruff format --check``.

    Returns:
        The unformatted file paths.
    """
    return [
        line.removeprefix("Would reformat: ").strip()
        for line in output.splitlines()
        if line.startswith("Would reformat: ")
    ]


def _ty_description(code: str, description: str) -> str:
    """Remove GitLab's duplicated ``<code>: `` message prefix."""
    return description.removeprefix(f"{code}: ")


def filter_ty_level(errors: list[TyError], level: CheckLevel) -> list[TyError]:
    """
    Filter ty diagnostics by severity.

    Args:
        errors: Parsed diagnostics.
        level: ``error`` keeps errors, ``warning`` keeps warnings and errors,
            ``all`` keeps everything.

    Returns:
        The filtered diagnostics.
    """
    match level:
        case "error":
            return [error for error in errors if error.level == "error"]
        case "warning":
            return [error for error in errors if error.level == "warning"]
        case _:
            return errors


def format_ruff_check(errors: list[RuffError]) -> str:
    """Format ruff findings compactly, aggregated for large result sets."""
    if not errors:
        return "No lint issues found."
    if _use_aggregate(errors):
        return _format_ruff_aggregate(errors)

    return _format_grouped(
        header=_ruff_header(errors),
        errors=errors,
        lines=lambda err: [
            f"  L{err.line}:{err.col} [{err.code}{'*' if err.fixable else ''}] "
            f"{err.message}"
        ],
    )


def format_ty_check(errors: list[TyError]) -> str:
    """Format ty diagnostics compactly, aggregated for large result sets."""
    if not errors:
        return "No type errors found."
    if _use_aggregate(errors):
        return _format_ty_aggregate(errors)

    return _format_grouped(
        header=_ty_header(errors),
        errors=errors,
        lines=lambda err: [
            f"  L{err.line}:{err.col} [{_level_mark(err.level)}:{err.code}] "
            f"{err.message}"
        ],
    )


def format_ruff_format(files: list[str]) -> str:
    """Format the list of unformatted files compactly."""
    if not files:
        return "All files properly formatted."

    lines = [f"ruff format: {len(files)} files need formatting", ""]
    lines.extend(f"  {f}" for f in sorted(files))

    return "\n".join(lines).strip()


def _use_aggregate(errors: Sequence[Any]) -> bool:
    """True when the result set is large enough to warrant rollups."""
    return (
        len(errors) >= AGGREGATE_MIN_ISSUES
        or len({err.file for err in errors}) >= AGGREGATE_MIN_FILES
    )


def _format_grouped(
    header: str,
    errors: Sequence[Any],
    lines: Callable[[Any], list[str]],
) -> str:
    """Format findings grouped by file, the plugin's compact layout."""
    by_file: dict[str, list[Any]] = {}

    for err in sorted(errors, key=lambda error: (error.file, error.line)):
        by_file.setdefault(err.file, []).append(err)

    out = [header, ""]

    for file in sorted(by_file):
        out.append(f"## {file}")

        for err in by_file[file]:
            out.extend(lines(err))
        out.append("")

    return "\n".join(out).strip()


def _ruff_header(errors: list[RuffError]) -> str:
    """Build the compact header line for a ruff result."""
    fixable = sum(1 for error in errors if error.fixable)
    files = len({error.file for error in errors})
    header = f"ruff: {len(errors)} issues in {files} files"

    return f"{header} ({fixable} fixable)" if fixable else header


def _ty_header(errors: list[TyError]) -> str:
    """Build the compact header line for a ty result."""
    error_count = sum(1 for error in errors if error.level == "error")
    warning_count = sum(1 for error in errors if error.level == "warning")
    files = len({error.file for error in errors})
    parts = []

    if error_count:
        parts.append(f"{error_count} errors")

    if warning_count:
        parts.append(f"{warning_count} warnings")

    return f"ty: {', '.join(parts)} in {files} files"


def _level_mark(level: str) -> str:
    """Map a diagnostic level to its one-letter marker."""
    match level:
        case "error":
            return "E"
        case _:
            return "W"


def _format_ruff_aggregate(errors: list[RuffError]) -> str:
    """Large-result layout: rule/file rollups plus flat diagnostic lines."""
    out = [_ruff_header(errors), ""]
    out.append("Top rules:")

    for code, count in _ranked_counts(error.code for error in errors):
        out.append(f"  {code} ({count}x)")

    out.append("")
    out.append("Top files:")
    by_file: dict[str, list[RuffError]] = {}

    for error in errors:
        by_file.setdefault(error.file, []).append(error)

    for file, file_errors in _ranked_groups(by_file):
        out.append(f"  {file} ({len(file_errors)} issues)")

        for code, count in _ranked_counts(err.code for err in file_errors):
            out.append(f"    {code} ({count})")

    out.append("")
    out.append("Violations:")
    details = sorted(errors, key=lambda error: (error.file, error.line, error.col))

    for err in details[:MAX_DETAIL_LINES]:
        fix = "*" if err.fixable else ""
        out.append(f"  {err.file}:{err.line}:{err.col} {err.code}{fix} {err.message}")

    _append_omission(out, len(details), "issues")

    return "\n".join(out).strip()


def _format_ty_aggregate(errors: list[TyError]) -> str:
    """Large-result layout: rule/file rollups plus flat diagnostic lines."""
    out = [_ty_header(errors), ""]
    out.append("Top rules:")

    for code, count in _ranked_counts(error.code for error in errors):
        out.append(f"  {code} ({count}x)")

    out.append("")
    out.append("Top files:")
    by_file: dict[str, list[TyError]] = {}

    for error in errors:
        by_file.setdefault(error.file, []).append(error)

    for file, file_errors in _ranked_groups(by_file):
        out.append(f"  {file} ({len(file_errors)} diagnostics)")

        for code, count in _ranked_counts(err.code for err in file_errors):
            out.append(f"    {code} ({count})")

    out.append("")
    out.append("Diagnostics:")
    details = sorted(errors, key=lambda error: (error.file, error.line, error.col))

    for err in details[:MAX_DETAIL_LINES]:
        out.append(
            f"  {err.file}:{err.line}:{err.col} [{_level_mark(err.level)}:{err.code}] "
            f"{err.message}"
        )

    _append_omission(out, len(details), "diagnostics")

    return "\n".join(out).strip()


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
