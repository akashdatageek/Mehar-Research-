"""Database connection helpers."""

import os

from sqlalchemy import Engine, create_engine, text

DEFAULT_DATABASE_URL = "postgresql+psycopg://rlg:rlg@localhost:5432/rlg"


def database_url() -> str:
    """DATABASE_URL from the environment (.env), else the docker-compose default."""
    return os.environ.get("DATABASE_URL", DEFAULT_DATABASE_URL)


def make_engine(url: str | None = None) -> Engine:
    """Create a SQLAlchemy engine for `url` (defaults to `database_url()`)."""
    return create_engine(url or database_url(), pool_pre_ping=True)


def healthcheck(engine: Engine) -> bool:
    """True when the database answers `SELECT 1`."""
    try:
        with engine.connect() as conn:
            return bool(conn.execute(text("SELECT 1")).scalar_one() == 1)
    except Exception:
        return False
