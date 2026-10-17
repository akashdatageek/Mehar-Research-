"""Test doubles shared across test suites."""

from collections.abc import Iterable

from rlg.llm.providers import ProviderRequest, ProviderResponse


class FakeProvider:
    """Returns scripted texts in order and records every request."""

    name = "anthropic"

    def __init__(self, texts: Iterable[str], input_tokens: int = 100, output_tokens: int = 20):
        self.texts = list(texts)
        self.requests: list[ProviderRequest] = []
        self.input_tokens = input_tokens
        self.output_tokens = output_tokens

    def complete(self, request: ProviderRequest) -> ProviderResponse:
        self.requests.append(request)
        if not self.texts:
            raise AssertionError("FakeProvider ran out of scripted responses")
        return ProviderResponse(
            text=self.texts.pop(0),
            input_tokens=self.input_tokens,
            output_tokens=self.output_tokens,
            model=request.model,
        )
