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
    import rlg.ingest.jobs  # noqa: F401  (registers ingestion handlers)
    from rlg.queue import run_worker

    n = run_worker(make_engine(), kinds=kind or None, max_jobs=max_jobs, stop_when_empty=once)
    typer.echo(f"handled {n} job(s)")


@queue_app.command("stats")
def queue_stats() -> None:
    """Show job counts by kind and status."""
    from rlg.queue import stats

    for (k, status), n in sorted(stats(make_engine()).items()):
        typer.echo(f"{k}\t{status}\t{n}")


fixtures_app = typer.Typer(help="Test fixture papers.", no_args_is_help=True)
app.add_typer(fixtures_app, name="fixtures")


@fixtures_app.command("download")
def fixtures_download() -> None:
    """Download fixture papers from arXiv (polite: >=3 s between requests)."""
    from rlg.config import EnvSettings
    from rlg.ingest.fixtures import download_fixtures, urllib_get

    manifest = download_fixtures(urllib_get, EnvSettings().arxiv_contact_email or "")
    typer.echo(f"{len(manifest['papers'])} papers in manifest")


@fixtures_app.command("verify")
def fixtures_verify() -> None:
    """Check downloaded fixtures against manifest.json sha256 values."""
    from rlg.ingest.fixtures import verify_fixtures

    problems = verify_fixtures()
    for p in problems:
        typer.echo(p)
    raise typer.Exit(1 if problems else 0)


ingest_app = typer.Typer(help="Ingestion from external sources.", no_args_is_help=True)
app.add_typer(ingest_app, name="ingest")


@ingest_app.command("harvest")
def ingest_harvest(
    from_date: Annotated[str, typer.Option("--from", help="First day, YYYY-MM-DD.")],
    until_date: Annotated[str, typer.Option("--until", help="Last day, YYYY-MM-DD.")],
    set_spec: Annotated[
        list[str] | None, typer.Option("--set", help="OAI set (default: cs, stat:stat:ML).")
    ] = None,
    enqueue_jobs: Annotated[
        bool, typer.Option("--enqueue", help="Enqueue one job per day instead of running now.")
    ] = False,
) -> None:
    """Harvest arXiv OAI-PMH records for a date range into the registry."""
    from datetime import date, timedelta

    from rlg.ingest.arxiv_oai import DEFAULT_SETS, default_http, harvest
    from rlg.queue import enqueue

    start, end = date.fromisoformat(from_date), date.fromisoformat(until_date)
    sets = set_spec or list(DEFAULT_SETS)
    engine = make_engine()
    if enqueue_jobs:
        n, day = 0, start
        while day <= end:
            key = f"arxiv.harvest_day:{day.isoformat()}:{','.join(sets)}"
            payload = {"day": day.isoformat(), "sets": sets}
            n += enqueue(engine, "arxiv.harvest_day", payload, dedup_key=key) is not None
            day += timedelta(days=1)
        typer.echo(f"enqueued {n} day job(s)")
        return
    s = harvest(engine, default_http(), start, end, sets)
    typer.echo(
        f"records={s.records} papers_inserted={s.papers_inserted} "
        f"papers_updated={s.papers_updated} versions_inserted={s.versions_inserted}"
    )


if __name__ == "__main__":
    app()
