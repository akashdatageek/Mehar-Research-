"""P0-04: provider-agnostic LLM client."""

import shutil
from pathlib import Path

import pytest
from pydantic import BaseModel

from rlg.config import load_config
from rlg.llm import LLMClient, PromptError, SchemaError, load_prompt
from tests.fakes import FakeProvider

ROOT = Path(__file__).resolve().parents[2]


class Label(BaseModel):
    label: str
    confidence: float


@pytest.fixture
def prompts_dir(tmp_path: Path) -> Path:
    d = tmp_path / "prompts"
    d.mkdir()
    for name in ("_json_output.md", "_json_repair.md"):
        shutil.copy(ROOT / "prompts" / name, d / name)
    (d / "classify.md").write_text("Classify this abstract:\n{{abstract}}\nYear: {{year}}\n")
    return d


def make_client(prompts_dir: Path, fake: FakeProvider, tmp_path: Path) -> LLMClient:
    cfg = load_config(env_file=tmp_path / "none.env")
    return LLMClient(cfg, providers={"anthropic": fake}, prompts_dir=prompts_dir)


def test_valid_json_returns_pydantic_object(prompts_dir: Path, tmp_path: Path) -> None:
    fake = FakeProvider(['{"label": "deep_read", "confidence": 0.9}'])
    client = make_client(prompts_dir, fake, tmp_path)
    out = client.call("classify", Label, {"abstract": "ReAct ...", "year": 2022}, tier="triage")
    assert out == Label(label="deep_read", confidence=0.9)
    assert len(fake.requests) == 1
    req = fake.requests[0]
    assert "ReAct ..." in req.user and "Year: 2022" in req.user
    assert '"confidence"' in req.system  # schema rendered into the system prompt
    assert req.model == client.tier("triage").model


def test_repair_retry_recovers(prompts_dir: Path, tmp_path: Path) -> None:
    fake = FakeProvider(["not json", '{"label": "ignore", "confidence": 0.2}'])
    client = make_client(prompts_dir, fake, tmp_path)
    res = client.call_with_meta("classify", Label, {"abstract": "x", "year": 1}, tier="triage")
    assert res.output.label == "ignore"
    assert len(res.attempts) == 2
    assert res.attempts[0].error is not None and res.attempts[1].error is None
    assert "did not validate" in fake.requests[1].user
    assert "not json" in fake.requests[1].user


def test_invalid_json_after_repair_raises_schema_error(prompts_dir: Path, tmp_path: Path) -> None:
    fake = FakeProvider(['{"label": "x"}', '{"label": "x", "confidence": "high"}'])
    client = make_client(prompts_dir, fake, tmp_path)
    with pytest.raises(SchemaError):
        client.call("classify", Label, {"abstract": "x", "year": 1}, tier="triage")
    assert len(fake.requests) == 2  # exactly one repair retry


def test_prompt_hash_changes_when_file_changes(prompts_dir: Path) -> None:
    h1 = load_prompt("classify", prompts_dir).sha256
    assert load_prompt("classify", prompts_dir).sha256 == h1
    (prompts_dir / "classify.md").write_text("Classify carefully:\n{{abstract}} {{year}}\n")
    assert load_prompt("classify", prompts_dir).sha256 != h1


def test_missing_input_and_unknown_prompt(prompts_dir: Path) -> None:
    with pytest.raises(PromptError, match="missing inputs: year"):
        load_prompt("classify", prompts_dir).render({"abstract": "x"})
    with pytest.raises(PromptError, match="not found"):
        load_prompt("nope", prompts_dir)
    with pytest.raises(PromptError, match="invalid prompt id"):
        load_prompt("../etc/passwd", prompts_dir)


def test_unknown_tier(prompts_dir: Path, tmp_path: Path) -> None:
    client = make_client(prompts_dir, FakeProvider([]), tmp_path)
    with pytest.raises(ValueError, match="unknown tier"):
        client.call("classify", Label, {"abstract": "x", "year": 1}, tier="huge")
