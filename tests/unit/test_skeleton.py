"""P0-01: package layout, CLI and slice-1 config files."""

import importlib
from pathlib import Path

import yaml
from typer.testing import CliRunner

import rlg
from rlg.cli import app

ROOT = Path(__file__).resolve().parents[2]

MODULES = [
    "config", "llm", "queue", "ingest", "triage", "parse", "extract", "verify",
    "er", "store", "serve", "analytics", "eval", "plan", "execute",
]  # fmt: skip

EDGE_TYPES = {
    "extends", "combines", "replaces_component", "refutes_or_contradicts",
    "transplants_domain", "evaluates_on", "uses_artifact", "compares_against",
    "introduces", "implements", "variant_of", "subset_of", "cites",
}  # fmt: skip

COMPONENTS = {
    "planner", "memory", "tool_interface", "action_space", "critic_verifier",
    "environment", "orchestration", "training_signal", "prompting", "other",
}  # fmt: skip


def test_all_stage_modules_import() -> None:
    for name in MODULES:
        importlib.import_module(f"rlg.{name}")


def test_cli_version() -> None:
    result = CliRunner().invoke(app, ["version"])
    assert result.exit_code == 0
    assert result.stdout.strip() == rlg.__version__


def test_anchors_yaml_is_consistent() -> None:
    data = yaml.safe_load((ROOT / "config" / "anchors.yaml").read_text())
    anchors = data["anchors"]
    ids = [a["id"] for a in anchors]
    assert len(ids) == len(set(ids)), "duplicate anchor ids"
    known = set(ids)
    for a in anchors:
        assert a["kind"] in {"paper", "artifact"}
        assert a["title"]
        if a["kind"] == "paper":
            assert a.get("arxiv_id") or a.get("url"), a["id"]
        else:
            assert a.get("url"), a["id"]
        for link in a.get("predecessors", []):
            assert link["anchor"] in known, f"{a['id']} -> unknown {link['anchor']}"
            assert link["type"] in EDGE_TYPES, link
            if link.get("component") is not None:
                assert link["component"] in COMPONENTS, link


def test_stub_configs_parse() -> None:
    for name in ["seed_concepts.yaml", "artifacts.yaml", "web_sources.yaml"]:
        assert isinstance(yaml.safe_load((ROOT / "config" / name).read_text()), dict)
