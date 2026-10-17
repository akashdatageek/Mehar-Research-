"""P0-07: fixture downloader (offline, fake HTTP + fake clock) and fixture presence."""

import itertools
import json
from pathlib import Path

import pytest

from rlg.ingest.fixtures import (
    FIXTURES_DIR,
    download_fixtures,
    fixture_specs,
    user_agent,
    verify_fixtures,
)
from rlg.ingest.ratelimit import RateLimiter


class FakeClock:
    def __init__(self) -> None:
        self.t = 0.0
        self.sleeps: list[float] = []

    def now(self) -> float:
        return self.t

    def sleep(self, s: float) -> None:
        self.sleeps.append(s)
        self.t += s


class FakeHttp:
    def __init__(self, clock: FakeClock, missing: set[str] = frozenset()) -> None:  # type: ignore[assignment]
        self.clock = clock
        self.calls: list[tuple[float, str, dict[str, str]]] = []
        self.missing = missing

    def __call__(self, url: str, headers: dict[str, str]) -> bytes | None:
        self.calls.append((self.clock.t, url, headers))
        self.clock.t += 0.5  # request takes some time
        return None if url in self.missing else f"bytes of {url}".encode()


def test_anchor_list_has_20_fixtures_3_pdf_only() -> None:
    specs = fixture_specs()
    assert len(specs) == 20
    assert sum(s.pdf_only for s in specs) >= 3


def test_download_is_polite_resumable_and_writes_manifest(tmp_path: Path) -> None:
    clock = FakeClock()
    http = FakeHttp(clock, missing={"https://arxiv.org/e-print/2201.11903"})
    limiter = RateLimiter(3.0, clock=clock.now, sleep=clock.sleep)
    manifest = download_fixtures(http, "me@example.org", tmp_path, limiter=limiter)

    specs = fixture_specs()
    n_requests = sum(1 if s.pdf_only else 2 for s in specs)
    assert len(http.calls) == n_requests
    times = [c[0] for c in http.calls]
    assert all(b - a >= 3.0 for a, b in itertools.pairwise(times))
    assert all("mailto:me@example.org" in c[2]["User-Agent"] for c in http.calls)

    by_id = {p["arxiv_id"]: p for p in manifest["papers"]}
    assert len(by_id) == 20
    assert by_id["2201.11903"]["has_source"] is False  # e-print 404 recorded, not fatal
    for s in specs:
        names = {f["name"] for f in by_id[s.arxiv_id]["files"]}
        assert "paper.pdf" in names
        if s.pdf_only:
            assert names == {"paper.pdf"}
    assert json.loads((tmp_path / "manifest.json").read_text()) == manifest
    assert verify_fixtures(tmp_path) == []

    # resume: everything present -> zero new requests, same manifest
    again = download_fixtures(http, "me@example.org", tmp_path, limiter=limiter)
    assert len(http.calls) == n_requests and again == manifest

    (tmp_path / "papers" / "2210.03629" / "paper.pdf").write_bytes(b"tampered")
    assert any("sha256 mismatch" in p for p in verify_fixtures(tmp_path))


def test_contact_email_required() -> None:
    with pytest.raises(ValueError, match="ARXIV_CONTACT_EMAIL"):
        user_agent("")


def test_rate_limiter_enforces_min_interval() -> None:
    clock = FakeClock()
    rl = RateLimiter(3.0, clock=clock.now, sleep=clock.sleep)
    rl.wait()
    rl.wait()
    clock.t += 10
    rl.wait()
    assert clock.sleeps == [3.0]


@pytest.mark.skipif(
    not (FIXTURES_DIR / "manifest.json").exists(),
    reason="fixture papers not downloaded; run `rlg fixtures download` (needs arxiv.org access)",
)
def test_fixture_papers_present_with_sha256() -> None:
    manifest = json.loads((FIXTURES_DIR / "manifest.json").read_text())
    assert len(manifest["papers"]) == 20
    assert sum(1 for p in manifest["papers"] if p["pdf_only"]) >= 3
    assert verify_fixtures() == []
