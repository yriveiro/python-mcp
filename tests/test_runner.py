import json
import subprocess
from pathlib import Path

from python_mcp.formatting import (
    calculate_metrics,
    filter_ty_level,
    format_ruff_check,
    format_ty_check,
    parse_ruff_check,
    parse_ty_check,
)
from python_mcp.models import RuffError, TyError
from python_mcp.runner import ToolRunner, changed_python_files, resolve_paths


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

    errors = parse_ruff_check(payload)

    assert errors == [
        RuffError(
            file="/tmp/project/a:b.py",
            line=2,
            col=8,
            code="F401",
            message="message: with [brackets]",
            fixable=True,
        )
    ]


def test_parse_ruff_concise_fallback() -> None:
    errors = parse_ruff_check("a.py:2:8: F401 [*] unused import")

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

    errors = parse_ty_check(payload)

    assert [error.level for error in errors] == ["error", "warning"]
    assert errors[0].message == "bad: value"


def test_parse_ty_concise_fallback() -> None:
    errors = parse_ty_check("a.py:1:2: warning[code] message: with colon")

    assert errors[0].level == "warning"
    assert errors[0].message == "message: with colon"


def test_filter_ty_level() -> None:
    errors = [
        TyError(file="a.py", line=1, col=1, level="error", code="E", message="e"),
        TyError(file="a.py", line=2, col=1, level="warning", code="W", message="w"),
        TyError(file="a.py", line=3, col=1, level="info", code="I", message="i"),
    ]

    assert len(filter_ty_level(errors, "error")) == 1
    assert len(filter_ty_level(errors, "warning")) == 1
    assert len(filter_ty_level(errors, "all")) == 3


def test_small_ruff_result_uses_plugin_layout() -> None:
    errors = [RuffError(file="a.py", line=1, col=1, code="F401", message="unused")]

    output = format_ruff_check(errors)

    assert "## a.py" in output
    assert "L1:1 [F401] unused" in output
    assert "Top rules:" not in output


def test_large_ruff_result_uses_aggregate_layout() -> None:
    errors = [
        RuffError(
            file=f"file_{index % 6}.py",
            line=index + 1,
            col=1,
            code="F401" if index % 2 else "F841",
            message="issue",
        )
        for index in range(30)
    ]

    output = format_ruff_check(errors)

    assert "Top rules:" in output
    assert "Top files:" in output
    assert "file_0.py:1:1" in output


def test_large_ty_result_uses_aggregate_layout() -> None:
    errors = [
        TyError(
            file=f"file_{index % 6}.py",
            line=index + 1,
            col=1,
            level="error",
            code="invalid-assignment",
            message="issue",
        )
        for index in range(30)
    ]

    output = format_ty_check(errors)

    assert "Top rules:" in output
    assert "Top files:" in output


def test_metrics_report_processed_savings() -> None:
    metrics = calculate_metrics("a " * 100, "a")

    assert metrics.saved_tokens > 0
    assert metrics.savings_percent > 0


def test_native_runner_uses_structured_outputs(tmp_path: Path) -> None:
    (tmp_path / "bad.py").write_text("import sys\n")
    result = ToolRunner(command_prefix="").ruff_check(["bad.py"], tmp_path)

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
