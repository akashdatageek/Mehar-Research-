"""P1-03: arXiv API feed parsing and e-print sniffing."""

import gzip
from datetime import date
from pathlib import Path

from rlg.ingest.arxiv_api import is_latex_source, listing_query, parse_feed

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "arxiv_oai"
FEED = (FIXTURES / "api_listing_2026-10-15.xml").read_bytes()


def test_recorded_feed_parses() -> None:
    records, total = parse_feed(FEED)
    assert total == 714 and len(records) == 3
    r = records[0]
    assert r.arxiv_id == "2610.22372" and "LIBERO-PeRM" in r.title
    assert r.versions[0].version == 1 and r.versions[0].published_at.tzinfo is not None
    assert r.authors and all(r.authors)
    assert r.primary_category is not None and r.primary_category in r.categories


def test_listing_query_covers_whole_utc_day() -> None:
    q = listing_query(date(2026, 10, 15), ["cs.*", "stat.ML"])
    assert q == "(cat:cs.* OR cat:stat.ML) AND submittedDate:[202610150000 TO 202610152359]"


def test_eprint_sniffing() -> None:
    assert is_latex_source(gzip.compress(b"\\documentclass{article}"))
    tar = bytearray(512)
    tar[257:262] = b"ustar"
    assert is_latex_source(bytes(tar))
    assert not is_latex_source(b"%PDF-1.5 ...")
