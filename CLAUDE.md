# CLAUDE.md — Research-Lineage Graph

Read this every session. `PLAN.md` is the spec; `feature_list.json` is the work queue; `claude-progress.txt` is the log.

## Session protocol
1. Read `claude-progress.txt`, `git log --oneline -20`, and `feature_list.json`.
2. If `GATE.md` exists and is not marked resolved, stop and tell the user what the gate needs.
3. Run `./init.sh` then `make test`. If anything that passed before now fails, fix that first.
4. Pick the **first** feature with `"passes": false` whose `depends_on` all pass. Work on that one only.
5. Implement, then run that feature's `test_steps` plus the full suite.
6. Only when all its steps pass: set `"passes": true`, append a dated entry to `claude-progress.txt` (what changed, files, open issues), commit `feat(<id>): <title>`.
7. At the end of a phase: write/update `docs/architecture/<module>.md`, tag `pN-done`.
8. If a feature has `"gate"`, write `GATE.md` and end the session.

## Hard rules
- Never edit or delete existing tests or `test_steps` to make them pass. Never edit `feature_list.json` except the `passes` field. If a feature is wrong, write the problem in `claude-progress.txt` and stop.
- Never write LLM output to canonical tables. LLM output goes to `candidate_*`; only `verify/` promotes.
- Every LLM call goes through `llm.call(prompt_id, schema, inputs, tier)`. No direct SDK calls elsewhere.
- Prompts live in `prompts/<prompt_id>.md`. No inline prompts.
- Never read or modify `data/gold/heldout/` from extraction, prompt-tuning or analytics code. Only `eval/` reads it.
- Secrets only from `.env`. Never commit `.env`, blobs, or `data/`.
- Full text and blobs stay local. UI/API expose at most 2-sentence quotes plus links.
- Respect rate limits: Semantic Scholar 1 RPS, OpenAlex keyed budget, arXiv polite (≥3 s between requests, user-agent with contact).
- Prefer simple: no new service or dependency without a note in `claude-progress.txt` explaining why.

## Layout
```
src/rlg/
  config/  llm/  queue/  ingest/  triage/  parse/  extract/  verify/  er/
  store/   serve/  analytics/  eval/  plan/  execute/  cli.py
prompts/            versioned prompt files
config/             models.yaml, sources, anchors.yaml, seed_concepts.yaml, artifacts.yaml, web_sources.yaml
migrations/         alembic
tests/  unit/ integration/ e2e/ fixtures/
data/   blobs/ gold/{dev,heldout}/ backups/        (gitignored)
docs/   architecture/ cost_model.md parsing_report.md
reports/
```

## Conventions
- Python 3.12, uv, ruff, mypy --strict on `src/`, Pydantic v2 models for every schema.
- SQL migrations via Alembic only.
- Tests: unit (no network, no DB), integration (Docker Postgres), e2e (fixtures, LLM calls mocked by recorded responses unless `RLG_LIVE=1`).
- Times are UTC, timezone-aware. `valid_*` = world time, `recorded_at/superseded_at` = pipeline time.
- CLI: `rlg <stage> <command>` (Typer). Every stage is idempotent and resumable.

## Architecture docs (for Mehar, who reads these instead of code)
For each module: purpose; classes and functions with one-line roles; which prompts it uses (by file); data read and written (tables); decisions made deterministically vs by LLM; failure modes. Keep diagrams in Mermaid.
