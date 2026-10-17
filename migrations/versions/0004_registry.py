"""Core registry: raw_document (immutable), paper, paper_version, artifact,
artifact_version, external_id.

Revision ID: 0004
Revises: 0003
Create Date: 2026-10-17
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision: str = "0004"
down_revision: str | None = "0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TS = sa.DateTime(timezone=True)


def upgrade() -> None:
    op.create_table(
        "raw_document",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column("source", sa.String, nullable=False),
        sa.Column("uri", sa.Text, nullable=False),
        sa.Column("fetched_at", TS, nullable=False),
        sa.Column("content_sha256", sa.String(64), nullable=False),
        sa.Column("blob_path", sa.Text, nullable=False),
        sa.Column("content_type", sa.String),
        sa.Column("bytes", sa.BigInteger, nullable=False),
        sa.Column("license", sa.Text),
        sa.UniqueConstraint("uri", "content_sha256", name="uq_raw_document_uri_sha"),
    )
    op.create_index("ix_raw_document_sha", "raw_document", ["content_sha256"])
    op.execute(
        """
        CREATE FUNCTION raw_document_immutable() RETURNS trigger AS $$
        BEGIN
            RAISE EXCEPTION 'raw_document rows are immutable (id=%)', OLD.id;
        END;
        $$ LANGUAGE plpgsql;
        CREATE TRIGGER raw_document_no_update BEFORE UPDATE ON raw_document
            FOR EACH ROW EXECUTE FUNCTION raw_document_immutable();
        """
    )

    op.create_table(
        "paper",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column("arxiv_id", sa.String, unique=True),
        sa.Column("doi", sa.String),
        sa.Column("title", sa.Text, nullable=False),
        sa.Column("abstract", sa.Text),
        sa.Column("authors", JSONB, nullable=False, server_default="[]"),
        sa.Column("first_published_at", TS),
        sa.Column("primary_category", sa.String),
        sa.Column("categories", JSONB, nullable=False, server_default="[]"),
        sa.Column("triage_route", sa.String),
        sa.Column("created_at", TS, nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", TS, nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint(
            "triage_route IN ('ignore', 'metadata_only', 'deep_read')", name="ck_paper_route"
        ),
    )
    op.create_index("ix_paper_doi", "paper", ["doi"])

    op.create_table(
        "paper_version",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column("paper_id", sa.BigInteger, sa.ForeignKey("paper.id"), nullable=False),
        sa.Column("version", sa.Integer, nullable=False),
        sa.Column("published_at", TS, nullable=False),
        sa.Column("raw_document_id", sa.BigInteger, sa.ForeignKey("raw_document.id")),
        sa.Column("has_source", sa.Boolean),
        sa.UniqueConstraint("paper_id", "version", name="uq_paper_version"),
    )

    op.create_table(
        "artifact",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column("kind", sa.String, nullable=False),
        sa.Column("canonical_url", sa.Text, nullable=False, unique=True),
        sa.Column("title", sa.Text),
        sa.Column("first_seen_at", TS, nullable=False),
        sa.CheckConstraint(
            "kind IN ('repo', 'model', 'spec', 'blog', 'docs')", name="ck_artifact_kind"
        ),
    )

    op.create_table(
        "artifact_version",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column("artifact_id", sa.BigInteger, sa.ForeignKey("artifact.id"), nullable=False),
        sa.Column("fetched_at", TS, nullable=False),
        sa.Column("content_sha256", sa.String(64), nullable=False),
        sa.Column(
            "raw_document_id", sa.BigInteger, sa.ForeignKey("raw_document.id"), nullable=False
        ),
        sa.UniqueConstraint("artifact_id", "content_sha256", name="uq_artifact_version_sha"),
    )

    op.create_table(
        "external_id",
        sa.Column("entity_kind", sa.String, nullable=False),
        sa.Column("entity_id", sa.BigInteger, nullable=False),
        sa.Column("scheme", sa.String, nullable=False),
        sa.Column("value", sa.String, nullable=False),
        sa.PrimaryKeyConstraint("entity_kind", "scheme", "value", name="pk_external_id"),
        sa.CheckConstraint("entity_kind IN ('paper', 'artifact')", name="ck_external_id_kind"),
        sa.CheckConstraint(
            "scheme IN ('arxiv', 'doi', 'openalex', 's2', 'github', 'hf')",
            name="ck_external_id_scheme",
        ),
    )
    op.create_index("ix_external_id_entity", "external_id", ["entity_kind", "entity_id"])


def downgrade() -> None:
    op.drop_index("ix_external_id_entity", table_name="external_id")
    op.drop_table("external_id")
    op.drop_table("artifact_version")
    op.drop_table("artifact")
    op.drop_table("paper_version")
    op.drop_index("ix_paper_doi", table_name="paper")
    op.drop_table("paper")
    op.execute("DROP TRIGGER raw_document_no_update ON raw_document")
    op.execute("DROP FUNCTION raw_document_immutable()")
    op.drop_index("ix_raw_document_sha", table_name="raw_document")
    op.drop_table("raw_document")
