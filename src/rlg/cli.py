"""Command-line entry point: `rlg <stage> <command>`.

Stage sub-apps are registered here as each phase lands.
"""

from typing import Annotated

import typer

from rlg import __version__
from rlg.store.db import healthcheck, make_engine

app = typer.Typer(help="Research-Lineage Graph pipeline.", no_args_is_help=True)


@app.callback()
def main() -> None:
    """Research-Lineage Graph pipeline."""


@app.command()
def version() -> None:
    """Print the package version."""
    typer.echo(__version__)


db_app = typer.Typer(help="Database utilities.", no_args_is_help=True)
app.add_typer(db_app, name="db")


@db_app.command("health")
def db_health() -> None:
    """Exit 0 if the database answers, 1 otherwise."""
    ok = healthcheck(make_engine())
    typer.echo("ok" if ok else "unreachable")
    raise typer.Exit(0 if ok else 1)


queue_app = typer.Typer(help="Job queue.", no_args_is_help=True)
app.add_typer(queue_app, name="queue")


@queue_app.command("work")
def queue_work(
    kind: Annotated[list[str] | None, typer.Option(help="Only these job kinds.")] = None,
    max_jobs: Annotated[int | None, typer.Option(help="Stop after this many jobs.")] = None,
    once: Annotated[bool, typer.Option(help="Stop when no job is runnable.")] = False,
) -> None:
    """Run a worker that processes queued jobs."""
    from rlg.queue import run_worker

    n = run_worker(make_engine(), kinds=kind or None, max_jobs=max_jobs, stop_when_empty=once)
    typer.echo(f"handled {n} job(s)")


@queue_app.command("stats")
def queue_stats() -> None:
    """Show job counts by kind and status."""
    from rlg.queue import stats

    for (k, status), n in sorted(stats(make_engine()).items()):
        typer.echo(f"{k}\t{status}\t{n}")


if __name__ == "__main__":
    app()
