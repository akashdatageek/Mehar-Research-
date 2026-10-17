"""`llm.call(prompt_id, schema, inputs, tier)`: the only way pipeline code calls an LLM."""

import json
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ValidationError

from rlg.config import AppConfig, ModelTier, load_config
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
    """Validated output plus everything the ledger (P0-05) needs."""

    output: T
    prompt: Prompt
    tier_name: str
    tier: ModelTier
    attempts: list[Attempt] = field(default_factory=list)


def _validate[T: BaseModel](schema: type[T], text: str) -> T | str:
    """Validated object, or a readable error string."""
    try:
        return schema.model_validate_json(text)
    except ValidationError as e:
        return str(e)


ProviderFactory = Callable[[AppConfig], Provider]

DEFAULT_PROVIDERS: dict[str, ProviderFactory] = {
    "anthropic": lambda cfg: AnthropicProvider(cfg.env.anthropic_api_key),
    "gemini": lambda cfg: GeminiProvider(cfg.env.gemini_api_key),
}


class LLMClient:
    """Resolves tiers, renders prompts, calls the provider, validates, repairs once."""

    def __init__(
        self,
        config: AppConfig | None = None,
        providers: Mapping[str, Provider] | None = None,
        prompts_dir: Path | None = None,
    ) -> None:
        self.config = config or load_config()
        self.prompts_dir = prompts_dir
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

    def call_with_meta[T: BaseModel](
        self, prompt_id: str, schema: type[T], inputs: Mapping[str, Any], tier: str
    ) -> CallResult[T]:
        model_tier = self.tier(tier)
        provider = self.provider(model_tier.provider)
        prompt = load_prompt(prompt_id, self.prompts_dir)
        json_schema = schema.model_json_schema()
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
        attempts: list[Attempt] = []
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
            response = provider.complete(repair_request)
            result = _validate(schema, response.text)
            attempts.append(
                Attempt(repair_request, response, result if isinstance(result, str) else None)
            )
            if isinstance(result, str):
                raise SchemaError(
                    f"{prompt_id} on tier {tier}: output invalid after repair retry: {result}"
                )

        return CallResult(
            output=result, prompt=prompt, tier_name=tier, tier=model_tier, attempts=attempts
        )

    def call[T: BaseModel](
        self, prompt_id: str, schema: type[T], inputs: Mapping[str, Any], tier: str
    ) -> T:
        return self.call_with_meta(prompt_id, schema, inputs, tier).output


_default: LLMClient | None = None


def default_client() -> LLMClient:
    global _default
    if _default is None:
        _default = LLMClient()
    return _default


def call[T: BaseModel](prompt_id: str, schema: type[T], inputs: Mapping[str, Any], tier: str) -> T:
    """Module-level entry point: `rlg.llm.call(prompt_id, schema, inputs, tier)`."""
    return default_client().call(prompt_id, schema, inputs, tier)
