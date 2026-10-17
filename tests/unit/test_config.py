"""P0-03: config loading."""

from datetime import date
from pathlib import Path

import pytest
import yaml

from rlg.config import ConfigError, load_config, load_models_config

ROOT = Path(__file__).resolve().parents[2]


def _write_models(tmp_path: Path, data: object) -> Path:
    path = tmp_path / "models.yaml"
    path.write_text(yaml.safe_dump(data))
    return path


def _example() -> dict[str, object]:
    data = yaml.safe_load((ROOT / "config" / "models.yaml").read_text())
    assert isinstance(data, dict)
    return data


def test_loads_example_config(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.delenv("DAILY_LLM_BUDGET_USD", raising=False)
    cfg = load_config(env_file=tmp_path / "missing.env")
    assert set(cfg.models.tiers) == {"triage", "extract", "adjudicate"}
    tier = cfg.models.tiers["adjudicate"]
    assert tier.provider == "anthropic"
    assert isinstance(tier.training_cutoff, date)
    assert cfg.daily_llm_budget_usd == cfg.models.budgets.daily_llm_usd


def test_env_overrides_daily_budget(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    env = tmp_path / ".env"
    env.write_text("DAILY_LLM_BUDGET_USD=1.25\nS2_API_KEY=abc\n")
    monkeypatch.delenv("DAILY_LLM_BUDGET_USD", raising=False)
    cfg = load_config(env_file=env)
    assert cfg.daily_llm_budget_usd == 1.25
    assert cfg.env.s2_api_key == "abc"


def test_tier_cost() -> None:
    tier = load_models_config().tiers["extract"]
    cost = tier.cost_usd(1_000_000, 1_000_000)
    assert cost == pytest.approx(tier.input_usd_per_mtok + tier.output_usd_per_mtok)
    assert tier.cost_usd(1_000_000, 0, batch=True) == pytest.approx(
        tier.input_usd_per_mtok * (1 - tier.batch_discount)
    )


def test_invalid_models_yaml_raises_clear_error(tmp_path: Path) -> None:
    data = _example()
    tiers = data["tiers"]
    assert isinstance(tiers, dict)
    tiers["extract"]["provider"] = "openai"
    tiers["extract"]["input_usd_per_mtok"] = -1
    del tiers["triage"]
    path = _write_models(tmp_path, data)
    with pytest.raises(ConfigError) as exc:
        load_models_config(path)
    msg = str(exc.value)
    assert str(path) in msg
    assert "tiers.extract.provider" in msg
    assert "tiers.extract.input_usd_per_mtok" in msg


def test_missing_tier_raises(tmp_path: Path) -> None:
    data = _example()
    tiers = data["tiers"]
    assert isinstance(tiers, dict)
    del tiers["triage"]
    with pytest.raises(ConfigError, match="missing tiers: triage"):
        load_models_config(_write_models(tmp_path, data))


def test_unknown_field_rejected(tmp_path: Path) -> None:
    data = _example()
    tiers = data["tiers"]
    assert isinstance(tiers, dict)
    tiers["triage"]["pirce"] = 1
    with pytest.raises(ConfigError, match=r"tiers\.triage\.pirce"):
        load_models_config(_write_models(tmp_path, data))


def test_bad_yaml_and_missing_file(tmp_path: Path) -> None:
    bad = tmp_path / "models.yaml"
    bad.write_text("tiers: [unclosed")
    with pytest.raises(ConfigError, match="invalid YAML"):
        load_models_config(bad)
    with pytest.raises(ConfigError, match="file not found"):
        load_models_config(tmp_path / "nope.yaml")
