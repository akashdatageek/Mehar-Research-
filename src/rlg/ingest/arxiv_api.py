"""arXiv API: same-day listings (Atom feed) and per-paper PDF + LaTeX e-print fetch.

E-print responses are sniffed: gzip/tar = LaTeX source; a PDF body (arXiv serves the PDF
for PDF-only submissions) or a 404 means has_source = false.
"""

import hashlib
import re
import urllib.parse
import xml.etree.ElementTree as ET
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta

from sqlalchemy import Engine, and_, func, select, update

from rlg.ingest.arxiv_oai import HarvestStats, OaiRecord, OaiVersion, store_records
from rlg.ingest.http import PoliteHttp
from rlg.store.blobs import BlobStore
from rlg.store.registry import register_raw_document
from rlg.store.tables import paper, paper_version

API_BASE = "https://export.arxiv.org/api/query"
DEFAULT_CATEGORIES = ("cs.*", "stat.ML")
PAGE_SIZE = 200
ATOM = {
    "a": "http://www.w3.org/2005/Atom",
    "arxiv": "http://arxiv.org/schemas/atom",
    "os": "http://a9.com/-/spec/opensearch/1.1/",
}
_ID = re.compile(r"abs/(?P<id>.+?)v(?P<v>\d+)$")


def _t(el: ET.Element, path: str) -> str | None:
    found = el.find(path, ATOM)
    return " ".join(found.text.split()) if found is not None and found.text else None


def _dt(s: str | None) -> datetime:
    return datetime.fromisoformat((s or "").replace("Z", "+00:00")).astimezone(UTC)


def parse_feed(xml: bytes) -> tuple[list[OaiRecord], int]:
    """Parse an API Atom feed into records (v1 date = published, vN date = updated)."""
    root = ET.fromstring(xml)
    total = int(_t(root, "os:totalResults") or 0)
    records = []
    for e in root.iterfind("a:entry", ATOM):
        m = _ID.search(_t(e, "a:id") or "")
        if not m:
            continue
        n = int(m.group("v"))
        published, updated = _dt(_t(e, "a:published")), _dt(_t(e, "a:updated"))
        versions = [OaiVersion(1, published, None)]
        if n > 1:
            versions.append(OaiVersion(n, updated, None))
        primary = e.find("arxiv:primary_category", ATOM)
        cats = [c.get("term", "") for c in e.iterfind("a:category", ATOM)]
        if primary is not None and primary.get("term") in cats:
            cats.remove(primary.get("term", ""))
            cats.insert(0, primary.get("term", ""))
        records.append(
            OaiRecord(
                arxiv_id=m.group("id"),
                title=_t(e, "a:title") or "",
                abstract=_t(e, "a:summary") or "",
                authors=[_t(a, "a:name") or "" for a in e.iterfind("a:author", ATOM)],
                categories=[c for c in cats if c],
                doi=_t(e, "arxiv:doi"),
                license=None,
                versions=versions,
            )
        )
    return records, total


def listing_query(day: date, categories: Sequence[str] = DEFAULT_CATEGORIES) -> str:
    cats = " OR ".join(f"cat:{c}" for c in categories)
    d = day.strftime("%Y%m%d")
    return f"({cats}) AND submittedDate:[{d}0000 TO {d}2359]"


def daily_listing(
    engine: Engine,
    http: PoliteHttp,
    day: date,
    categories: Sequence[str] = DEFAULT_CATEGORIES,
    page_size: int = PAGE_SIZE,
) -> HarvestStats:
    """Store every paper submitted on `day` (UTC) in `categories`."""
    total = HarvestStats()
    start = 0
    while True:
        body = http.get(
            API_BASE,
            {
                "search_query": listing_query(day, categories),
                "sortBy": "submittedDate",
                "sortOrder": "ascending",
                "start": str(start),
                "max_results": str(page_size),
            },
        )
        records, n_total = parse_feed(body or b"<feed xmlns='http://www.w3.org/2005/Atom'/>")
        s = store_records(engine, records)
        total.records += s.records
        total.papers_inserted += s.papers_inserted
        total.papers_updated += s.papers_updated
        total.versions_inserted += s.versions_inserted
        start += page_size
        if not records or start >= n_total:
            return total


@dataclass(frozen=True)
class FetchResult:
    arxiv_id: str
    version: int
    pdf_sha256: str | None
    source_sha256: str | None

    @property
    def has_source(self) -> bool:
        return self.source_sha256 is not None


def is_latex_source(data: bytes) -> bool:
    """gzip, or a plain tar archive (ustar magic at offset 257)."""
    return data[:2] == b"\x1f\x8b" or data[257:262] == b"ustar"


def fetch_files(
    engine: Engine,
    blobs: BlobStore,
    http: PoliteHttp,
    arxiv_id: str,
    version: int | None = None,
    now: datetime | None = None,
) -> FetchResult:
    """Fetch PDF + e-print for one paper version (default: latest known) into blobs."""
    now = now or datetime.now(UTC)
    with engine.connect() as conn:
        q = (
            select(paper_version.c.id, paper_version.c.version)
            .join(paper, paper.c.id == paper_version.c.paper_id)
            .where(paper.c.arxiv_id == arxiv_id)
            .order_by(paper_version.c.version.desc())
        )
        if version is not None:
            q = q.where(paper_version.c.version == version)
        row = conn.execute(q.limit(1)).one_or_none()
    if row is None:
        raise LookupError(f"no paper_version for {arxiv_id} v{version or 'latest'}")
    vid = f"{arxiv_id}v{row.version}"
    q_id = urllib.parse.quote(vid, safe="./")

    pdf_url = f"https://arxiv.org/pdf/{q_id}"
    pdf = http.get(pdf_url)
    pdf_doc = None
    if pdf is not None:
        pdf_doc, _ = register_raw_document(
            engine,
            blobs,
            source="arxiv_pdf",
            uri=pdf_url,
            content=pdf,
            fetched_at=now,
            content_type="application/pdf",
        )

    src_url = f"https://arxiv.org/e-print/{q_id}"
    src = http.get(src_url)
    src_doc = None
    if src is not None and is_latex_source(src):
        src_doc, _ = register_raw_document(
            engine,
            blobs,
            source="arxiv_eprint",
            uri=src_url,
            content=src,
            fetched_at=now,
            content_type="application/gzip",
        )

    with engine.begin() as conn:
        conn.execute(
            update(paper_version)
            .where(paper_version.c.id == row.id)
            .values(
                raw_document_id=src_doc, pdf_raw_document_id=pdf_doc, has_source=src_doc is not None
            )
        )
    return FetchResult(
        arxiv_id,
        row.version,
        hashlib.sha256(pdf).hexdigest() if pdf is not None else None,
        hashlib.sha256(src).hexdigest() if src is not None and src_doc is not None else None,
    )


def pending_deep_read(engine: Engine, limit: int = 100) -> list[str]:
    """arXiv ids routed deep_read whose latest version has not been fetched yet."""
    latest = (
        select(paper_version.c.paper_id, func.max(paper_version.c.version).label("v"))
        .group_by(paper_version.c.paper_id)
        .subquery()
    )
    q = (
        select(paper.c.arxiv_id)
        .join(latest, latest.c.paper_id == paper.c.id)
        .join(
            paper_version,
            and_(paper_version.c.paper_id == paper.c.id, paper_version.c.version == latest.c.v),
        )
        .where(paper.c.triage_route == "deep_read", paper_version.c.has_source.is_(None))
        .order_by(paper.c.first_published_at)
        .limit(limit)
    )
    with engine.connect() as conn:
        return [r for (r,) in conn.execute(q) if r]


def yesterday_utc(now: datetime | None = None) -> date:
    return ((now or datetime.now(UTC)) - timedelta(days=1)).date()
