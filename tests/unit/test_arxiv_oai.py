"""P1-02: arXiv OAI-PMH parsing and politeness (recorded responses, fake clock)."""

from datetime import UTC, date, datetime

import pytest

from rlg.ingest.arxiv_oai import OaiError, iter_pages, parse_list_records, split_authors
from rlg.ingest.http import HttpError, PoliteHttp
from rlg.ingest.ratelimit import RateLimiter
from tests.arxiv_fakes import NO_RECORDS, PAGE1, PAGE2, FakeClock, OaiTransport


def test_recorded_page_parses_into_papers_and_versions() -> None:
    records, token = parse_list_records(PAGE1)
    assert len(records) == 6
    assert token is not None and "skip%3D1300" in token
    by_id = {r.arxiv_id: r for r in records}
    r = by_id["1709.09051"]
    assert r.title and r.abstract and r.categories
    assert [v.version for v in r.versions] == sorted(v.version for v in r.versions)
    assert all(v.published_at.tzinfo is not None for v in r.versions)
    assert len({v.published_at for v in r.versions}) == len(r.versions)  # own dates
    assert r.first_published_at == r.versions[0].published_at
    assert any(rec.doi for rec in records)
    assert all(rec.primary_category == rec.categories[0] for rec in records)


def test_last_page_has_no_token() -> None:
    records, token = parse_list_records(PAGE2)
    assert len(records) == 4 and token is None


def test_version_dates_are_utc() -> None:
    records, _ = parse_list_records(PAGE1)
    v = records[0].versions[0]
    assert v.published_at.utcoffset() is not None
    assert v.published_at == v.published_at.astimezone(UTC)
    assert v.published_at < datetime(2026, 10, 2, tzinfo=UTC)


def test_split_authors() -> None:
    assert split_authors(
        "Ryan G. James, Blanca Ayala, Bahti Zakirov, and James P. Crutchfield"
    ) == [
        "Ryan G. James",
        "Blanca Ayala",
        "Bahti Zakirov",
        "James P. Crutchfield",
    ]
    assert split_authors("A. One (MIT, CSAIL) and B. Two") == ["A. One", "B. Two"]


def test_oai_errors() -> None:
    assert parse_list_records(NO_RECORDS) == ([], None)
    bad = NO_RECORDS.replace(b"noRecordsMatch", b"badArgument")
    with pytest.raises(OaiError, match="badArgument"):
        parse_list_records(bad)


def test_rate_limiter_enforces_3s_between_requests_and_follows_token() -> None:
    clock = FakeClock()
    transport = OaiTransport(clock)
    http = PoliteHttp(
        RateLimiter(3.0, clock=clock.now, sleep=clock.sleep),
        "rlg-test (mailto:test@example.org)",
        transport=transport,
        sleep=clock.sleep,
    )
    pages = list(iter_pages(http, "cs", date(2026, 10, 1), date(2026, 10, 1)))
    assert [len(p) for p in pages] == [6, 4]
    times = [c[0] for c in transport.calls]
    assert len(times) == 2 and times[1] - times[0] >= 3.0
    assert transport.calls[1][1] == {
        "verb": "ListRecords",
        "resumptionToken": parse_list_records(PAGE1)[1],
    }
    assert "mailto:" in transport.calls[0][2]["User-Agent"]


def test_retry_after_on_503_then_error() -> None:
    clock = FakeClock()
    responses = [(503, b"", {"Retry-After": "7"}), (200, b"ok", {})]
    http = PoliteHttp(
        RateLimiter(0, clock=clock.now, sleep=clock.sleep),
        "ua",
        transport=lambda url, h: responses.pop(0),
        sleep=clock.sleep,
    )
    assert http.get("https://x") == b"ok"
    assert 7.0 in clock.sleeps
    http_fail = PoliteHttp(
        RateLimiter(0), "ua", transport=lambda url, h: (500, b"", {}), sleep=clock.sleep
    )
    with pytest.raises(HttpError):
        http_fail.get("https://x")
