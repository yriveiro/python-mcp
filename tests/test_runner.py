import json
import subprocess
from pathlib import Path

from python_mcp.formatting import (
    calculate_metrics,
    filter_ty_level,
    format_findings,
    parse_bandit,
    parse_codespell,
    parse_deptry,
    parse_pydoclint,
    parse_pytest_collect,
    parse_ruff,
    parse_ty,
    parse_vulture,
)
from python_mcp.models import Finding
from python_mcp.runner import ToolRunner, changed_python_files, resolve_paths
from python_mcp.tooling import TOOLS


def test_parse_ruff_json_preserves_colons_and_fixability() -> None:
    payload = json.dumps(
        [
            {
                "filename": "/tmp/project/a:b.py",
                "code": "F401",
                "message": "message: with [brackets]",
                "location": {"row": 2, "column": 8},
                "fix": {"applicability": "safe"},
            }
        ]
    )

    assert parse_ruff(payload) == [
        Finding(
            file="/tmp/project/a:b.py",
            line=2,
            col=8,
            code="F401",
            message="message: with [brackets]",
            fixable=True,
        )
    ]


def test_parse_ruff_concise_fallback() -> None:
    errors = parse_ruff("a.py:2:8: F401 [*] unused import")

    assert errors[0].code == "F401"
    assert errors[0].fixable


def test_parse_ty_gitlab_json_maps_severity() -> None:
    payload = json.dumps(
        [
            {
                "check_name": "invalid-assignment",
                "description": "invalid-assignment: bad: value",
                "severity": "major",
                "location": {
                    "path": "a.py",
                    "positions": {"begin": {"line": 1, "column": 10}},
                },
            },
            {
                "check_name": "unknown-rule",
                "description": "warning",
                "severity": "minor",
                "location": {
                    "path": "b.py",
                    "positions": {"begin": {"line": 2, "column": 1}},
                },
            },
        ]
    )

    errors = parse_ty(payload)

    assert [error.level for error in errors] == ["error", "warning"]
    assert errors[0].message == "bad: value"


def test_parse_ty_concise_fallback() -> None:
    errors = parse_ty("a.py:1:2: warning[code] message: with colon")

    assert errors[0].level == "warning"
    assert errors[0].message == "message: with colon"


def test_parse_vulture_output() -> None:
    errors = parse_vulture("src/a.py:12: unused function 'helper' (60% confidence)")

    assert errors == [
        Finding(
            file="src/a.py",
            line=12,
            message="unused function 'helper'",
            confidence=60,
        )
    ]


def test_parse_bandit_json() -> None:
    payload = json.dumps(
        {
            "results": [
                {
                    "filename": "a.py",
                    "line_number": 4,
                    "col_offset": 2,
                    "test_id": "B101",
                    "issue_text": "Use of assert detected",
                    "issue_severity": "LOW",
                }
            ]
        }
    )

    assert parse_bandit(payload) == [
        Finding(
            file="a.py",
            line=4,
            col=3,
            code="B101",
            message="Use of assert detected",
            level="info",
            severity="LOW",
        )
    ]


def test_parse_deptry_output() -> None:
    errors = parse_deptry(
        "src/a.py:3:8: DEP001 'requests' imported but missing from dependencies"
    )

    assert errors == [
        Finding(
            file="src/a.py",
            line=3,
            col=8,
            code="DEP001",
            message="'requests' imported but missing from dependencies",
        )
    ]


def test_parse_codespell_output() -> None:
    typo = "t" + "eh"
    correction = "t" + "he"
    errors = parse_codespell(f"README.md:4: {typo} ==> {correction}")

    assert errors == [
        Finding(file="README.md", line=4, message=typo, suggestion=correction)
    ]


def test_parse_pytest_collection() -> None:
    collection = parse_pytest_collect(
        "tests/test_a.py::test_one\n\n1 test collected in 0.01s"
    )

    assert collection.tests == ["tests/test_a.py::test_one"]
    assert collection.errors == []


def test_parse_pytest_collection_error() -> None:
    collection = parse_pytest_collect("ERROR test_b.py\n\n1 error in 0.01s")

    assert collection.errors == [
        Finding(file="test_b.py", message="pytest collection error")
    ]


def test_parse_pydoclint_output() -> None:
    findings = parse_pydoclint(
        "src/a.py\nsrc/a.py\n"
        "    4: DOC201: Function `x` does not have a return section\n"
        "    9: DOC105: Argument names match, but types do not match: x\n"
    )

    assert findings == [
        Finding(
            file="src/a.py",
            line=4,
            code="DOC201",
            message="Function `x` does not have a return section",
        ),
        Finding(
            file="src/a.py",
            line=9,
            code="DOC105",
            message="Argument names match, but types do not match: x",
        ),
    ]


def test_format_findings_uses_grouped_layout() -> None:
    output = format_findings(
        [Finding(file="a.py", line=1, col=1, code="F401", message="unused")],
        name="ruff",
        empty_message="No lint issues found.",
        render_line=lambda finding: (
            f"  L{finding.line}:{finding.col} [{finding.code}] {finding.message}"
        ),
    )

    assert "## a.py" in output
    assert "L1:1 [F401] unused" in output


def test_large_result_uses_aggregate_layout() -> None:
    errors = [
        Finding(
            file=f"file_{index % 6}.py",
            line=index + 1,
            col=1,
            code="F401" if index % 2 else "F841",
            message="issue",
        )
        for index in range(30)
    ]

    output = format_findings(
        errors,
        name="ruff",
        empty_message="No lint issues found.",
        render_line=lambda finding: f"  {finding.file}:{finding.line}",
    )

    assert "Top rules:" in output
    assert "Top files:" in output
    assert "file_0.py:1" in output


def test_filter_ty_level() -> None:
    errors = [
        Finding(file="a.py", line=1, col=1, level="error", code="E", message="e"),
        Finding(file="a.py", line=2, col=1, level="warning", code="W", message="w"),
        Finding(file="a.py", line=3, col=1, level="info", code="I", message="i"),
    ]

    assert len(filter_ty_level(errors, "error")) == 1
    assert len(filter_ty_level(errors, "warning")) == 1
    assert len(filter_ty_level(errors, "all")) == 3


def test_metrics_report_processed_savings() -> None:
    metrics = calculate_metrics("a " * 100, "a")

    assert metrics.saved_tokens > 0
    assert metrics.savings_percent > 0


def test_native_runner_uses_structured_outputs(tmp_path: Path) -> None:
    (tmp_path / "bad.py").write_text("import sys\n")
    result = ToolRunner(command_prefix="").run(
        TOOLS["ruff_check"], ["bad.py"], tmp_path
    )

    assert result.exit_code == 1
    assert "F401" in result.output
    assert result.metrics is not None


def test_resolve_paths_expands_globs(tmp_path: Path) -> None:
    (tmp_path / "a.py").write_text("a = 1\n")
    (tmp_path / "b.py").write_text("b = 2\n")
    (tmp_path / "c.txt").write_text("c\n")

    assert sorted(resolve_paths(["*.py"], tmp_path)) == ["a.py", "b.py"]


def test_resolve_paths_passes_plain_through() -> None:
    assert resolve_paths(["src", "tests/test_x.py"], Path(".")) == [
        "src",
        "tests/test_x.py",
    ]


def test_changed_python_files_in_git_repo(tmp_path: Path) -> None:
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    subprocess.run(["git", "config", "user.email", "t@t.dev"], cwd=tmp_path, check=True)
    subprocess.run(["git", "config", "user.name", "T"], cwd=tmp_path, check=True)
    (tmp_path / "tracked.py").write_text("a = 1\n")
    subprocess.run(["git", "add", "tracked.py"], cwd=tmp_path, check=True)
    subprocess.run(["git", "commit", "-qm", "init"], cwd=tmp_path, check=True)
    (tmp_path / "tracked.py").write_text("a = 2\n")
    (tmp_path / "new.py").write_text("b = 1\n")

    assert sorted(changed_python_files(tmp_path)) == ["new.py", "tracked.py"]


def test_changed_python_files_outside_repo(tmp_path: Path) -> None:
    assert changed_python_files(tmp_path) == []
