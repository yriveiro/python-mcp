from pathlib import Path

import pytest
from typer.testing import CliRunner

from python_mcp.cli import app
from python_mcp.cli.skills import bundled_skill_names, install_skill

runner = CliRunner()


def test_bundled_skill_names_include_python_mcp() -> None:
    assert "python-mcp" in bundled_skill_names()


def test_install_skill_copies_to_agents_layout(tmp_path: Path) -> None:
    destination, files = install_skill("python-mcp", tmp_path)

    assert destination == tmp_path / ".agents" / "skills" / "python-mcp"
    assert (destination / "SKILL.md").is_file()
    contents = (destination / "SKILL.md").read_text()
    assert "name: python-mcp" in contents
    assert "`ruff_check`" in contents
    assert "`ruff_format`" in contents
    assert "`ty_check`" in contents
    assert "Their output is structured and intentionally compact." in contents
    assert "uv-mcp" not in contents
    assert files == sorted(
        str(path.relative_to(destination))
        for path in destination.rglob("*")
        if path.is_file()
    )


def test_install_skill_requires_force_for_existing(tmp_path: Path) -> None:
    install_skill("python-mcp", tmp_path)

    with pytest.raises(ValueError, match="already installed"):
        install_skill("python-mcp", tmp_path)

    install_skill("python-mcp", tmp_path, force=True)


def test_install_unknown_skill_raises(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="Unknown skill"):
        install_skill("nonexistent", tmp_path)


def test_skill_install_via_cli(tmp_path: Path) -> None:
    result = runner.invoke(
        app,
        ["skill", "install", "python-mcp", "--target", str(tmp_path)],
    )

    assert result.exit_code == 0
    assert (tmp_path / ".agents" / "skills" / "python-mcp" / "SKILL.md").is_file()


def test_skill_install_unknown_returns_error(tmp_path: Path) -> None:
    result = runner.invoke(
        app,
        ["skill", "install", "nonexistent", "--target", str(tmp_path)],
    )

    assert result.exit_code == 1
