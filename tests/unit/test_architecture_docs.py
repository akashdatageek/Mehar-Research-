"""Architecture docs list every public name and the tables each module writes."""

import importlib
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]

DOCS = {
    "llm": ("llm.md", ["llm_call", "llm_cache"]),
    "queue": ("queue.md", ["job"]),
}


@pytest.mark.parametrize("module", sorted(DOCS))
def test_doc_lists_public_names_and_tables(module: str) -> None:
    doc_name, tables = DOCS[module]
    doc = (ROOT / "docs" / "architecture" / doc_name).read_text()
    mod = importlib.import_module(f"rlg.{module}")
    missing = [name for name in mod.__all__ if f"`{name}" not in doc]
    assert not missing, f"{doc_name} does not mention: {missing}"
    for table in tables:
        assert f"`{table}`" in doc
    for heading in ("## Purpose", "## Classes and functions", "## Prompts used",
                    "## Data read and written", "## Deterministic vs LLM decisions",
                    "## Failure modes", "```mermaid"):  # fmt: skip
        assert heading in doc
