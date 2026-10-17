"""Database connection helpers."""

from sqlalchemy import Engine, create_engine, text

from rlg.config.settings import EnvSettings


def database_url() -> str:
    """DATABASE_URL from the environment or .env, else the docker-compose default."""
    return EnvSettings().database_url


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
