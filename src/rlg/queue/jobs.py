"""Postgres job queue: enqueue, claim with FOR UPDATE SKIP LOCKED, retry with backoff.

Job lifecycle: queued -> running -> done | (queued again with backoff) | failed.
A `running` job whose lock is older than `lock_timeout` is assumed to belong to a dead
worker and can be claimed again (or failed, if it has used all its attempts).
"""

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import Engine, and_, func, or_, select, update
from sqlalchemy.dialects.postgresql import insert

from rlg.store.tables import job

DEFAULT_LOCK_TIMEOUT = timedelta(minutes=30)
DEFAULT_BACKOFF_BASE = timedelta(seconds=30)
MAX_BACKOFF = timedelta(hours=6)


@dataclass(frozen=True)
class Job:
    id: int
    kind: str
    payload: dict[str, Any]
    attempts: int
    max_attempts: int
    locked_by: str | None


def _now(now: datetime | None) -> datetime:
    return now if now is not None else datetime.now(UTC)


def enqueue(
    engine: Engine,
    kind: str,
    payload: dict[str, Any],
    *,
    dedup_key: str | None = None,
    run_after: datetime | None = None,
    max_attempts: int = 5,
    now: datetime | None = None,
) -> int | None:
    """Add a job. With `dedup_key`, enqueueing the same key twice is a no-op (returns None)."""
    t = _now(now)
    stmt = (
        insert(job)
        .values(
            kind=kind,
            payload_json=payload,
            dedup_key=dedup_key,
            status="queued",
            attempts=0,
            max_attempts=max_attempts,
            run_after=run_after or t,
            created_at=t,
        )
        .on_conflict_do_nothing(index_elements=["dedup_key"])
        .returning(job.c.id)
    )
    with engine.begin() as conn:
        return conn.execute(stmt).scalar_one_or_none()


def claim(
    engine: Engine,
    worker_id: str,
    *,
    kinds: list[str] | None = None,
    lock_timeout: timedelta = DEFAULT_LOCK_TIMEOUT,
    now: datetime | None = None,
) -> Job | None:
    """Atomically take the next runnable job (or one with an expired lock), or None."""
    t = _now(now)
    stale = and_(job.c.status == "running", job.c.locked_at < t - lock_timeout)
    with engine.begin() as conn:
        # Stale locks that already used every attempt: fail them instead of running again.
        conn.execute(
            update(job)
            .where(stale, job.c.attempts >= job.c.max_attempts)
            .values(
                status="failed",
                finished_at=t,
                last_error=func.coalesce(job.c.last_error, "lock expired on last attempt"),
                locked_at=None,
                locked_by=None,
            )
        )
        candidate = (
            select(job.c.id)
            .where(or_(and_(job.c.status == "queued", job.c.run_after <= t), stale))
            .order_by(job.c.run_after, job.c.id)
            .limit(1)
            .with_for_update(skip_locked=True)
        )
        if kinds:
            candidate = candidate.where(job.c.kind.in_(kinds))
        row = conn.execute(
            update(job)
            .where(job.c.id == candidate.scalar_subquery())
            .values(status="running", attempts=job.c.attempts + 1, locked_at=t, locked_by=worker_id)
            .returning(job)
        ).one_or_none()
    if row is None:
        return None
    return Job(
        id=row.id,
        kind=row.kind,
        payload=row.payload_json,
        attempts=row.attempts,
        max_attempts=row.max_attempts,
        locked_by=row.locked_by,
    )


def complete(engine: Engine, j: Job, *, now: datetime | None = None) -> bool:
    """Mark done. False if this worker no longer holds the lock (job was reclaimed)."""
    with engine.begin() as conn:
        res = conn.execute(
            update(job)
            .where(job.c.id == j.id, job.c.status == "running", job.c.locked_by == j.locked_by)
            .values(status="done", finished_at=_now(now), locked_at=None)
        )
    return res.rowcount == 1


def backoff(attempts: int, base: timedelta = DEFAULT_BACKOFF_BASE) -> timedelta:
    """Exponential backoff after the `attempts`-th failure: base * 2^(attempts-1), capped."""
    delay: timedelta = base * (2 ** max(attempts - 1, 0))
    return min(delay, MAX_BACKOFF)


def fail(
    engine: Engine,
    j: Job,
    error: str,
    *,
    backoff_base: timedelta = DEFAULT_BACKOFF_BASE,
    now: datetime | None = None,
) -> str:
    """Record a failure: requeue with backoff, or mark failed after max_attempts. Returns status."""
    t = _now(now)
    final = j.attempts >= j.max_attempts
    values: dict[str, Any] = {"last_error": error[:4000], "locked_at": None, "locked_by": None}
    if final:
        values |= {"status": "failed", "finished_at": t}
    else:
        values |= {"status": "queued", "run_after": t + backoff(j.attempts, backoff_base)}
    with engine.begin() as conn:
        conn.execute(
            update(job)
            .where(job.c.id == j.id, job.c.status == "running", job.c.locked_by == j.locked_by)
            .values(**values)
        )
    return str(values["status"])


def stats(engine: Engine) -> dict[tuple[str, str], int]:
    """Job counts by (kind, status)."""
    with engine.connect() as conn:
        rows = conn.execute(
            select(job.c.kind, job.c.status, func.count()).group_by(job.c.kind, job.c.status)
        ).all()
    return {(r[0], r[1]): int(r[2]) for r in rows}
