"""paper_version.pdf_raw_document_id: the PDF blob beside the LaTeX e-print.

Revision ID: 0005
Revises: 0004
Create Date: 2026-10-17
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0005"
down_revision: str | None = "0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "paper_version",
        sa.Column("pdf_raw_document_id", sa.BigInteger, sa.ForeignKey("raw_document.id")),
    )


def downgrade() -> None:
    op.drop_column("paper_version", "pdf_raw_document_id")
