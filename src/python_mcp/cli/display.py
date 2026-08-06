from rich.console import Console


def info(message: str) -> None:
    """Write informational output."""
    Console().print(message)


def success(message: str) -> None:
    """Write successful-operation output."""
    Console().print(f"[bold green]OK[/] {message}")


def error(message: str) -> None:
    """Write an error to stderr."""
    Console(stderr=True).print(f"[bold red]ERROR[/] {message}")
