class ToolError(Exception):
    """Base exception for all tool execution errors."""


class ToolNotFoundError(ToolError):
    """Raised when a required executable cannot be located or executed."""
