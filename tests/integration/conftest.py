"""Integration fixtures: a throwaway database on the Docker Postgres (`make up`).

Tests here skip when Postgres is unreachable, so `make test` still runs without Docker.
"""

import uuid
from collections.abc import Iterator
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import Engine, make_url, text

from rlg.store.db import database_url, healthcheck, make_engine

ROOT = Path(__file__).resolve().parents[2]


def alembic_config(url: str) -> Config:
    cfg = Config(str(ROOT / "alembic.ini"))
    cfg.attributes["database_url"] = url
    return cfg


@pytest.fixture(scope="session")
def admin_engine() -> Iterator[Engine]:
    engine = make_engine(database_url())
    if not healthcheck(engine):
        pytest.skip("Postgres not reachable; run `make up`")
    yield engine.execution_options(isolation_level="AUTOCOMMIT")
    engine.dispose()


@pytest.fixture
def empty_db_url(admin_engine: Engine) -> Iterator[str]:
    """URL of a fresh, empty database, dropped after the test."""
    name = f"rlg_test_{uuid.uuid4().hex[:12]}"
    with admin_engine.connect() as conn:
        conn.execute(text(f'CREATE DATABASE "{name}"'))
    url = make_url(database_url()).set(database=name).render_as_string(hide_password=False)
    yield url
    with admin_engine.connect() as conn:
        conn.execute(text(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)'))


@pytest.fixture
def db_engine(empty_db_url: str) -> Iterator[Engine]:
    """Engine on a fresh database migrated to head."""
    command.upgrade(alembic_config(empty_db_url), "head")
    engine = make_engine(empty_db_url)
    yield engine
    engine.dispose()
