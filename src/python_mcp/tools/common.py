from mcp.types import ToolAnnotations

from python_mcp.context import services

__all__ = ["READ_ONLY", "services"]

READ_ONLY = ToolAnnotations(
    readOnlyHint=True,
    idempotentHint=True,
    openWorldHint=False,
)
