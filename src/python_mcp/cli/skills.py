import shutil
from pathlib import Path
from typing import Annotated

import typer

from python_mcp.cli.display import error, info, success

SKILLS_DIR = Path(__file__).parent.parent / "skills"
AGENTS_DIR = Path(".agents")
SKILLS_SUBDIR = "skills"

skill_app = typer.Typer(
    help="Manage Agent Skills bundled with python-mcp.",
    no_args_is_help=True,
)


def bundled_skill_names() -> list[str]:
    """Return the names of skills bundled with this package."""
    return sorted(
        name
        for name in (entry.name for entry in SKILLS_DIR.iterdir())
        if (SKILLS_DIR / name / "SKILL.md").is_file()
    )


def install_skill(
    name: str, project_dir: Path, force: bool = False
) -> tuple[Path, list[str]]:
    """
    Install a bundled skill into an agent-compatible project layout.

    Args:
        name: Skill name.
        project_dir: Target project directory.
        force: Overwrite an existing installation.

    Returns:
        tuple[Path, list[str]]: The destination directory and the list of
        installed files.

    Raises:
        ValueError: If the skill is unknown or already installed.
    """
    source = SKILLS_DIR / name
    if not (source / "SKILL.md").is_file():
        available = ", ".join(bundled_skill_names())
        raise ValueError(f"Unknown skill {name!r}. Bundled skills: {available}")

    destination = project_dir / AGENTS_DIR / SKILLS_SUBDIR / name
    if destination.exists():
        if not force:
            raise ValueError(
                f"Skill {name!r} is already installed at {destination}. "
                "Use --force to overwrite it."
            )
        shutil.rmtree(destination)
    shutil.copytree(source, destination)

    files = sorted(
        str(path.relative_to(destination))
        for path in destination.rglob("*")
        if path.is_file()
    )
    return destination, files


@skill_app.command("install")
def install(
    name: Annotated[str, typer.Argument(help="Skill name to install")],
    target: Annotated[
        Path,
        typer.Option(
            help="Project directory to install into",
            show_default=True,
        ),
    ] = Path("."),
    force: Annotated[
        bool,
        typer.Option("--force", "-f", help="Overwrite an existing installation"),
    ] = False,
) -> None:
    """Install a bundled skill into an agent-compatible project."""
    try:
        destination, files = install_skill(name, target, force=force)
    except ValueError as exc:
        error(str(exc))
        raise typer.Exit(code=1) from exc
    success(f"Installed skill {name!r} to {destination}")
    for file in files:
        info(f"  {file}")
    info(f"Hint: agents discover skills at {destination / 'SKILL.md'}")
