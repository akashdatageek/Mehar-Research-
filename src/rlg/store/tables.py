"""SQLAlchemy Core table definitions mirroring the Alembic migrations.

Migrations are the source of truth for DDL; these objects are for typed queries.
"""

from sqlalchemy import (
    BigInteger,
    Boolean,
    Column,
    Date,
    DateTime,
    Integer,
    MetaData,
    Numeric,
    String,
    Table,
    Text,
)
from sqlalchemy.dialects.postgresql import JSONB

metadata = MetaData()

llm_call = Table(
    "llm_call",
    metadata,
    Column("id", BigInteger, primary_key=True, autoincrement=True),
    Column("provider", String, nullable=False),
    Column("model", String, nullable=False),
    Column("model_cutoff", Date, nullable=False),
    Column("tier", String, nullable=False),
    Column("prompt_id", String, nullable=False),
    Column("prompt_hash", String(64), nullable=False),
    Column("schema_version", String(64), nullable=False),
    Column("cache_key", String(64), nullable=False),
    Column("input_tokens", Integer, nullable=False),
    Column("output_tokens", Integer, nullable=False),
    Column("cost_usd", Numeric(12, 6), nullable=False),
    Column("cache_hit", Boolean, nullable=False),
    Column("attempts", Integer, nullable=False),
    Column("started_at", DateTime(timezone=True), nullable=False),
    Column("ok", Boolean, nullable=False),
    Column("error", Text),
)

llm_cache = Table(
    "llm_cache",
    metadata,
    Column("cache_key", String(64), primary_key=True),
    Column("input_sha256", String(64), nullable=False),
    Column("prompt_hash", String(64), nullable=False),
    Column("model", String, nullable=False),
    Column("schema_version", String(64), nullable=False),
    Column("output_json", JSONB, nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False),
)
