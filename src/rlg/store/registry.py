"""Registry writes shared by all fetchers."""

from datetime import datetime

from sqlalchemy import Engine, select
from sqlalchemy.dialects.postgresql import insert

from rlg.store.blobs import BlobStore
from rlg.store.tables import raw_document


def register_raw_document(
    engine: Engine,
    blobs: BlobStore,
    *,
    source: str,
    uri: str,
    content: bytes,
    fetched_at: datetime,
    content_type: str | None = None,
    license: str | None = None,
) -> tuple[int, bool]:
    """Store `content` as a blob and record it. Returns (raw_document_id, created).

    Re-registering the same bytes for the same URI returns the existing row.
    """
    ref = blobs.put(content)
    stmt = (
        insert(raw_document)
        .values(
            source=source,
            uri=uri,
            fetched_at=fetched_at,
            content_sha256=ref.sha256,
            blob_path=ref.path,
            content_type=content_type,
            bytes=ref.bytes,
            license=license,
        )
        .on_conflict_do_nothing(constraint="uq_raw_document_uri_sha")
        .returning(raw_document.c.id)
    )
    with engine.begin() as conn:
        new_id = conn.execute(stmt).scalar_one_or_none()
        if new_id is not None:
            return new_id, True
        existing = conn.execute(
            select(raw_document.c.id).where(
                raw_document.c.uri == uri, raw_document.c.content_sha256 == ref.sha256
            )
        ).scalar_one()
        return existing, False
