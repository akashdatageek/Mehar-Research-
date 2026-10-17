"""Queue handlers for ingestion jobs. Import registers them with rlg.queue."""

from datetime import date
from typing import Any

from rlg.queue import handler


@handler("arxiv.harvest_day")
def harvest_day(payload: dict[str, Any]) -> None:
    """Harvest one UTC day of arXiv OAI records: payload {"day": "YYYY-MM-DD", "sets": [...]}."""
    from rlg.ingest.arxiv_oai import DEFAULT_SETS, default_http, harvest
    from rlg.store.db import make_engine

    day = date.fromisoformat(payload["day"])
    harvest(make_engine(), default_http(), day, day, payload.get("sets") or DEFAULT_SETS)


@handler("arxiv.fetch_files")
def fetch_files_job(payload: dict[str, Any]) -> None:
    """Fetch PDF + e-print for one paper: payload {"arxiv_id": "...", "version": int?}."""
    from rlg.config import EnvSettings
    from rlg.ingest.arxiv_api import fetch_files
    from rlg.ingest.arxiv_oai import default_http
    from rlg.store.blobs import BlobStore
    from rlg.store.db import make_engine

    fetch_files(
        make_engine(),
        BlobStore(EnvSettings().blob_dir),
        default_http(),
        payload["arxiv_id"],
        payload.get("version"),
    )
