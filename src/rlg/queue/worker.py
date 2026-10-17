"""Worker loop: claim a job, run its handler, complete or fail it."""

import logging
import os
import socket
import time
from collections.abc import Callable
from datetime import timedelta
from typing import Any

from sqlalchemy import Engine

from rlg.queue.jobs import DEFAULT_BACKOFF_BASE, DEFAULT_LOCK_TIMEOUT, claim, complete, fail

log = logging.getLogger(__name__)

Handler = Callable[[dict[str, Any]], None]
HANDLERS: dict[str, Handler] = {}


def handler(kind: str) -> Callable[[Handler], Handler]:
    """Decorator registering a job handler for `kind`. Handlers must be idempotent."""

    def register(fn: Handler) -> Handler:
        HANDLERS[kind] = fn
        return fn

    return register


@handler("noop")
def _noop(payload: dict[str, Any]) -> None:
    """Smoke-test job kind."""


def default_worker_id() -> str:
    return f"{socket.gethostname()}:{os.getpid()}"


def run_worker(
    engine: Engine,
    *,
    handlers: dict[str, Handler] | None = None,
    worker_id: str | None = None,
    kinds: list[str] | None = None,
    max_jobs: int | None = None,
    poll_seconds: float = 2.0,
    stop_when_empty: bool = False,
    lock_timeout: timedelta = DEFAULT_LOCK_TIMEOUT,
    backoff_base: timedelta = DEFAULT_BACKOFF_BASE,
) -> int:
    """Process jobs until `max_jobs` are handled or (with stop_when_empty) none are runnable.

    Returns the number of jobs handled (done or failed).
    """
    handlers = HANDLERS if handlers is None else handlers
    worker_id = worker_id or default_worker_id()
    kinds = kinds or sorted(handlers)
    handled = 0
    while max_jobs is None or handled < max_jobs:
        j = claim(engine, worker_id, kinds=kinds, lock_timeout=lock_timeout)
        if j is None:
            if stop_when_empty:
                break
            time.sleep(poll_seconds)
            continue
        try:
            handlers[j.kind](j.payload)
        except Exception as e:
            status = fail(engine, j, f"{type(e).__name__}: {e}", backoff_base=backoff_base)
            log.warning(
                "job %s (%s) attempt %s failed -> %s: %s", j.id, j.kind, j.attempts, status, e
            )
        else:
            complete(engine, j)
        handled += 1
    return handled
