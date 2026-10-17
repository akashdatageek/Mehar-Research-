"""P0-05: LLM cache, cost ledger, budget guard (against Postgres)."""

import shutil
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from pydantic import BaseModel
from sqlalchemy import Engine, func, select

from rlg.config import load_config
from rlg.llm import BudgetExceeded, LLMClient, SchemaError, SqlLedger
from rlg.store.tables import llm_call
from tests.fakes import FakeProvider

pytestmark = pytest.mark.integration

ROOT = Path(__file__).resolve().parents[2]
VALID = '{"label": "deep_read", "confidence": 0.9}'


class Label(BaseModel):
    label: str
    confidence: float


class Clock:
    def __init__(self, t: datetime) -> None:
        self.t = t

    def __call__(self) -> datetime:
        return self.t


@pytest.fixture
def prompts_dir(tmp_path: Path) -> Path:
    d = tmp_path / "prompts"
    d.mkdir()
    for name in ("_json_output.md", "_json_repair.md"):
        shutil.copy(ROOT / "prompts" / name, d / name)
    (d / "classify.md").write_text("Classify:\n{{abstract}}\n")
    return d


def make_client(
    db_engine: Engine,
    prompts_dir: Path,
    fake: FakeProvider,
    tmp_path: Path,
    budget: float | None = None,
    clock: Clock | None = None,
) -> LLMClient:
    env = tmp_path / "test.env"
    env.write_text(f"DAILY_LLM_BUDGET_USD={budget}\n" if budget is not None else "")
    return LLMClient(
        load_config(env_file=env),
        providers={"anthropic": fake},
        prompts_dir=prompts_dir,
        ledger=SqlLedger(db_engine),
        now=clock or Clock(datetime(2026, 10, 17, 12, tzinfo=UTC)),
    )


def rows(engine: Engine) -> list[dict[str, object]]:
    with engine.connect() as conn:
        return [dict(r._mapping) for r in conn.execute(select(llm_call).order_by(llm_call.c.id))]


def test_second_identical_call_is_cache_hit_with_zero_cost(
    db_engine: Engine, prompts_dir: Path, tmp_path: Path
) -> None:
    fake = FakeProvider([VALID])
    client = make_client(db_engine, prompts_dir, fake, tmp_path)
    first = client.call_with_meta("classify", Label, {"abstract": "ReAct"}, tier="extract")
    second = client.call_with_meta("classify", Label, {"abstract": "ReAct"}, tier="extract")
    assert len(fake.requests) == 1  # no second paid call
    assert not first.cache_hit and first.cost_usd > 0
    assert second.cache_hit and second.cost_usd == 0
    assert second.output == first.output
    r = rows(db_engine)
    assert [x["cache_hit"] for x in r] == [False, True]
    assert float(r[1]["cost_usd"]) == 0  # type: ignore[arg-type]


def test_cache_key_changes_with_prompt_or_input(
    db_engine: Engine, prompts_dir: Path, tmp_path: Path
) -> None:
    fake = FakeProvider([VALID, VALID, VALID])
    client = make_client(db_engine, prompts_dir, fake, tmp_path)
    client.call("classify", Label, {"abstract": "A"}, tier="extract")
    client.call("classify", Label, {"abstract": "B"}, tier="extract")
    (prompts_dir / "classify.md").write_text("Classify carefully:\n{{abstract}}\n")
    client.call("classify", Label, {"abstract": "A"}, tier="extract")
    assert len(fake.requests) == 3


def test_over_budget_raises_before_any_provider_request(
    db_engine: Engine, prompts_dir: Path, tmp_path: Path
) -> None:
    fake = FakeProvider([VALID])
    client = make_client(db_engine, prompts_dir, fake, tmp_path, budget=0.0001)
    with pytest.raises(BudgetExceeded):
        client.call("classify", Label, {"abstract": "x"}, tier="adjudicate")
    assert fake.requests == []
    r = rows(db_engine)
    assert len(r) == 1 and r[0]["ok"] is False and "BudgetExceeded" in str(r[0]["error"])


def test_budget_counts_todays_spend_only(
    db_engine: Engine, prompts_dir: Path, tmp_path: Path
) -> None:
    clock = Clock(datetime(2026, 10, 17, 23, 0, tzinfo=UTC))
    # worst case per adjudicate call ~ 16000 out tokens * $20/M = $0.32; 1M in tokens = $4.
    fake = FakeProvider([VALID, VALID], input_tokens=1_000_000, output_tokens=0)
    client = make_client(db_engine, prompts_dir, fake, tmp_path, budget=4.2, clock=clock)
    client.call("classify", Label, {"abstract": "a"}, tier="adjudicate")  # spends $4.00
    with pytest.raises(BudgetExceeded):
        client.call("classify", Label, {"abstract": "b"}, tier="adjudicate")
    clock.t += timedelta(hours=2)  # next UTC day
    client.call("classify", Label, {"abstract": "b"}, tier="adjudicate")
    assert len(fake.requests) == 2


def test_every_call_writes_one_row(db_engine: Engine, prompts_dir: Path, tmp_path: Path) -> None:
    fake = FakeProvider([VALID, "bad", VALID, "bad", "still bad"])
    client = make_client(db_engine, prompts_dir, fake, tmp_path)
    client.call("classify", Label, {"abstract": "1"}, tier="triage")  # ok, 1 attempt
    client.call("classify", Label, {"abstract": "1"}, tier="triage")  # cache hit
    client.call("classify", Label, {"abstract": "2"}, tier="triage")  # repaired, 2 attempts
    with pytest.raises(SchemaError):
        client.call("classify", Label, {"abstract": "3"}, tier="triage")  # failed
    r = rows(db_engine)
    assert len(r) == 4
    assert [x["attempts"] for x in r] == [1, 0, 2, 2]
    assert [x["ok"] for x in r] == [True, True, True, False]
    assert all(x["prompt_hash"] and x["model_cutoff"] and x["provider"] for x in r)
    with db_engine.connect() as conn:
        failed_cost = conn.execute(
            select(func.sum(llm_call.c.cost_usd)).where(llm_call.c.ok.is_(False))
        ).scalar_one()
    assert failed_cost > 0  # failed calls still count toward spend
