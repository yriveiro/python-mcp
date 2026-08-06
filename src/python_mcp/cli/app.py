#!/usr/bin/env python3
import typer

from python_mcp.cli.display import error
from python_mcp.cli.skills import skill_app
from python_mcp.settings import Settings, configure_logging

app = typer.Typer(
    help="MCP server for running ruff and ty with token-efficient output.",
    no_args_is_help=False,
)
app.add_typer(skill_app, name="skill")


def _start_server() -> None:
    """Configure and run the FastMCP server."""
    configure_logging(Settings())

    try:
        from python_mcp.server import mcp

        mcp.run()
    except Exception as exc:
        error(f"Error running server: {exc}")
        raise typer.Exit(code=1) from exc


@app.callback(invoke_without_command=True)
def main(ctx: typer.Context) -> None:
    """Run the MCP server when no subcommand is provided."""
    if ctx.invoked_subcommand is None:
        _start_server()


def run() -> None:
    """Run the Typer application."""
    app()
