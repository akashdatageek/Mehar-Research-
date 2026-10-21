"""Command-line entry point: `rlg <stage> <command>`. Stages register sub-apps here."""

import typer

from rlg import __version__
from rlg.store.db import healthcheck, make_engine

app = typer.Typer(help="Research-Lineage Graph pipeline.", no_args_is_help=True)
db_app = typer.Typer(help="Database commands.", no_args_is_help=True)
app.add_typer(db_app, name="db")


@app.callback()
def main() -> None:
    """Research-Lineage Graph pipeline."""


@app.command()
def version() -> None:
    """Print the package version."""
    typer.echo(__version__)


@db_app.command("health")
def db_health() -> None:
    """Exit 0 if the database answers, 1 otherwise."""
    ok = healthcheck(make_engine())
    typer.echo("ok" if ok else "unreachable")
    raise typer.Exit(0 if ok else 1)


if __name__ == "__main__":
    app()
