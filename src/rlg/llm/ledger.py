"""Content-hash cache and cost ledger for LLM calls (tables llm_cache, llm_call)."""

from dataclasses import asdict, dataclass
from datetime import date, datetime
from typing import Any

from sqlalchemy import Engine, func, select
from sqlalchemy.dialects.postgresql import insert

from rlg.store.tables import llm_cache, llm_call


class BudgetExceeded(RuntimeError):
    """A call would push today's LLM spend over the configured budget. Raised before any request."""


@dataclass(frozen=True)
class CallRecord:
    """One row of llm_call: one `llm.call` invocation (all its attempts), cache hit or not."""

    provider: str
    model: str
    model_cutoff: date
    tier: str
    prompt_id: str
    prompt_hash: str
    schema_version: str
    cache_key: str
    input_tokens: int
    output_tokens: int
    cost_usd: float
    cache_hit: bool
    attempts: int
    started_at: datetime
    ok: bool
    error: str | None = None


@dataclass(frozen=True)
class CacheEntry:
    cache_key: str
    input_sha256: str
    prompt_hash: str
    model: str
    schema_version: str
    output_json: Any
    created_at: datetime


class SqlLedger:
    """Postgres-backed cache and ledger."""

    def __init__(self, engine: Engine) -> None:
        self.engine = engine

    def get_cached(self, cache_key: str) -> Any | None:
        """Cached output JSON for `cache_key`, or None."""
        with self.engine.connect() as conn:
            return conn.execute(
                select(llm_cache.c.output_json).where(llm_cache.c.cache_key == cache_key)
            ).scalar_one_or_none()

    def put_cache(self, entry: CacheEntry) -> None:
        """Store a validated output; first writer wins."""
        with self.engine.begin() as conn:
            conn.execute(insert(llm_cache).values(**asdict(entry)).on_conflict_do_nothing())

    def spent_since(self, since: datetime, tier: str | None = None) -> float:
        """Total cost_usd of calls started at or after `since` (optionally one tier)."""
        q = select(func.coalesce(func.sum(llm_call.c.cost_usd), 0)).where(
            llm_call.c.started_at >= since
        )
        if tier is not None:
            q = q.where(llm_call.c.tier == tier)
        with self.engine.connect() as conn:
            return float(conn.execute(q).scalar_one())

    def record(self, rec: CallRecord) -> None:
        """Append one llm_call row."""
        with self.engine.begin() as conn:
            conn.execute(llm_call.insert().values(**asdict(rec)))
