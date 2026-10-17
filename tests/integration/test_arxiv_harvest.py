"""P1-02: harvesting into the registry is idempotent."""

from datetime import date

import pytest
from sqlalchemy import Engine, func, select, text

from rlg.ingest.arxiv_oai import harvest
from rlg.ingest.http import PoliteHttp
from rlg.ingest.ratelimit import RateLimiter
from rlg.store.tables import external_id, paper, paper_version
from tests.arxiv_fakes import OaiTransport

pytestmark = pytest.mark.integration
DAY = date(2026, 10, 1)


def counts(engine: Engine) -> tuple[int, int, int]:
    with engine.connect() as conn:
        return tuple(  # type: ignore[return-value]
            conn.execute(select(func.count()).select_from(t)).scalar_one()
            for t in (paper, paper_version, external_id)
        )


def make_http() -> PoliteHttp:
    return PoliteHttp(RateLimiter(0), "rlg-test", transport=OaiTransport(), sleep=lambda s: None)


def test_harvest_then_reharvest_inserts_zero_rows(db_engine: Engine) -> None:
    first = harvest(db_engine, make_http(), DAY, DAY)
    assert first.papers_inserted == 10 and first.versions_inserted > 10
    before = counts(db_engine)
    assert before[0] == 10 and before[2] >= 10

    again = harvest(db_engine, make_http(), DAY, DAY)
    assert again.rows_inserted == 0 and again.papers_updated == 0
    assert counts(db_engine) == before


def test_changed_metadata_updates_not_inserts(db_engine: Engine) -> None:
    harvest(db_engine, make_http(), DAY, DAY)
    with db_engine.begin() as conn:
        conn.execute(text("UPDATE paper SET title = 'stale' WHERE arxiv_id = '1709.09051'"))
    before = counts(db_engine)
    s = harvest(db_engine, make_http(), DAY, DAY)
    assert s.papers_updated == 1 and s.rows_inserted == 0
    assert counts(db_engine) == before
    with db_engine.connect() as conn:
        title = conn.execute(
            select(paper.c.title).where(paper.c.arxiv_id == "1709.09051")
        ).scalar_one()
    assert title != "stale"
