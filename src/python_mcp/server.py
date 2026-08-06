import python_mcp.tools  # noqa: F401
from python_mcp.app import app as mcp
from python_mcp.settings import Settings, configure_logging

__all__ = ["mcp"]


if __name__ == "__main__":
    configure_logging(Settings())
    mcp.run()
