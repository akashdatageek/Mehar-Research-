"""Command-line entry point: `rlg <stage> <command>`.

Stage sub-apps are registered here as each phase lands.
"""

import typer

from rlg import __version__

app = typer.Typer(help="Research-Lineage Graph pipeline.", no_args_is_help=True)


@app.callback()
def main() -> None:
    """Research-Lineage Graph pipeline."""


@app.command()
def version() -> None:
    """Print the package version."""
    typer.echo(__version__)


if __name__ == "__main__":
    app()
