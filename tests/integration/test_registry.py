"""P1-01: core registry schema."""

from datetime import UTC, datetime
from pathlib import Path

import pytest
from sqlalchemy import Engine, func, insert, select, text, update
from sqlalchemy.exc import DBAPIError, IntegrityError

from rlg.store.blobs import BlobStore
from rlg.store.registry import register_raw_document
from rlg.store.tables import external_id, paper, paper_version, raw_document

pytestmark = pytest.mark.integration
T = datetime(2026, 10, 17, tzinfo=UTC)


def test_blob_written_twice_stored_once(db_engine: Engine, tmp_path: Path) -> None:
    store = BlobStore(tmp_path)
    kw = {"source": "arxiv", "uri": "https://arxiv.org/pdf/2210.03629", "fetched_at": T}
    id1, created1 = register_raw_document(db_engine, store, content=b"%PDF-1", **kw)
    id2, created2 = register_raw_document(db_engine, store, content=b"%PDF-1", **kw)
    assert id1 == id2 and created1 and not created2
    assert len([p for p in tmp_path.rglob("*") if p.is_file()]) == 1
    with db_engine.connect() as conn:
        assert conn.execute(select(func.count()).select_from(raw_document)).scalar_one() == 1
    # changed content at the same URI is a new immutable row
    id3, created3 = register_raw_document(db_engine, store, content=b"%PDF-2", **kw)
    assert created3 and id3 != id1


def test_raw_document_rows_are_immutable(db_engine: Engine, tmp_path: Path) -> None:
    rid, _ = register_raw_document(
        db_engine, BlobStore(tmp_path), source="s", uri="u", content=b"x", fetched_at=T
    )
    with pytest.raises(DBAPIError, match="immutable"), db_engine.begin() as conn:
        conn.execute(update(raw_document).where(raw_document.c.id == rid).values(uri="v"))


def test_paper_versions_and_external_ids(db_engine: Engine) -> None:
    with db_engine.begin() as conn:
        pid = conn.execute(
            insert(paper).values(arxiv_id="2210.03629", title="ReAct").returning(paper.c.id)
        ).scalar_one()
        for v in (1, 2):
            conn.execute(insert(paper_version).values(paper_id=pid, version=v, published_at=T))
        conn.execute(
            insert(external_id).values(
                entity_kind="paper", entity_id=pid, scheme="arxiv", value="2210.03629"
            )
        )
    with pytest.raises(IntegrityError), db_engine.begin() as conn:
        conn.execute(insert(paper_version).values(paper_id=pid, version=1, published_at=T))
    with pytest.raises(IntegrityError), db_engine.begin() as conn:
        conn.execute(
            insert(external_id).values(
                entity_kind="paper", entity_id=pid + 1, scheme="arxiv", value="2210.03629"
            )
        )
    with pytest.raises(IntegrityError), db_engine.begin() as conn:
        conn.execute(text("UPDATE paper SET triage_route = 'maybe'"))
