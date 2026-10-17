"""Provider adapters. Only this module talks to vendor SDKs (CLAUDE.md hard rule)."""

import copy
from dataclasses import dataclass
from typing import Any, Protocol


class ProviderError(RuntimeError):
    """The provider refused or failed in a way a retry with the same input will not fix."""


@dataclass(frozen=True)
class ProviderRequest:
    model: str
    system: str
    user: str
    json_schema: dict[str, Any]
    max_output_tokens: int


@dataclass(frozen=True)
class ProviderResponse:
    text: str
    input_tokens: int
    output_tokens: int
    model: str


class Provider(Protocol):
    """Anything that turns a ProviderRequest into raw JSON text plus token counts."""

    name: str

    def complete(self, request: ProviderRequest) -> ProviderResponse: ...


def closed_schema(schema: dict[str, Any]) -> dict[str, Any]:
    """Copy of `schema` with `additionalProperties: false` on every object (structured outputs)."""
    out = copy.deepcopy(schema)

    def walk(node: object) -> None:
        if isinstance(node, dict):
            if node.get("type") == "object" and "properties" in node:
                node.setdefault("additionalProperties", False)
            for v in node.values():
                walk(v)
        elif isinstance(node, list):
            for v in node:
                walk(v)

    walk(out)
    return out


class AnthropicProvider:
    """Claude via the Anthropic SDK with JSON-schema structured output."""

    name = "anthropic"

    def __init__(self, api_key: str | None = None) -> None:
        import anthropic

        self._client = anthropic.Anthropic(api_key=api_key) if api_key else anthropic.Anthropic()

    def complete(self, request: ProviderRequest) -> ProviderResponse:
        response = self._client.messages.create(
            model=request.model,
            max_tokens=request.max_output_tokens,
            system=request.system,
            messages=[{"role": "user", "content": request.user}],
            output_config={
                "format": {"type": "json_schema", "schema": closed_schema(request.json_schema)}
            },
        )
        if response.stop_reason == "refusal":
            raise ProviderError(f"{request.model} refused: {response.stop_details}")
        text = "".join(b.text for b in response.content if b.type == "text")
        return ProviderResponse(
            text=text,
            input_tokens=response.usage.input_tokens,
            output_tokens=response.usage.output_tokens,
            model=response.model,
        )


class GeminiProvider:
    """Gemini via the google-genai SDK with JSON response schema."""

    name = "gemini"

    def __init__(self, api_key: str | None = None) -> None:
        from google import genai

        self._client = genai.Client(api_key=api_key) if api_key else genai.Client()

    def complete(self, request: ProviderRequest) -> ProviderResponse:
        from google.genai import types

        response = self._client.models.generate_content(
            model=request.model,
            contents=request.user,
            config=types.GenerateContentConfig(
                system_instruction=request.system,
                response_mime_type="application/json",
                response_json_schema=request.json_schema,
                max_output_tokens=request.max_output_tokens,
            ),
        )
        usage = response.usage_metadata
        input_tokens = (usage.prompt_token_count or 0) if usage else 0
        output_tokens = (
            (usage.candidates_token_count or 0) + (usage.thoughts_token_count or 0) if usage else 0
        )
        return ProviderResponse(
            text=response.text or "",
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            model=request.model,
        )
