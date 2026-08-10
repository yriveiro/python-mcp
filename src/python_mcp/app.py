from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from fastmcp import FastMCP

from python_mcp import __version__
from python_mcp.context import ServerContext
from python_mcp.runner import ToolRunner
from python_mcp.settings import Settings, configure_logging


@asynccontextmanager
async def lifespan(_server: FastMCP) -> AsyncIterator[ServerContext]:
    """
    Build the shared services for the lifetime of the server.

    Args:
        _server: The FastMCP server instance, unused.

    Yields:
        ServerContext: The shared services for the server lifetime.
    """
    settings = Settings()
    configure_logging(settings)
    yield ServerContext(
        runner=ToolRunner(
            command_prefix=settings.command_prefix,
            command_timeout=settings.command_timeout,
        ),
        project_dir=(
            Path(settings.project_dir).resolve() if settings.project_dir else Path.cwd()
        ),
    )


app = FastMCP(
    "python-mcp",
    instructions=(
        "Run Python code-quality checks with token-efficient output. Use ruff_check "
        "to lint, ruff_format to verify formatting, ty_check to type check, "
        "vulture_check for dead-code analysis, bandit_check for security, "
        "deptry_check for dependencies, pytest_collect for test collection, and "
        "codespell_check for spelling. "
        "Prefer changed_only=true for fast feedback "
        "on recently edited files, and pass paths with glob patterns to "
        "narrow the scope."
    ),
    version=__version__,
    lifespan=lifespan,
)
