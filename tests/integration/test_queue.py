"""P0-06: Postgres job queue."""

import threading
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from sqlalchemy import Engine, select

from rlg.queue import backoff, claim, complete, enqueue, fail, run_worker, stats
from rlg.store.tables import job

pytestmark = pytest.mark.integration

T0 = datetime(2026, 10, 17, 12, tzinfo=UTC)


def job_row(engine: Engine, job_id: int) -> Any:
    with engine.connect() as conn:
        return conn.execute(select(job).where(job.c.id == job_id)).one()


def test_two_concurrent_workers_never_claim_same_job(db_engine: Engine) -> None:
    n = 200
    ids = {enqueue(db_engine, "noop", {"i": i}) for i in range(n)}
    claimed: dict[str, list[int]] = {"a": [], "b": [], "c": [], "d": []}
    barrier = threading.Barrier(len(claimed))

    def work(name: str) -> None:
        barrier.wait()
        while (j := claim(db_engine, name)) is not None:
            claimed[name].append(j.id)
            complete(db_engine, j)

    threads = [threading.Thread(target=work, args=(name,)) for name in claimed]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    all_claims = [i for lst in claimed.values() for i in lst]
    assert len(all_claims) == n == len(set(all_claims))
    assert set(all_claims) == ids
    assert sum(1 for lst in claimed.values() if lst) >= 2  # work actually got shared
    assert stats(db_engine) == {("noop", "done"): n}


def test_killed_worker_job_reclaimed_after_lock_timeout(db_engine: Engine) -> None:
    jid = enqueue(db_engine, "noop", {}, now=T0)
    lost = claim(db_engine, "dead-worker", now=T0)
    assert lost is not None and lost.id == jid
    # worker dies without complete/fail; lock still fresh -> nobody else gets it
    timeout = timedelta(minutes=5)
    assert claim(db_engine, "w2", lock_timeout=timeout, now=T0 + timedelta(minutes=4)) is None
    again = claim(db_engine, "w2", lock_timeout=timeout, now=T0 + timedelta(minutes=6))
    assert again is not None and again.id == jid and again.attempts == 2
    assert not complete(db_engine, lost)  # the dead worker's late completion is ignored
    assert complete(db_engine, again)
    assert job_row(db_engine, jid).status == "done"


def test_failed_job_retried_until_max_attempts_then_failed(db_engine: Engine) -> None:
    jid = enqueue(db_engine, "boom", {}, max_attempts=3, now=T0)
    t = T0
    statuses = []
    for _ in range(3):
        j = claim(db_engine, "w", now=t)
        assert j is not None and j.id == jid
        statuses.append(fail(db_engine, j, "ValueError: nope", now=t))
        row = job_row(db_engine, jid)
        if row.status == "queued":
            assert row.run_after == t + backoff(j.attempts)
            assert claim(db_engine, "w", now=t) is None  # not runnable before backoff
            t = row.run_after
    assert statuses == ["queued", "queued", "failed"]
    row = job_row(db_engine, jid)
    assert row.status == "failed" and row.attempts == 3 and "nope" in row.last_error
    assert claim(db_engine, "w", now=t + timedelta(days=1)) is None


def test_stale_lock_on_last_attempt_is_failed_not_rerun(db_engine: Engine) -> None:
    jid = enqueue(db_engine, "noop", {}, max_attempts=1, now=T0)
    assert claim(db_engine, "dead", now=T0) is not None
    assert (
        claim(db_engine, "w", lock_timeout=timedelta(minutes=1), now=T0 + timedelta(hours=1))
        is None
    )
    assert job_row(db_engine, jid).status == "failed"


def test_worker_runs_handlers_with_retries(db_engine: Engine) -> None:
    calls: list[int] = []

    def flaky(payload: dict[str, Any]) -> None:
        calls.append(payload["n"])
        if len(calls) == 1:
            raise RuntimeError("transient")

    enqueue(db_engine, "flaky", {"n": 1})
    handled = run_worker(
        db_engine,
        handlers={"flaky": flaky},
        stop_when_empty=True,
        backoff_base=timedelta(0),
    )
    assert handled == 2 and calls == [1, 1]
    assert stats(db_engine) == {("flaky", "done"): 1}


def test_dedup_key_makes_enqueue_idempotent(db_engine: Engine) -> None:
    assert enqueue(db_engine, "noop", {}, dedup_key="paper:2210.03629") is not None
    assert enqueue(db_engine, "noop", {}, dedup_key="paper:2210.03629") is None
    assert stats(db_engine) == {("noop", "queued"): 1}
