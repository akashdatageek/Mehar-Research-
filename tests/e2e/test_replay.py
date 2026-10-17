"""P0-07: recorded-response replay lets e2e tests run with zero network calls."""

import shutil
from pathlib import Path

import pytest
from pydantic import BaseModel

from rlg.config import load_config
from rlg.llm import LLMClient
from rlg.llm.replay import RecordingMissing, ReplayProvider
from tests.fakes import FakeProvider

ROOT = Path(__file__).resolve().parents[2]


class Card(BaseModel):
    problem: str
    methods: list[str]


def client(tmp_path: Path, provider: ReplayProvider) -> LLMClient:
    prompts = tmp_path / "prompts"
    prompts.mkdir(exist_ok=True)
    for name in ("_json_output.md", "_json_repair.md"):
        shutil.copy(ROOT / "prompts" / name, prompts / name)
    (prompts / "card.md").write_text("Summarise:\n{{text}}\n")
    cfg = load_config(env_file=tmp_path / "none.env")
    return LLMClient(cfg, providers={"anthropic": provider}, prompts_dir=prompts)


def test_record_then_replay_offline(tmp_path: Path, no_network: list[object]) -> None:
    recordings = tmp_path / "recordings"
    live = FakeProvider(['{"problem": "tool use", "methods": ["ReAct"]}'])
    recorder = ReplayProvider("anthropic", recordings, live=live)
    recorded = client(tmp_path, recorder).call("card", Card, {"text": "ReAct"}, tier="extract")
    assert len(list(recordings.glob("*.json"))) == 1

    replayed = client(tmp_path, ReplayProvider("anthropic", recordings)).call(
        "card", Card, {"text": "ReAct"}, tier="extract"
    )
    assert replayed == recorded
    assert no_network == []  # zero network calls


def test_missing_recording_is_an_error(tmp_path: Path) -> None:
    with pytest.raises(RecordingMissing):
        client(tmp_path, ReplayProvider("anthropic", tmp_path / "empty")).call(
            "card", Card, {"text": "new"}, tier="extract"
        )


def test_network_is_blocked_in_e2e() -> None:
    import socket

    with pytest.raises(RuntimeError, match="network call"):
        socket.create_connection(("example.org", 443), timeout=1)
