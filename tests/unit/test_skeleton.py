"""P0-01 skeleton checks: package layout, CLI, and structure of the hand-written config files."""

import importlib
import re
from pathlib import Path
from typing import Any

import pytest
import yaml
from typer.testing import CliRunner

from rlg import __version__
from rlg.cli import app

ROOT = Path(__file__).resolve().parents[2]
CONFIG = ROOT / "config"

MODULES = [
    "config", "llm", "queue", "ingest", "triage", "parse", "extract", "verify",
    "er", "store", "serve", "analytics", "eval", "plan", "execute",
]  # fmt: skip

# Enums from PLAN.md Step 4 and PLAN_v2_base.md data model.
EDGE_TYPES = {
    "extends", "combines", "replaces_component", "refutes_or_contradicts", "transplants_domain",
    "evaluates_on", "uses_artifact", "compares_against", "introduces", "implements",
    "variant_of", "subset_of", "cites",
}  # fmt: skip
COMPONENTS = {
    "planner", "memory", "tool_interface", "action_space", "critic_verifier", "environment",
    "orchestration", "training_signal", "prompting", "other",
}  # fmt: skip
ARXIV_ID = re.compile(r"^\d{4}\.\d{4,5}$")


def load(name: str) -> Any:
    return yaml.safe_load((CONFIG / name).read_text())


@pytest.mark.parametrize("module", MODULES)
def test_stage_modules_import(module: str) -> None:
    importlib.import_module(f"rlg.{module}")


def test_cli_version() -> None:
    result = CliRunner().invoke(app, ["version"])
    assert result.exit_code == 0
    assert result.output.strip() == __version__


def test_anchors_consistent() -> None:
    anchors = load("anchors.yaml")["anchors"]
    ids = [a["id"] for a in anchors]
    assert len(ids) == len(set(ids)), "duplicate anchor ids"
    by_id = {a["id"]: a for a in anchors}
    for a in anchors:
        assert a["kind"] in {"paper", "artifact"}
        if a["kind"] == "paper":
            assert ARXIV_ID.match(a["arxiv_id"]), a["id"]
        else:
            assert a["url"].startswith("https://"), a["id"]
        for p in a["predecessors"]:
            assert p["anchor"] in by_id, f"{a['id']} -> unknown {p['anchor']}"
            assert p["anchor"] != a["id"], "self-loop"
            assert p["type"] in EDGE_TYPES, p
            assert p.get("component", "other") in COMPONENTS, p
            assert by_id[p["anchor"]]["year"] <= a["year"], f"{a['id']} predates {p['anchor']}"
    arxiv_ids = [a["arxiv_id"] for a in anchors if a["kind"] == "paper"]
    assert len(arxiv_ids) == len(set(arxiv_ids)), "duplicate arxiv ids"


def test_anchors_mark_fixtures() -> None:
    anchors = load("anchors.yaml")["anchors"]
    fixtures = [a for a in anchors if a.get("fixture")]
    assert len(fixtures) == 20
    assert all(a["kind"] == "paper" for a in fixtures)
    pdf_only = [a for a in anchors if a.get("pdf_only")]
    assert len(pdf_only) >= 3
    assert all(a.get("fixture") for a in pdf_only)


def test_niche_shape() -> None:
    niche = load("niche.yaml")
    assert niche["definition"].strip()
    ins, outs = niche["in_anchors"], niche["near_miss_out"]
    assert 35 <= len(ins) <= 45
    assert 20 <= len(outs) <= 30
    in_ids = {x["arxiv_id"] for x in ins}
    out_ids = {x["arxiv_id"] for x in outs}
    assert len(in_ids) == len(ins) and len(out_ids) == len(outs), "duplicates"
    assert not in_ids & out_ids, "paper is both in and out"
    assert all(ARXIV_ID.match(i) for i in in_ids | out_ids)
    anchor_arxiv = {a["id"]: a.get("arxiv_id") for a in load("anchors.yaml")["anchors"]}
    for x in ins:
        if "anchor" in x:
            assert anchor_arxiv[x["anchor"]] == x["arxiv_id"], x
    assert all(x["why"] for x in outs)


@pytest.mark.parametrize(
    ("name", "key"),
    [("seed_concepts.yaml", "concepts"), ("artifacts.yaml", "artifacts"),
     ("web_sources.yaml", "sources")],
)  # fmt: skip
def test_stub_configs_parse(name: str, key: str) -> None:
    data = load(name)
    assert isinstance(data["version"], int)
    assert isinstance(data[key], list) and data[key]
