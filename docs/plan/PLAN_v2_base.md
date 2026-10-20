> **Reference only.** The primary spec is `PLAN.md` (v3.1). Use this file only where v3.1 is silent: the full data model, the stack, and the detail for Steps 7–12. Where they conflict, v3.1 wins.

# Research-Lineage Graph — Build Plan (v2, after second-pass review)

Slice 1: **AI agents + harnesses / tools / skills** (2022 → today).
Philosophy: **LLM proposes, deterministic code disposes.** LLM output only ever lands in `candidate_*` tables; deterministic verifiers promote it.

This file is the single source of truth for Claude Code. `CLAUDE.md` holds repo rules, `feature_list.json` holds the ordered, testable features, `KICKOFF.md` holds the prompts to start each session.

---

## 0. What changed in the second pass

| # | First-pass assumption | Problem found | Revision |
|---|---|---|---|
| 1 | Full stack from day one (Postgres, MinIO, GROBID, Dagster, Argilla, MLflow, MinerU) | Runs on a laptop; too many services for a solo builder; MinerU needs a GPU; Argilla v2 needs Elasticsearch | **Lean core:** Postgres 17 + pgvector in Docker, content-addressed blobs on local disk, a Postgres job queue + CLI + cron. GROBID added in P3, MLflow (file backend) in P11. Built-in review UI replaces Argilla. MinerU optional. Dagster only if the queue proves insufficient (decision point after P6). |
| 2 | One LLM vendor implied | Mehar has a Claude API key and is considering Gemini | **Provider-agnostic LLM layer** with tiers in `config/models.yaml` (triage / extract / adjudicate). Every call logs provider, model, training cutoff, prompt hash, tokens, cost. |
| 3 | 150-paper, double-annotated gold set | One human annotator | **100-paper gold set** (60 dev / 40 held-out). Agreement measured by self re-annotation of 20 papers ≥10 days later, plus a strong model as second annotator to surface disagreements (never as ground truth). |
| 4 | Claude Code builds everything end to end | Gold labels, schema freeze and thresholds need a human | **Human gates** (H1–H4) where Claude Code stops, writes `GATE.md`, and waits. |
| 5 | Lineage extracted only from papers | Harness/skills lineage lives in repos, specs, blogs with no citations | **Artifact extractor:** deterministic edges from dependency files, explicit links and README acknowledgements; LLM edges from blog/spec text with the same span-grounding rule. |
| 6 | Node granularity undecided | Blocks schema | **Three node kinds:** `paper`, `artifact` (repo / model / spec / blog / docs), `concept` (method, task, benchmark, dataset, metric, harness, tool_protocol, skill_format). `paper/artifact —introduces→ concept`, `artifact —implements→ concept`. |
| 7 | 8 delta types, sub-types TBD | Too coarse for agents | Keep the 8 types; add a **`component` enum** for agent systems: `planner, memory, tool_interface, action_space, critic_verifier, environment, orchestration, training_signal, prompting, other`. Schema v1 frozen at gate H1 after a 30-paper pilot. |
| 8 | Time-split eval with extractor cutoff < T | No strong model has a cutoff old enough; generator leakage is the real threat | Two tracks: **retrospective** (freeze at T, with a leakage probe that asks the generator to recall post-T papers and reports results stratified) and **prospective** (predictions hashed and timestamped now, scored against papers that appear 3–6 months later). Prospective is the headline metric. |
| 9 | No query surface until planning | Mehar and Amoeba need to use the graph early | New **P7: graph API + MCP server + read-only "field map" UI**, right after the graph exists. |
| 10 | Code is the only output | Mehar does not read implementation files | Every phase ends with a generated **`docs/architecture/<module>.md`**: classes, prompts (by file), logic, data written. Prompts live in `prompts/` as versioned files, never inline. |
| 11 | Amoeba interface TBD | Amoeba agents use a contract (role, helper) and a log checker | Planning exports **Amoeba task spec + team spec** where each persona maps to an Amoeba contract and each team carries the expected tools/skills for the checker. |
| 12 | Cost unknown | Budget risk | P4 measures tokens/paper on 20 fixtures and writes `docs/cost_model.md`; a hard daily budget is enforced in code. Planning estimate: backfill of ~3k deep reads in the low hundreds of USD with batch APIs; daily run a few USD. **Treat as an assumption until measured.** |
| 13 | Graph DB projection optional | Adds ops for no v1 benefit | **No graph DB in v1.** Analytics load snapshots into igraph in memory. RDF/CiTO export is a stretch feature. |
| 14 | Licensing noted only | arXiv licenses vary | Full text and blobs stay local and private; anything exported or shown in the UI is spans ≤ 2 sentences plus links. |
| 15 | No backups | Laptop | Nightly `pg_dump` to the blob dir plus an off-machine copy (manual). |

---

## 1. Architecture

```
SOURCES  arXiv OAI-PMH/API · arXiv e-print (LaTeX) · OpenAlex · Semantic Scholar
         · GitHub · Hugging Face · curated blogs/specs list
   │
P1 INGEST     raw_document (immutable, sha256, fetched_at) · paper/paper_version · external_id
   │
P2 TRIAGE     T0 rules → T1 SPECTER2 + logistic regression → T2 small LLM (borderline only)
   │          route: ignore | metadata_only | deep_read   (daily deep-read cap)
P3 PARSE      LaTeX → CanonicalDoc{text, sections, citations, tables, offsets}
   │          fallback: GROBID (refs/citation contexts) + Marker (body)
P4 EXTRACT    LLM, JSON-schema output → candidate_claim / candidate_edge / candidate_result
   │          every item carries evidence {doc_version_id, span_start, span_end, quote}
P5 VERIFY     span match → citation adjacency → NLI → LLM adjudication (uncertain band) → review UI
   │  + ER    block → embed → score → curated alias table → reversible merges
P6 STORE      bitemporal edges (valid_from/valid_to, recorded_at/superseded_at), provenance,
   │          results, evidence, pgvector; freeze(T, R) API; nightly backup
P7 SERVE      FastAPI graph API · MCP server (for Amoeba / Claude) · read-only field-map UI
P8 ANALYTICS  families (Leiden) · topics (BERTopic) · bursts (Kleinberg) · main paths ·
   │          frontier · SOTA & saturation · contradictions · gaps (link prediction) · transplants
P9 EVAL       retrospective time-split + leakage probe · prospective prediction ledger ·
   │          graph completion · extraction/ER quality
P10 PLAN      seeds → typed-delta proposals → deterministic novelty gate → debate + Elo (pruning only)
   │          → lineage personas → Amoeba task/team spec
P11 EXECUTE   Docker sandbox · pre-registered protocol (immutable) · separate grader ·
              MLflow · write-back with provenance=agent (excluded from eval by default)
P12 ABLATIONS flat RAG vs typed graph · role vs lineage personas · write-back on/off · novelty gate on/off
```

### Stack
Python 3.12, uv, Pydantic v2, SQLAlchemy 2 + Alembic, Postgres 17 + pgvector ≥ 0.8.7 (Docker), Typer CLI, FastAPI (+ HTMX/Jinja for review and field-map UIs), sentence-transformers (SPECTER2, NLI cross-encoder base size for CPU), scikit-learn / LightGBM, igraph + leidenalg, BERTopic, GROBID (Docker, P3), Marker (P3), official MCP Python SDK (P7), MLflow file backend (P11), pytest + hypothesis, ruff, mypy, OpenTelemetry-lite logging to JSONL.

### Core data model (v1, finalized at gate H1)

```
paper(id, arxiv_id, doi, title, first_published_at, primary_category, triage_route, ...)
paper_version(id, paper_id, version, published_at, raw_document_id)
artifact(id, kind[repo|model|spec|blog|docs], canonical_url, title, first_seen_at)
artifact_version(id, artifact_id, fetched_at, content_sha256, raw_document_id)
raw_document(id, source, uri, fetched_at, content_sha256, blob_path, license)
external_id(entity_kind, entity_id, scheme[arxiv|doi|openalex|s2|github|hf], value)

concept(id, kind[method|task|benchmark|dataset|metric|harness|tool_protocol|skill_format],
        canonical_name, definition, created_recorded_at)
concept_alias(concept_id, alias, source[curated|er], recorded_at)
merge_event(id, kept_id, merged_id, reason, recorded_at, reverted_at)

edge(id, src_kind, src_id, dst_kind, dst_id,
     type[extends|combines|replaces_component|refutes_or_contradicts|transplants_domain|
          evaluates_on|uses_artifact|compares_against|introduces|implements|variant_of|subset_of|cites],
     component (enum, nullable), delta_summary,
     valid_from, valid_to, recorded_at, superseded_at,
     status[candidate|verified|rejected], confidence, verifier_version,
     provenance[extracted|human|agent|imported|deterministic], run_id)
evidence(id, owner_kind, owner_id, doc_version_kind, doc_version_id,
         span_start, span_end, quote, quote_sha256)

result(id, method_concept_id, benchmark_concept_id, split, metric, value, setting_json,
       harness_concept_id, reported_in_kind, reported_in_id, valid_from, recorded_at,
       provenance, status)

llm_call(id, provider, model, model_cutoff, prompt_id, prompt_hash, schema_version,
         input_tokens, output_tokens, cost_usd, cache_hit, started_at, ok)
job(id, kind, payload_json, status, attempts, run_after, locked_at)   -- SKIP LOCKED queue
review_item(id, owner_kind, owner_id, reason, assigned_label, labeled_at)
prediction(id, created_at, sha256, payload_json, horizon_until, scored_at, score_json)
analytics_snapshot(id, snapshot_T, snapshot_R, kind, payload_json, code_version)
```

**Invariants (enforced by tests):**
1. No `verified` edge or result without ≥1 evidence row whose quote is an exact (whitespace-normalized) substring of the stored canonical text at its offsets, except `provenance=deterministic` (e.g. dependency file parsing, which stores file path + line).
2. `freeze(T)` never returns rows with `valid_from > T`; `freeze(T, R)` never returns rows with `recorded_at > R`.
3. Agent-provenance rows are excluded from analytics and eval unless explicitly requested.
4. Merges are reversible; reverting restores prior edge endpoints.
5. Identical `(content_sha, prompt_hash, model)` never triggers a second paid call.

---

## 2. Phases

Each phase: **spec → build features in order → acceptance tests green → architecture doc → commit tag `pN-done`.** Human gates stop the run.

### P0 — Scaffold & harness
- Repo layout per `CLAUDE.md`; `docker-compose.yml` (Postgres + pgvector only); `.env.example`; `make up/test/lint`.
- `llm/` provider-agnostic client: Anthropic + Gemini adapters, tiered by `config/models.yaml`; schema-validated JSON output with one repair retry; content-hash cache; cost ledger (`llm_call`); daily budget guard that refuses calls over budget.
- `prompts/` loader (prompt_id → file, hash recorded).
- Postgres job queue with `SKIP LOCKED`, retries, backoff.
- Fixture downloader: 20 papers (LaTeX + PDF) from the anchor list into `tests/fixtures/`.
- **Accept:** `make up && make test` green; invalid JSON rejected; repeat call is a cache hit with zero cost; budget guard blocks over-budget calls; queue survives a worker crash (test).

### P1 — Registry & ingestion
- arXiv OAI-PMH harvester (sets cs, stat.ML) for a date range; arXiv API for same-day listings; version handling.
- OpenAlex (keyed) and Semantic Scholar (keyed, 1 RPS) enrichment: IDs, references, citation contexts and intents where present.
- GitHub + HF fetchers for a curated `config/artifacts.yaml`; blog/spec fetcher for `config/web_sources.yaml`; all snapshots hashed and versioned.
- Dedup: arXiv base ID; cross-source via `external_id`; fallback title+first-author+year then MinHash; collisions → review queue.
- **Accept:** re-harvesting a day inserts 0 rows; 50 known papers resolve to one paper each across arXiv/DOI/OpenAlex/S2; rate limiters verified with a fake clock; a changed README creates a new `artifact_version`, not a new artifact.

### P2 — Triage
- T0 rules (categories + keyword allow-list in config).
- Bootstrap labels: positives = anchor papers + papers citing ≥2 anchors; negatives = random cs sample; T2 LLM labels 600 abstracts; **Mehar spot-checks 150** in the review UI (gate H0, light).
- T1: SPECTER2 embeddings → logistic regression + kNN-to-anchor feature; threshold tuned for recall.
- T2: small-tier LLM on the uncertain band only; deterministic final routing; daily deep-read cap with priority queue.
- **Accept:** on held-out labels recall ≥ 0.95 for deep_read-worthy, precision ≥ 0.6; one simulated day of ~1,300 abstracts completes under the triage budget.

### P3 — Parsing
- LaTeX parser: multi-file resolution, macro stripping, section tree, bibliography + `\cite` key resolution, citation sentences, tables to structured cells, char-offset map to canonical text.
- Fallbacks: GROBID (Docker) for references/citation contexts; Marker for body text when no source.
- Spike: measure share of slice papers with usable LaTeX → `docs/parsing_report.md`.
- **Accept:** on 20 fixtures ≥ 95% of cite occurrences resolved, ≥ 90% of tables extracted, offsets round-trip (property test), fallback path exercised on ≥ 3 PDF-only fixtures.

### P4 — Extraction, review UI, gold set
- Pass A paper card; pass B delta edges (+component); pass C result rows (LaTeX tables, harness/attempt budget in `setting_json`); artifact extractor (deterministic dependency/link edges + LLM on blog/spec text).
- Review UI (FastAPI + HTMX): queue, evidence highlighted in context, accept / reject / relabel / edit, keyboard shortcuts, export.
- Cost model from 20 fixtures → `docs/cost_model.md`.
- **Gate H1:** Mehar annotates a 30-paper pilot; Claude Code proposes schema/taxonomy adjustments from disagreements; Mehar freezes **schema v1**.
- **Gate H2:** Mehar annotates the 100-paper gold set (60 dev / 40 held-out, held-out is read-only to agents).
- **Accept:** schema-valid ≥ 99%; ≥ 95% of quotes span-exact; per-type P/R report on the dev split.

### P5 — Verification & entity resolution
- Verification ladder: span match → citation adjacency (else downgrade to `cites`) → NLI with per-type calibrated thresholds → LLM adjudication for the uncertain band and every `refutes_or_contradicts` → review queue with daily stratified sample.
- ER: Splink for papers/authors/repos; concepts via blocking + embeddings + LLM `same|variant_of|different` adjudication; auto-merge only on curated alias hits; `variant_of/subset_of` become edges; reversible merges.
- Seed ~300 canonical concepts from `config/seed_concepts.yaml`.
- **Gate H3:** verified-edge precision ≥ 0.85 on held-out; ER false-merge ≤ 2%. If missed, Claude Code writes a failure analysis and stops.

### P6 — Bitemporal graph & backfill
- Canonical tables, promotion from candidate tables, `freeze(T, R)` SQL views + Python API, provenance filters, nightly backup.
- Backfill run of the slice (batch APIs), resumable, budget-capped; daily incremental job wired to cron.
- **Accept:** freeze property tests; anchor lineages in `config/anchors.yaml` appear as paths in `freeze(2025-12-31)` for ≥ 70% of listed links; backfill resumes after a kill with no duplicate paid calls.

### P7 — Serve: API, MCP, field map
- FastAPI: entity lookup, neighbors by edge type, lineage path between two concepts, results by benchmark, `as_of` parameter on every endpoint.
- MCP server exposing the same as tools (read-only) for Amoeba / Claude.
- Field-map UI: family view, concept page (lineage up/down with evidence quotes), benchmark page (SOTA curve).
- **Accept:** API contract tests; MCP tools callable from a test client; every UI claim links to its evidence.

### P8 — Field-state analytics
- Leiden families (weighted typed edges + coupling + kNN), identity tracking across snapshots; BERTopic dynamic topics; Kleinberg bursts; main-path (SPC) on extends/replaces/combines; frontier rule; SOTA trajectory + saturation per (benchmark, split, metric, harness class); contradiction clusters; gap link prediction (heuristic features + LightGBM baseline); transplant detector.
- All outputs written to `analytics_snapshot` keyed by T.
- **Accept:** main path recovers ≥ 70% of anchor links; SOTA values match hand-checked samples in `tests/fixtures/sota_checks.yaml`; deterministic rerun reproduces identical snapshot.

### P9 — Evaluation harness
- Retrospective: freeze at T (default 2025-06-30), generate edges/ideas, match to post-T papers (SPECTER2 similarity + typed-edge match), graph completion hit@k; leakage probe; results stratified by probe outcome.
- Prospective ledger: predictions hashed and timestamped (`prediction` table + append-only JSONL), scorer runs monthly.
- Extraction / ER quality report on the held-out split.
- **Accept:** end-to-end retrospective run produces `reports/eval_<date>.md`; ledger entries are tamper-evident (hash chain test).

### P10 — Planning → Amoeba
- **Gate H4:** Mehar confirms the Amoeba task/team spec format (Claude Code drafts it from Amoeba's contract model: role, helper, expected tools/skills for the checker).
- Seed selection (deterministic) → proposals as typed-delta tuples with hypothesis, predicted delta, falsification criterion → **novelty gate** (exact tuple match, near-duplicate embedding, recency/scoop flag, all bases verified) → debate + Elo for pruning only → lineage personas (concept cluster + key evidence + known failure modes + tools) → export spec.
- **Accept:** novelty gate rejects 100% of a planted set of published deltas; Elo bookkeeping unit-tested; exported spec validates against the agreed JSON schema.

### P11 — Execution & write-back
- Docker sandbox (no network by default, quotas); pre-registration row frozen before run; separate grader process with read-only access; MLflow file backend; write-back with `provenance=agent`, interpretive edges stay `candidate`.
- **Accept:** agent cannot alter a pre-registered protocol (test); negative results stored; analytics/eval exclude agent rows by default.

### P12 — Ablations & report
- Flat RAG (and a GraphRAG/LightRAG baseline) vs typed graph; role vs lineage personas; write-back on/off; novelty gate on/off; same budget, same eval.
- **Accept:** `reports/ablations.md` with confidence intervals.

---

## 3. Human gates (Claude Code stops and waits)

| Gate | When | Mehar does | Time estimate |
|---|---|---|---|
| H0 | P2 | Spot-check 150 triage labels | ~1 h |
| H1 | P4 | Annotate 30-paper pilot, freeze schema v1 | ~4–6 h |
| H2 | P4 | Annotate 100-paper gold set | ~10–15 h, can run in parallel with P5 coding |
| H3 | P5 | Accept precision/ER results or request changes | ~30 min |
| H4 | P10 | Approve Amoeba spec format | ~30 min |

At a gate Claude Code writes `GATE.md` (what is needed, where, how to resume) and ends the session.

---

## 4. Risks & how the plan handles them

- **Eval leakage** → prospective ledger as headline; leakage probe; stratified reporting.
- **Hallucinated edges** → span-exact rule + NLI + held-out precision gate.
- **Entity drift** → curated alias table, reversible merges, ER false-merge gate.
- **Harness confounds in benchmarks** → no SOTA point without `setting_json`.
- **Silent blog/doc edits** → versioned, hashed snapshots.
- **Cost overrun** → measured cost model, daily budget guard, cache, batch APIs.
- **Agent going off-plan** → one feature per session, tests are immutable, gates, JSON feature list.
- **Herding toward the frontier** → planner reserves a share of seeds for low-attention branches and transplants (config `seed_mix`).

## 5. Open decisions left on purpose
1. Gemini vs Claude per tier (set in config after the P4 cost model).
2. Dagster adoption (decide after P6 if the cron + queue setup hurts).
3. Second slice (SLMs or VLMs) after P9.
