"""Typed settings: secrets from .env, pipeline config from config/*.yaml."""

from datetime import date
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

REPO_ROOT = Path(__file__).resolve().parents[3]
CONFIG_DIR = REPO_ROOT / "config"

TierName = Literal["triage", "extract", "adjudicate"]
REQUIRED_TIERS: tuple[TierName, ...] = ("triage", "extract", "adjudicate")


class ConfigError(ValueError):
    """A config file is missing or invalid. The message names the file and the bad fields."""


class EnvSettings(BaseSettings):
    """Secrets and machine-specific values. Read from the environment, then `.env`."""

    model_config = SettingsConfigDict(env_file=REPO_ROOT / ".env", extra="ignore")

    anthropic_api_key: str | None = None
    gemini_api_key: str | None = None
    openalex_api_key: str | None = None
    s2_api_key: str | None = None
    github_token: str | None = None
    hf_token: str | None = None
    arxiv_contact_email: str | None = None
    daily_llm_budget_usd: float | None = Field(default=None, ge=0)
    database_url: str = "postgresql+psycopg://rlg:rlg@localhost:5432/rlg"


class ModelTier(BaseModel):
    """One LLM tier: which provider/model to call and what it costs."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    provider: Literal["anthropic", "gemini"]
    model: str = Field(min_length=1)
    training_cutoff: date
    input_usd_per_mtok: float = Field(ge=0)
    output_usd_per_mtok: float = Field(ge=0)
    batch_discount: float = Field(default=0.0, ge=0, le=1)
    max_output_tokens: int = Field(default=4096, gt=0)

    def cost_usd(self, input_tokens: int, output_tokens: int, *, batch: bool = False) -> float:
        """Dollar cost of one call with these token counts."""
        cost = (
            input_tokens * self.input_usd_per_mtok + output_tokens * self.output_usd_per_mtok
        ) / 1_000_000
        return cost * (1 - self.batch_discount) if batch else cost


class Budgets(BaseModel):
    """Spending caps enforced in code (P0-05)."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    daily_llm_usd: float = Field(ge=0)
    triage_daily_usd: float | None = Field(default=None, ge=0)


class ModelsConfig(BaseModel):
    """Contents of config/models.yaml."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    version: int
    tiers: dict[TierName, ModelTier]
    budgets: Budgets

    @model_validator(mode="after")
    def _all_tiers_present(self) -> "ModelsConfig":
        missing = [t for t in REQUIRED_TIERS if t not in self.tiers]
        if missing:
            raise ValueError(f"missing tiers: {', '.join(missing)}")
        return self


class AppConfig(BaseModel):
    """Everything a stage needs: env settings plus models config with budget overrides applied."""

    model_config = ConfigDict(frozen=True)

    env: EnvSettings
    models: ModelsConfig

    @property
    def daily_llm_budget_usd(self) -> float:
        """Daily LLM budget: .env override if set, else models.yaml."""
        if self.env.daily_llm_budget_usd is not None:
            return self.env.daily_llm_budget_usd
        return self.models.budgets.daily_llm_usd


def _read_yaml(path: Path) -> object:
    try:
        return yaml.safe_load(path.read_text())
    except FileNotFoundError as e:
        raise ConfigError(f"{path}: file not found") from e
    except yaml.YAMLError as e:
        raise ConfigError(f"{path}: invalid YAML: {e}") from e


def _format_errors(path: Path, err: ValidationError) -> str:
    lines = [f"{path}: {err.error_count()} validation error(s)"]
    for e in err.errors():
        loc = ".".join(str(p) for p in e["loc"]) or "<root>"
        lines.append(f"  {loc}: {e['msg']}")
    return "\n".join(lines)


def load_models_config(path: Path | None = None) -> ModelsConfig:
    """Load and validate config/models.yaml; raise ConfigError with a readable message."""
    path = path or CONFIG_DIR / "models.yaml"
    try:
        return ModelsConfig.model_validate(_read_yaml(path))
    except ValidationError as e:
        raise ConfigError(_format_errors(path, e)) from e


def load_config(config_dir: Path | None = None, env_file: Path | None = None) -> AppConfig:
    """Load the full app config from `config_dir` (default: repo config/) and `.env`."""
    config_dir = config_dir or CONFIG_DIR
    env = EnvSettings(_env_file=env_file) if env_file else EnvSettings()  # type: ignore[call-arg]
    return AppConfig(env=env, models=load_models_config(config_dir / "models.yaml"))
