import logging
import sys

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Server settings configurable via ``PYTHON_MCP_*`` environment variables."""

    model_config = SettingsConfigDict(env_prefix="PYTHON_MCP_")

    log_level: str = "INFO"
    project_dir: str | None = None
    command_prefix: str = "uv run"
    command_timeout: float | None = None


def configure_logging(settings: Settings) -> None:
    """Configure stdio-safe logging on stderr for the given settings."""
    logging.basicConfig(
        level=settings.log_level.upper(),
        format="%(levelname)s:%(name)s:%(message)s",
        stream=sys.stderr,
    )
