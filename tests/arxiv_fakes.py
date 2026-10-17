"""Fake HTTP transport serving the recorded arXiv OAI pages."""

import urllib.parse
from collections.abc import Mapping
from pathlib import Path

FIXTURES = Path(__file__).resolve().parent / "fixtures" / "arxiv_oai"
PAGE1 = (FIXTURES / "cs_2026-10-01_page1.xml").read_bytes()
PAGE2 = (FIXTURES / "cs_2026-10-01_page2.xml").read_bytes()


class FakeClock:
    def __init__(self) -> None:
        self.t = 0.0
        self.sleeps: list[float] = []

    def now(self) -> float:
        return self.t

    def sleep(self, s: float) -> None:
        self.sleeps.append(s)
        self.t += s


class OaiTransport:
    """Serves page1 for the initial cs query, page2 for its resumption token."""

    def __init__(self, clock: FakeClock | None = None) -> None:
        self.clock = clock
        self.calls: list[tuple[float, dict[str, str], Mapping[str, str]]] = []

    def __call__(self, url: str, headers: Mapping[str, str]) -> tuple[int, bytes, dict[str, str]]:
        params = dict(urllib.parse.parse_qsl(urllib.parse.urlsplit(url).query))
        self.calls.append((self.clock.t if self.clock else 0.0, params, headers))
        if self.clock:
            self.clock.t += 0.2
        if "resumptionToken" in params:
            return 200, PAGE2, {}
        if params.get("set") == "cs":
            return 200, PAGE1, {}
        return 200, NO_RECORDS, {}


NO_RECORDS = b"""<?xml version="1.0" encoding="UTF-8"?>
<OAI-PMH xmlns="http://www.openarchives.org/OAI/2.0/">
<responseDate>2026-10-17T00:00:00Z</responseDate>
<request verb="ListRecords">http://oaipmh.arxiv.org/oai</request>
<error code="noRecordsMatch">The combination of the values of the from, until, set and
metadataPrefix arguments results in an empty list.</error>
</OAI-PMH>"""
