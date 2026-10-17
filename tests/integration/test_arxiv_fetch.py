"""P1-03: fetching PDF + e-print into blobs."""

import gzip
import hashlib
from datetime import UTC, datetime
from pathlib import Path

import pytest
from sqlalchemy import Engine, insert, select, update

from rlg.ingest.arxiv_api import fetch_files, pending_deep_read
from rlg.ingest.http import PoliteHttp
from rlg.ingest.ratelimit import RateLimiter
from rlg.store.blobs import BlobStore
from rlg.store.tables import paper, paper_version, raw_document

pytestmark = pytest.mark.integration
FIXTURE_PAPERS = Path(__file__).resolve().parents[1] / "fixtures" / "papers"
T = datetime(2026, 10, 17, tzinfo=UTC)


def add_paper(engine: Engine, arxiv_id: str, versions: int = 1) -> int:
    with engine.begin() as conn:
        pid = conn.execute(
            insert(paper).values(arxiv_id=arxiv_id, title=arxiv_id).returning(paper.c.id)
        ).scalar_one()
        for v in range(1, versions + 1):
            conn.execute(insert(paper_version).values(paper_id=pid, version=v, published_at=T))
    return int(pid)


def http_serving(files: dict[str, bytes | None]) -> tuple[PoliteHttp, list[str]]:
    seen: list[str] = []

    def transport(url: str, headers: object) -> tuple[int, bytes, dict[str, str]]:
        seen.append(url)
        body = files.get(url)
        return (404, b"", {}) if body is None else (200, body, {})

    return PoliteHttp(RateLimiter(0), "rlg-test", transport=transport), seen


def version_row(engine: Engine, arxiv_id: str) -> object:
    with engine.connect() as conn:
        return conn.execute(
            select(paper_version)
            .join(paper, paper.c.id == paper_version.c.paper_id)
            .where(paper.c.arxiv_id == arxiv_id)
            .order_by(paper_version.c.version.desc())
        ).first()


@pytest.mark.skipif(
    not (FIXTURE_PAPERS / "2210.03629" / "source.tar.gz").exists(),
    reason="fixture papers not downloaded (rlg fixtures download)",
)
def test_fetch_fixture_stores_both_blobs_with_sha256(db_engine: Engine, tmp_path: Path) -> None:
    pdf = (FIXTURE_PAPERS / "2210.03629" / "paper.pdf").read_bytes()
    src = (FIXTURE_PAPERS / "2210.03629" / "source.tar.gz").read_bytes()
    add_paper(db_engine, "2210.03629", versions=3)
    http, seen = http_serving(
        {"https://arxiv.org/pdf/2210.03629v3": pdf, "https://arxiv.org/e-print/2210.03629v3": src}
    )
    blobs = BlobStore(tmp_path)
    res = fetch_files(db_engine, blobs, http, "2210.03629", now=T)
    assert len(seen) == 2  # latest version only
    assert res.version == 3 and res.has_source
    assert res.pdf_sha256 == hashlib.sha256(pdf).hexdigest()
    assert res.source_sha256 == hashlib.sha256(src).hexdigest()
    assert blobs.get(res.pdf_sha256) == pdf and blobs.get(res.source_sha256) == src
    row = version_row(db_engine, "2210.03629")
    assert row.has_source is True  # type: ignore[attr-defined]
    with db_engine.connect() as conn:
        docs = {r.id: r for r in conn.execute(select(raw_document)).all()}
    assert docs[row.raw_document_id].content_sha256 == res.source_sha256  # type: ignore[attr-defined]
    assert docs[row.pdf_raw_document_id].content_sha256 == res.pdf_sha256  # type: ignore[attr-defined]


def test_small_fetch_and_missing_source(db_engine: Engine, tmp_path: Path) -> None:
    add_paper(db_engine, "2401.00001")
    add_paper(db_engine, "2401.00002")
    tex = gzip.compress(b"\\documentclass{article}")
    http, _ = http_serving(
        {
            "https://arxiv.org/pdf/2401.00001v1": b"%PDF-1.5 a",
            "https://arxiv.org/e-print/2401.00001v1": tex,
            "https://arxiv.org/pdf/2401.00002v1": b"%PDF-1.5 b",
            # PDF-only submission: arXiv serves the PDF at the e-print URL
            "https://arxiv.org/e-print/2401.00002v1": b"%PDF-1.5 b",
        }
    )
    blobs = BlobStore(tmp_path)
    assert fetch_files(db_engine, blobs, http, "2401.00001").has_source
    res = fetch_files(db_engine, blobs, http, "2401.00002")
    assert not res.has_source and res.pdf_sha256 is not None
    row = version_row(db_engine, "2401.00002")
    assert row.has_source is False and row.raw_document_id is None  # type: ignore[attr-defined]

    add_paper(db_engine, "2401.00003")
    http404, _ = http_serving({"https://arxiv.org/pdf/2401.00003v1": b"%PDF-1.5 c"})
    assert not fetch_files(db_engine, blobs, http404, "2401.00003").has_source
    assert version_row(db_engine, "2401.00003").has_source is False  # type: ignore[attr-defined]


def test_pending_deep_read(db_engine: Engine) -> None:
    add_paper(db_engine, "2401.00010", versions=2)
    add_paper(db_engine, "2401.00011")
    with db_engine.begin() as conn:
        conn.execute(
            update(paper).where(paper.c.arxiv_id == "2401.00010").values(triage_route="deep_read")
        )
    assert pending_deep_read(db_engine) == ["2401.00010"]
