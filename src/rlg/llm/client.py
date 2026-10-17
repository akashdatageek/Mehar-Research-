"""`llm.call(prompt_id, schema, inputs, tier)`: the only way pipeline code calls an LLM.

Order of operations for one call:
  1. render prompt, compute cache key = sha256(input_sha256, prompt_hash, model, schema_version)
  2. cache hit -> validated output, llm_call row with cache_hit=true and cost 0
  3. budget guard -> BudgetExceeded before any provider request
  4. provider request, schema validation, at most one repair retry (budget re-checked)
  5. cache the validated output; exactly one llm_call row per call, success or failure
"""

import hashlib
import json
import math
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ValidationError

from rlg.config import AppConfig, ModelTier, load_config
from rlg.llm.ledger import BudgetExceeded, CacheEntry, CallRecord, SqlLedger
from rlg.llm.prompts import Prompt, load_prompt
from rlg.llm.providers import (
    AnthropicProvider,
    GeminiProvider,
    Provider,
    ProviderRequest,
    ProviderResponse,
)

SYSTEM_PROMPT_ID = "_json_output"
REPAIR_PROMPT_ID = "_json_repair"
CHARS_PER_TOKEN_ESTIMATE = 3  # conservative: overestimates input tokens for the budget guard


class SchemaError(ValueError):
    """The model's output failed schema validation, including after one repair retry."""


@dataclass(frozen=True)
class Attempt:
    """One provider round-trip (the first try or the repair retry)."""

    request: ProviderRequest
    response: ProviderResponse
    error: str | None


@dataclass(frozen=True)
class CallResult[T: BaseModel]:
    """Validated output plus what the ledger recorded."""

    output: T
    prompt: Prompt
    tier_name: str
    tier: ModelTier
    cache_key: str
    cache_hit: bool
    cost_usd: float
    attempts: list[Attempt] = field(default_factory=list)


def sha256_json(value: object) -> str:
    """sha256 of canonical JSON (sorted keys, no whitespace)."""
    data = json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(data.encode()).hexdigest()


def schema_version(schema: type[BaseModel]) -> str:
    """Hash of the Pydantic model's JSON schema."""
    return sha256_json(schema.model_json_schema())


def cache_key(input_sha256: str, prompt_hash: str, model: str, schema_ver: str) -> str:
    return hashlib.sha256(f"{input_sha256}:{prompt_hash}:{model}:{schema_ver}".encode()).hexdigest()


def _validate[T: BaseModel](schema: type[T], text: str) -> T | str:
    """Validated object, or a readable error string."""
    try:
        return schema.model_validate_json(text)
    except ValidationError as e:
        return str(e)


def _utc_now() -> datetime:
    return datetime.now(UTC)


ProviderFactory = Callable[[AppConfig], Provider]

DEFAULT_PROVIDERS: dict[str, ProviderFactory] = {
    "anthropic": lambda cfg: AnthropicProvider(cfg.env.anthropic_api_key),
    "gemini": lambda cfg: GeminiProvider(cfg.env.gemini_api_key),
}


class LLMClient:
    """Resolves tiers, renders prompts, caches, guards the budget, validates, repairs once.

    `ledger=None` disables cache, ledger and budget guard (unit tests only);
    `default_client()` always uses the Postgres ledger.
    """

    def __init__(
        self,
        config: AppConfig | None = None,
        providers: Mapping[str, Provider] | None = None,
        prompts_dir: Path | None = None,
        ledger: SqlLedger | None = None,
        now: Callable[[], datetime] = _utc_now,
    ) -> None:
        self.config = config or load_config()
        self.prompts_dir = prompts_dir
        self.ledger = ledger
        self.now = now
        self._providers: dict[str, Provider] = dict(providers or {})

    def provider(self, name: str) -> Provider:
        if name not in self._providers:
            self._providers[name] = DEFAULT_PROVIDERS[name](self.config)
        return self._providers[name]

    def tier(self, tier: str) -> ModelTier:
        try:
            return self.config.models.tiers[tier]  # type: ignore[index]
        except KeyError as e:
            raise ValueError(f"unknown tier {tier!r}") from e

    def _check_budget(self, tier_name: str, tier: ModelTier, request: ProviderRequest) -> None:
        """Raise BudgetExceeded if the worst-case cost of `request` would exceed a budget."""
        if self.ledger is None:
            return
        est_input = math.ceil((len(request.system) + len(request.user)) / CHARS_PER_TOKEN_ESTIMATE)
        worst_case = tier.cost_usd(est_input, request.max_output_tokens)
        day_start = self.now().astimezone(UTC).replace(hour=0, minute=0, second=0, microsecond=0)
        daily = self.config.daily_llm_budget_usd
        spent = self.ledger.spent_since(day_start)
        if spent + worst_case > daily:
            raise BudgetExceeded(
                f"daily LLM budget ${daily:.2f}: spent ${spent:.4f}, "
                f"next call may cost up to ${worst_case:.4f}"
            )
        triage_cap = self.config.models.budgets.triage_daily_usd
        if tier_name == "triage" and triage_cap is not None:
            spent_triage = self.ledger.spent_since(day_start, tier="triage")
            if spent_triage + worst_case > triage_cap:
                raise BudgetExceeded(
                    f"triage budget ${triage_cap:.2f}: spent ${spent_triage:.4f}, "
                    f"next call may cost up to ${worst_case:.4f}"
                )

    def call_with_meta[T: BaseModel](
        self, prompt_id: str, schema: type[T], inputs: Mapping[str, Any], tier: str
    ) -> CallResult[T]:
        model_tier = self.tier(tier)
        prompt = load_prompt(prompt_id, self.prompts_dir)
        json_schema = schema.model_json_schema()
        schema_ver = schema_version(schema)
        input_sha = sha256_json(dict(inputs))
        key = cache_key(input_sha, prompt.sha256, model_tier.model, schema_ver)
        started_at = self.now()

        def record(**kw: Any) -> None:
            if self.ledger is None:
                return
            base: dict[str, Any] = {
                "provider": model_tier.provider,
                "model": model_tier.model,
                "model_cutoff": model_tier.training_cutoff,
                "tier": tier,
                "prompt_id": prompt_id,
                "prompt_hash": prompt.sha256,
                "schema_version": schema_ver,
                "cache_key": key,
                "started_at": started_at,
                "input_tokens": 0,
                "output_tokens": 0,
                "cost_usd": 0.0,
                "cache_hit": False,
                "attempts": 0,
                "ok": True,
            }
            self.ledger.record(CallRecord(**(base | kw)))

        if self.ledger is not None:
            cached = self.ledger.get_cached(key)
            if cached is not None:
                hit = _validate(schema, json.dumps(cached))
                if not isinstance(hit, str):
                    record(cache_hit=True)
                    return CallResult(
                        output=hit,
                        prompt=prompt,
                        tier_name=tier,
                        tier=model_tier,
                        cache_key=key,
                        cache_hit=True,
                        cost_usd=0.0,
                    )

        system = load_prompt(SYSTEM_PROMPT_ID, self.prompts_dir).render(
            {"schema": json.dumps(json_schema, indent=2, sort_keys=True)}
        )
        request = ProviderRequest(
            model=model_tier.model,
            system=system,
            user=prompt.render(inputs),
            json_schema=json_schema,
            max_output_tokens=model_tier.max_output_tokens,
        )
        provider = self.provider(model_tier.provider)
        attempts: list[Attempt] = []

        def totals() -> dict[str, Any]:
            tin = sum(a.response.input_tokens for a in attempts)
            tout = sum(a.response.output_tokens for a in attempts)
            return {
                "input_tokens": tin,
                "output_tokens": tout,
                "cost_usd": model_tier.cost_usd(tin, tout),
                "attempts": len(attempts),
            }

        try:
            self._check_budget(tier, model_tier, request)
            response = provider.complete(request)
            result = _validate(schema, response.text)
            attempts.append(Attempt(request, response, result if isinstance(result, str) else None))

            if isinstance(result, str):
                repair = load_prompt(REPAIR_PROMPT_ID, self.prompts_dir).render(
                    {"error": result, "previous": response.text}
                )
                repair_request = ProviderRequest(
                    model=request.model,
                    system=request.system,
                    user=f"{request.user}\n\n{repair}",
                    json_schema=json_schema,
                    max_output_tokens=request.max_output_tokens,
                )
                self._check_budget(tier, model_tier, repair_request)
                response = provider.complete(repair_request)
                result = _validate(schema, response.text)
                attempts.append(
                    Attempt(repair_request, response, result if isinstance(result, str) else None)
                )
                if isinstance(result, str):
                    raise SchemaError(
                        f"{prompt_id} on tier {tier}: output invalid after repair retry: {result}"
                    )
        except Exception as e:
            record(ok=False, error=f"{type(e).__name__}: {e}"[:2000], **totals())
            raise

        t = totals()
        if self.ledger is not None:
            self.ledger.put_cache(
                CacheEntry(
                    cache_key=key,
                    input_sha256=input_sha,
                    prompt_hash=prompt.sha256,
                    model=model_tier.model,
                    schema_version=schema_ver,
                    output_json=result.model_dump(mode="json"),
                    created_at=self.now(),
                )
            )
        record(**t)
        return CallResult(
            output=result,
            prompt=prompt,
            tier_name=tier,
            tier=model_tier,
            cache_key=key,
            cache_hit=False,
            cost_usd=t["cost_usd"],
            attempts=attempts,
        )

    def call[T: BaseModel](
        self, prompt_id: str, schema: type[T], inputs: Mapping[str, Any], tier: str
    ) -> T:
        return self.call_with_meta(prompt_id, schema, inputs, tier).output


_default: LLMClient | None = None


def default_client() -> LLMClient:
    """Process-wide client with the Postgres cache, ledger and budget guard."""
    global _default
    if _default is None:
        from rlg.store.db import make_engine

        _default = LLMClient(ledger=SqlLedger(make_engine()))
    return _default


def call[T: BaseModel](prompt_id: str, schema: type[T], inputs: Mapping[str, Any], tier: str) -> T:
    """Module-level entry point: `rlg.llm.call(prompt_id, schema, inputs, tier)`."""
    return default_client().call(prompt_id, schema, inputs, tier)
