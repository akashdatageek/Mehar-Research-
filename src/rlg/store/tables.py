"""SQLAlchemy Core table definitions mirroring the Alembic migrations.

Migrations are the source of truth for DDL; these objects are for typed queries.
"""

from sqlalchemy import (
    BigInteger,
    Boolean,
    Column,
    Date,
    DateTime,
    ForeignKey,
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

job = Table(
    "job",
    metadata,
    Column("id", BigInteger, primary_key=True, autoincrement=True),
    Column("kind", String, nullable=False),
    Column("payload_json", JSONB, nullable=False),
    Column("dedup_key", String, unique=True),
    Column("status", String, nullable=False),
    Column("attempts", Integer, nullable=False),
    Column("max_attempts", Integer, nullable=False),
    Column("run_after", DateTime(timezone=True), nullable=False),
    Column("locked_at", DateTime(timezone=True)),
    Column("locked_by", String),
    Column("last_error", Text),
    Column("created_at", DateTime(timezone=True), nullable=False),
    Column("finished_at", DateTime(timezone=True)),
)

raw_document = Table(
    "raw_document",
    metadata,
    Column("id", BigInteger, primary_key=True, autoincrement=True),
    Column("source", String, nullable=False),
    Column("uri", Text, nullable=False),
    Column("fetched_at", DateTime(timezone=True), nullable=False),
    Column("content_sha256", String(64), nullable=False),
    Column("blob_path", Text, nullable=False),
    Column("content_type", String),
    Column("bytes", BigInteger, nullable=False),
    Column("license", Text),
)

paper = Table(
    "paper",
    metadata,
    Column("id", BigInteger, primary_key=True, autoincrement=True),
    Column("arxiv_id", String, unique=True),
    Column("doi", String),
    Column("title", Text, nullable=False),
    Column("abstract", Text),
    Column("authors", JSONB, nullable=False),
    Column("first_published_at", DateTime(timezone=True)),
    Column("primary_category", String),
    Column("categories", JSONB, nullable=False),
    Column("triage_route", String),
    Column("created_at", DateTime(timezone=True), nullable=False),
    Column("updated_at", DateTime(timezone=True), nullable=False),
)

paper_version = Table(
    "paper_version",
    metadata,
    Column("id", BigInteger, primary_key=True, autoincrement=True),
    Column("paper_id", BigInteger, ForeignKey("paper.id"), nullable=False),
    Column("version", Integer, nullable=False),
    Column("published_at", DateTime(timezone=True), nullable=False),
    Column("raw_document_id", BigInteger, ForeignKey("raw_document.id")),
    Column("has_source", Boolean),
)

artifact = Table(
    "artifact",
    metadata,
    Column("id", BigInteger, primary_key=True, autoincrement=True),
    Column("kind", String, nullable=False),
    Column("canonical_url", Text, nullable=False, unique=True),
    Column("title", Text),
    Column("first_seen_at", DateTime(timezone=True), nullable=False),
)

artifact_version = Table(
    "artifact_version",
    metadata,
    Column("id", BigInteger, primary_key=True, autoincrement=True),
    Column("artifact_id", BigInteger, ForeignKey("artifact.id"), nullable=False),
    Column("fetched_at", DateTime(timezone=True), nullable=False),
    Column("content_sha256", String(64), nullable=False),
    Column("raw_document_id", BigInteger, ForeignKey("raw_document.id"), nullable=False),
)

external_id = Table(
    "external_id",
    metadata,
    Column("entity_kind", String, primary_key=True),
    Column("entity_id", BigInteger, nullable=False),
    Column("scheme", String, primary_key=True),
    Column("value", String, primary_key=True),
)
