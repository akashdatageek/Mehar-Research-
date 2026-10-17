"""P0-02: Postgres + pgvector via Docker."""

import pytest
from alembic import command
from sqlalchemy import Engine, create_engine, text

from rlg.store.db import healthcheck

from .conftest import alembic_config

pytestmark = pytest.mark.integration


def test_healthcheck(admin_engine: Engine) -> None:
    assert healthcheck(admin_engine)


def test_pgvector_version_at_least_0_8_7(db_engine: Engine) -> None:
    with db_engine.connect() as conn:
        version = conn.execute(
            text("SELECT extversion FROM pg_extension WHERE extname = 'vector'")
        ).scalar_one()
    assert tuple(int(p) for p in version.split(".")) >= (0, 8, 7)


def test_vector_column_create_and_query(db_engine: Engine) -> None:
    with db_engine.begin() as conn:
        conn.execute(text("CREATE TABLE emb (id int PRIMARY KEY, v vector(3))"))
        conn.execute(
            text("INSERT INTO emb VALUES (1, '[1,0,0]'), (2, '[0,1,0]'), (3, '[0.9,0.1,0]')")
        )
        rows = (
            conn.execute(text("SELECT id FROM emb ORDER BY v <-> '[1,0,0]' LIMIT 2"))
            .scalars()
            .all()
        )
    assert rows == [1, 3]


def test_alembic_upgrade_then_downgrade(empty_db_url: str) -> None:
    cfg = alembic_config(empty_db_url)
    command.upgrade(cfg, "head")
    command.downgrade(cfg, "base")
    engine = create_engine(empty_db_url)
    with engine.connect() as conn:
        assert (
            conn.execute(
                text("SELECT count(*) FROM pg_extension WHERE extname = 'vector'")
            ).scalar_one()
            == 0
        )
        assert conn.execute(text("SELECT version_num FROM alembic_version")).all() == []
    engine.dispose()
