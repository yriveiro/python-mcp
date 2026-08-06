from dataclasses import dataclass
from pathlib import Path
from typing import cast

from fastmcp import Context

from python_mcp.runner import ToolRunner


@dataclass(slots=True)
class ServerContext:
    """
    Per-server shared services created by the lifespan.

    Attributes:
        runner: Executes ruff and ty with token-efficient output.
        project_dir: Directory that checks run against.
    """

    runner: ToolRunner
    project_dir: Path


def services(ctx: Context) -> ServerContext:
    """
    Return the typed server services from a FastMCP context.

    Args:
        ctx: FastMCP request context.

    Returns:
        The shared services created by the server lifespan.
    """
    return cast(ServerContext, ctx.lifespan_context)
