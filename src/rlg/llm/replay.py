"""Recorded LLM responses for e2e tests: replay by default, record when RLG_LIVE=1.

A recording is keyed by sha256(provider, model, system, user, json_schema) and stored as
`<dir>/<key>.json`. Replay never touches the network.
"""

import hashlib
import json
from dataclasses import asdict
from pathlib import Path

from rlg.llm.providers import Provider, ProviderRequest, ProviderResponse

RECORDINGS_DIR = Path(__file__).resolve().parents[3] / "tests" / "fixtures" / "llm_recordings"


class RecordingMissing(LookupError):
    """No recording for this request. Re-record with RLG_LIVE=1."""


def request_key(provider: str, request: ProviderRequest) -> str:
    data = json.dumps(
        {"provider": provider, **asdict(request)}, sort_keys=True, separators=(",", ":")
    )
    return hashlib.sha256(data.encode()).hexdigest()


class ReplayProvider:
    """Provider that serves recorded responses; with `live`, records through `live` instead."""

    def __init__(
        self, name: str, recordings_dir: Path = RECORDINGS_DIR, live: Provider | None = None
    ) -> None:
        self.name = name
        self.dir = recordings_dir
        self.live = live

    def complete(self, request: ProviderRequest) -> ProviderResponse:
        path = self.dir / f"{request_key(self.name, request)}.json"
        if self.live is not None:
            response = self.live.complete(request)
            self.dir.mkdir(parents=True, exist_ok=True)
            path.write_text(
                json.dumps({"request": asdict(request), "response": asdict(response)}, indent=2)
            )
            return response
        if not path.exists():
            raise RecordingMissing(f"no recording {path.name} for model {request.model}")
        return ProviderResponse(**json.loads(path.read_text())["response"])
