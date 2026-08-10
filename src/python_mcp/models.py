from typing import Literal

from pydantic import BaseModel

type CheckLevel = Literal["all", "error", "warning"]
type DiagnosticLevel = Literal["error", "warning", "info"]


class Finding(BaseModel):
    """
    A single diagnostic reported by a code-quality tool.

    Attributes:
        file: Path of the file the finding belongs to, relative when known.
        message: Human-readable description of the finding.
        line: 1-based line number, ``0`` when the tool reports no location.
        col: 1-based column number, ``0`` when the tool reports no location.
        code: Tool-specific issue code (e.g. ``F401`` or ``B101``).
        level: Severity of the finding.
        fixable: Whether the tool offers an automated fix.
        confidence: Percent confidence for vulture findings.
        severity: Raw severity label for bandit findings (``LOW``, ``MEDIUM``,
            or ``HIGH``).
        suggestion: Proposed correction for codespell findings.
    """

    file: str
    message: str
    line: int = 0
    col: int = 0
    code: str | None = None
    level: DiagnosticLevel = "error"
    fixable: bool = False
    confidence: int | None = None
    severity: str | None = None
    suggestion: str | None = None


class TokenMetrics(BaseModel):
    """Estimated token savings of the compact output versus raw output."""

    raw_tokens: int
    processed_tokens: int
    saved_tokens: int
    savings_percent: int


class CheckResult(BaseModel):
    """
    Result of a code-quality check run.

    Attributes:
        output: Token-efficient output for the model.
        exit_code: Exit code of the underlying command.
        issues: Number of findings (lint issues, unformatted files, collection
            errors, or diagnostics, depending on the tool).
        fixable: Number of findings with an available fix.
        warnings: Number of warning-level findings.
        saved_tokens: Estimated tokens removed from the raw output.
        savings_percent: Share of raw tokens removed, rounded.
    """

    output: str
    exit_code: int
    issues: int = 0
    fixable: int = 0
    warnings: int = 0
    saved_tokens: int = 0
    savings_percent: int = 0

    @property
    def clean(self) -> bool:
        """True when the underlying command reported no findings."""
        return self.exit_code == 0
