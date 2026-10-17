"""Prompt files: `prompts/<prompt_id>.md`, rendered with `{{name}}` placeholders and hashed."""

import hashlib
import json
import re
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

PROMPTS_DIR = Path(__file__).resolve().parents[3] / "prompts"
_PLACEHOLDER = re.compile(r"\{\{\s*([A-Za-z_][A-Za-z0-9_]*)\s*\}\}")
_PROMPT_ID = re.compile(r"^[A-Za-z0-9_][A-Za-z0-9_.-]*$")


class PromptError(ValueError):
    """Unknown prompt id, bad id, or missing template input."""


@dataclass(frozen=True)
class Prompt:
    """A loaded prompt file. `sha256` is the hash of the file bytes (the prompt_hash)."""

    id: str
    template: str
    sha256: str

    @property
    def placeholders(self) -> set[str]:
        return set(_PLACEHOLDER.findall(self.template))

    def render(self, inputs: Mapping[str, object]) -> str:
        """Fill `{{name}}` placeholders; non-string values are JSON-encoded."""
        missing = self.placeholders - set(inputs)
        if missing:
            raise PromptError(f"prompt {self.id!r} missing inputs: {', '.join(sorted(missing))}")

        def sub(m: re.Match[str]) -> str:
            value = inputs[m.group(1)]
            return value if isinstance(value, str) else json.dumps(value, sort_keys=True)

        return _PLACEHOLDER.sub(sub, self.template)


def load_prompt(prompt_id: str, prompts_dir: Path | None = None) -> Prompt:
    """Read `prompts/<prompt_id>.md` and hash it."""
    if not _PROMPT_ID.match(prompt_id):
        raise PromptError(f"invalid prompt id {prompt_id!r}")
    path = (prompts_dir or PROMPTS_DIR) / f"{prompt_id}.md"
    try:
        raw = path.read_bytes()
    except FileNotFoundError as e:
        raise PromptError(f"prompt {prompt_id!r} not found at {path}") from e
    return Prompt(
        id=prompt_id, template=raw.decode("utf-8"), sha256=hashlib.sha256(raw).hexdigest()
    )
