import importlib

from typer.testing import CliRunner

from python_mcp.cli import app

cli_app = importlib.import_module("python_mcp.cli.app")

runner = CliRunner()


def test_no_arguments_starts_server(monkeypatch) -> None:
    received: list[bool] = []
    monkeypatch.setattr(cli_app, "_start_server", lambda: received.append(True))

    result = runner.invoke(app, [])

    assert result.exit_code == 0
    assert received == [True]
