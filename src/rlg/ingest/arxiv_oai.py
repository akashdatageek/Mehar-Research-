"""arXiv OAI-PMH harvester (metadataPrefix=arXivRaw) -> paper, paper_version, external_id.

Each version keeps its own submission date. Re-harvesting the same records inserts nothing:
papers upsert on arxiv_id (and only update when a field changed), versions and external
ids are insert-or-ignore.
"""

import re
import xml.etree.ElementTree as ET
from collections.abc import Iterator, Sequence
from dataclasses import dataclass
from datetime import UTC, date, datetime
from email.utils import parsedate_to_datetime

from sqlalchemy import Engine, func, literal_column, or_, select
from sqlalchemy.dialects.postgresql import insert

from rlg.ingest.http import PoliteHttp
from rlg.store.tables import external_id, paper, paper_version

OAI_BASE = "https://oaipmh.arxiv.org/oai"
DEFAULT_SETS = ("cs", "stat:stat:ML")
NS = {"oai": "http://www.openarchives.org/OAI/2.0/", "raw": "http://arxiv.org/OAI/arXivRaw/"}


class OaiError(RuntimeError):
    pass


@dataclass(frozen=True)
class OaiVersion:
    version: int
    published_at: datetime
    source_type: str | None


@dataclass(frozen=True)
class OaiRecord:
    arxiv_id: str
    title: str
    abstract: str
    authors: list[str]
    categories: list[str]
    doi: str | None
    license: str | None
    versions: list[OaiVersion]

    @property
    def primary_category(self) -> str | None:
        return self.categories[0] if self.categories else None

    @property
    def first_published_at(self) -> datetime:
        return min(v.published_at for v in self.versions)


def _text(el: ET.Element, path: str) -> str | None:
    found = el.find(path, NS)
    if found is None or found.text is None:
        return None
    return " ".join(found.text.split())


def split_authors(raw: str) -> list[str]:
    """'A, B, and C (Univ X)' -> ['A', 'B', 'C']. Affiliations in parentheses are dropped."""
    depth, cleaned = 0, []
    for ch in raw:
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth = max(depth - 1, 0)
        elif depth == 0:
            cleaned.append(ch)
    parts = re.split(r",\s*(?:and\s+)?|\s+and\s+", "".join(cleaned))
    return [" ".join(p.split()) for p in parts if p.strip()]


def parse_list_records(xml: bytes) -> tuple[list[OaiRecord], str | None]:
    """Parse one ListRecords page. Returns (records, resumption token or None)."""
    root = ET.fromstring(xml)
    err = root.find("oai:error", NS)
    if err is not None:
        if err.get("code") == "noRecordsMatch":
            return [], None
        raise OaiError(f"OAI error {err.get('code')}: {(err.text or '').strip()}")
    records: list[OaiRecord] = []
    for rec in root.iterfind("oai:ListRecords/oai:record", NS):
        header = rec.find("oai:header", NS)
        if header is not None and header.get("status") == "deleted":
            continue
        meta = rec.find("oai:metadata/raw:arXivRaw", NS)
        if meta is None:
            continue
        versions = []
        for v in meta.iterfind("raw:version", NS):
            dt = parsedate_to_datetime(_text(v, "raw:date") or "")
            versions.append(
                OaiVersion(
                    version=int((v.get("version") or "v1").lstrip("v")),
                    published_at=dt.astimezone(UTC),
                    source_type=_text(v, "raw:source_type"),
                )
            )
        records.append(
            OaiRecord(
                arxiv_id=_text(meta, "raw:id") or "",
                title=_text(meta, "raw:title") or "",
                abstract=_text(meta, "raw:abstract") or "",
                authors=split_authors(_text(meta, "raw:authors") or ""),
                categories=(_text(meta, "raw:categories") or "").split(),
                doi=_text(meta, "raw:doi"),
                license=_text(meta, "raw:license"),
                versions=versions,
            )
        )
    token_el = root.find("oai:ListRecords/oai:resumptionToken", NS)
    token = (token_el.text or "").strip() if token_el is not None else ""
    return records, token or None


def iter_pages(
    http: PoliteHttp, set_spec: str, from_date: date, until_date: date
) -> Iterator[list[OaiRecord]]:
    """Yield record pages for one set and date range, following resumption tokens."""
    params: dict[str, str] = {
        "verb": "ListRecords",
        "metadataPrefix": "arXivRaw",
        "set": set_spec,
        "from": from_date.isoformat(),
        "until": until_date.isoformat(),
    }
    while True:
        body = http.get(OAI_BASE, params)
        if body is None:
            raise OaiError(f"OAI endpoint returned 404 for {params}")
        records, token = parse_list_records(body)
        yield records
        if token is None:
            return
        params = {"verb": "ListRecords", "resumptionToken": token}


@dataclass
class HarvestStats:
    records: int = 0
    papers_inserted: int = 0
    papers_updated: int = 0
    versions_inserted: int = 0

    @property
    def rows_inserted(self) -> int:
        return self.papers_inserted + self.versions_inserted


def store_records(engine: Engine, records: Sequence[OaiRecord]) -> HarvestStats:
    """Upsert papers, versions and arXiv/DOI external ids. Idempotent."""
    stats = HarvestStats(records=len(records))
    with engine.begin() as conn:
        for r in records:
            values = {
                "arxiv_id": r.arxiv_id,
                "doi": r.doi,
                "title": r.title,
                "abstract": r.abstract,
                "authors": r.authors,
                "first_published_at": r.first_published_at,
                "primary_category": r.primary_category,
                "categories": r.categories,
            }
            stmt = insert(paper).values(**values)
            changed = or_(
                *(paper.c[k].is_distinct_from(stmt.excluded[k]) for k in values if k != "arxiv_id")
            )
            upsert = stmt.on_conflict_do_update(
                index_elements=["arxiv_id"],
                set_={**{k: stmt.excluded[k] for k in values}, "updated_at": func.now()},
                where=changed,
            ).returning(paper.c.id, (literal_column("xmax") == 0).label("new"))
            row = conn.execute(upsert).one_or_none()
            if row is None:  # unchanged
                pid = conn.execute(
                    select(paper.c.id).where(paper.c.arxiv_id == r.arxiv_id)
                ).scalar_one()
            else:
                pid = row.id
                if row.new:
                    stats.papers_inserted += 1
                else:
                    stats.papers_updated += 1
            for v in r.versions:
                res = conn.execute(
                    insert(paper_version)
                    .values(paper_id=pid, version=v.version, published_at=v.published_at)
                    .on_conflict_do_nothing(index_elements=["paper_id", "version"])
                    .returning(paper_version.c.id)
                )
                stats.versions_inserted += len(res.all())
            ids = [("arxiv", r.arxiv_id)] + ([("doi", r.doi.lower())] if r.doi else [])
            for scheme, value in ids:
                conn.execute(
                    insert(external_id)
                    .values(entity_kind="paper", entity_id=pid, scheme=scheme, value=value)
                    .on_conflict_do_nothing()
                )
    return stats


def harvest(
    engine: Engine,
    http: PoliteHttp,
    from_date: date,
    until_date: date,
    sets: Sequence[str] = DEFAULT_SETS,
) -> HarvestStats:
    """Harvest `sets` for [from_date, until_date] and store everything."""
    total = HarvestStats()
    for set_spec in sets:
        for page in iter_pages(http, set_spec, from_date, until_date):
            s = store_records(engine, page)
            total.records += s.records
            total.papers_inserted += s.papers_inserted
            total.papers_updated += s.papers_updated
            total.versions_inserted += s.versions_inserted
    return total


def default_http() -> PoliteHttp:
    """PoliteHttp for arXiv: >=3 s between requests, contact e-mail in the User-Agent."""
    from rlg.config import EnvSettings
    from rlg.ingest.fixtures import ARXIV_MIN_INTERVAL_S, user_agent
    from rlg.ingest.ratelimit import RateLimiter

    return PoliteHttp(
        RateLimiter(ARXIV_MIN_INTERVAL_S), user_agent(EnvSettings().arxiv_contact_email or "")
    )
