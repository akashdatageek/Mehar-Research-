"""Download the anchor fixture papers (LaTeX e-print + PDF) into tests/fixtures/papers/.

Downloaded files are gitignored (full text stays local); tests/fixtures/manifest.json
records each file's sha256 so every machine can verify it has the same bytes.
"""

import hashlib
import json
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from rlg.ingest.ratelimit import RateLimiter

REPO_ROOT = Path(__file__).resolve().parents[3]
FIXTURES_DIR = REPO_ROOT / "tests" / "fixtures"
ANCHORS = REPO_ROOT / "config" / "anchors.yaml"
ARXIV_MIN_INTERVAL_S = 3.0

HttpGet = Callable[[str, dict[str, str]], bytes | None]
"""(url, headers) -> body, or None for 404."""


@dataclass(frozen=True)
class FixtureSpec:
    anchor_id: str
    arxiv_id: str
    title: str
    pdf_only: bool


def fixture_specs(anchors_path: Path = ANCHORS) -> list[FixtureSpec]:
    """Anchors marked `fixture: true` that have an arXiv id."""
    data = yaml.safe_load(anchors_path.read_text())
    return [
        FixtureSpec(a["id"], str(a["arxiv_id"]), a["title"], bool(a.get("pdf_only", False)))
        for a in data["anchors"]
        if a.get("fixture") and a.get("arxiv_id")
    ]


def user_agent(contact_email: str) -> str:
    if not contact_email:
        raise ValueError("ARXIV_CONTACT_EMAIL must be set (arXiv asks for a contact)")
    return f"research-lineage-graph/0.1 (mailto:{contact_email})"


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def download_fixtures(
    http_get: HttpGet,
    contact_email: str,
    out_dir: Path = FIXTURES_DIR,
    anchors_path: Path = ANCHORS,
    limiter: RateLimiter | None = None,
) -> dict[str, Any]:
    """Fetch PDF (+ e-print unless pdf_only) for each fixture; write manifest.json. Resumable."""
    headers = {"User-Agent": user_agent(contact_email)}
    limiter = limiter or RateLimiter(ARXIV_MIN_INTERVAL_S)
    manifest_path = out_dir / "manifest.json"
    known_missing: set[tuple[str, str]] = set()
    if manifest_path.exists():  # resume: don't re-request files arXiv already said are missing
        for p in json.loads(manifest_path.read_text())["papers"]:
            have = {f["name"] for f in p["files"]}
            for name in ("paper.pdf", "source.tar.gz"):
                if name not in have and not (name == "source.tar.gz" and p["pdf_only"]):
                    known_missing.add((p["arxiv_id"], name))
    papers: list[dict[str, Any]] = []
    for spec in fixture_specs(anchors_path):
        pdir = out_dir / "papers" / spec.arxiv_id
        pdir.mkdir(parents=True, exist_ok=True)
        targets = [("paper.pdf", f"https://arxiv.org/pdf/{spec.arxiv_id}")]
        if not spec.pdf_only:
            targets.append(("source.tar.gz", f"https://arxiv.org/e-print/{spec.arxiv_id}"))
        files = []
        for name, url in targets:
            path = pdir / name
            if path.exists():
                data = path.read_bytes()
            elif (spec.arxiv_id, name) in known_missing:
                continue
            else:
                limiter.wait()
                body = http_get(url, headers)
                if body is None:
                    continue
                path.write_bytes(body)
                data = body
            files.append({"name": name, "url": url, "sha256": _sha256(data), "bytes": len(data)})
        papers.append(
            {
                "anchor_id": spec.anchor_id,
                "arxiv_id": spec.arxiv_id,
                "title": spec.title,
                "pdf_only": spec.pdf_only,
                "has_source": any(f["name"] == "source.tar.gz" for f in files),
                "files": files,
            }
        )
    manifest = {"version": 1, "papers": papers}
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n")
    return manifest


def verify_fixtures(out_dir: Path = FIXTURES_DIR) -> list[str]:
    """Problems found comparing files on disk with manifest.json (empty list = all good)."""
    manifest_path = out_dir / "manifest.json"
    if not manifest_path.exists():
        return [f"{manifest_path} missing; run `rlg fixtures download`"]
    problems = []
    for paper in json.loads(manifest_path.read_text())["papers"]:
        for f in paper["files"]:
            path = out_dir / "papers" / paper["arxiv_id"] / f["name"]
            if not path.exists():
                problems.append(f"{path} missing")
            elif _sha256(path.read_bytes()) != f["sha256"]:
                problems.append(f"{path} sha256 mismatch")
    return problems


def urllib_get(url: str, headers: dict[str, str]) -> bytes | None:
    """Real HTTP GET (used by the CLI)."""
    import urllib.error
    import urllib.request

    req = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            body: bytes = resp.read()
            return body
    except urllib.error.HTTPError as e:
        if e.code == 404:
            return None
        raise
