import shutil

import pytest

from python_mcp.models import CheckResult
from python_mcp.runner import ToolRunner
from python_mcp.tooling import TOOLS

pytestmark = pytest.mark.skipif(
    any(shutil.which(tool) is None for tool in ("ruff", "vulture", "bandit")),
    reason="required integration tools are not installed",
)


def test_runner_runs_ruff_check_end_to_end(tmp_path) -> None:
    (tmp_path / "sample.py").write_text(
        "import sys\n\n\ndef f() -> int:\n    return 1\n"
    )
    runner = ToolRunner(command_prefix="")

    result = runner.run(TOOLS["ruff_check"], ["sample.py"], tmp_path)

    assert result.exit_code == 1
    assert "F401" in result.output


def test_runner_runs_vulture_check_end_to_end(tmp_path) -> None:
    (tmp_path / "sample.py").write_text("def unused_function() -> None:\n    pass\n")
    runner = ToolRunner(command_prefix="")

    result = runner.run(TOOLS["vulture_check"], ["sample.py"], tmp_path)

    assert result.exit_code != 0
    assert "unused function" in result.output


def test_runner_runs_bandit_check_end_to_end(tmp_path) -> None:
    (tmp_path / "sample.py").write_text("password = 'secret'\n")
    runner = ToolRunner(command_prefix="")

    result = runner.run(TOOLS["bandit_check"], ["sample.py"], tmp_path)

    assert result.exit_code != 0
    assert "B105" in result.output


def test_check_result_clean_property() -> None:
    assert CheckResult(output="clean", exit_code=0).clean
    assert not CheckResult(output="issues", exit_code=1).clean
