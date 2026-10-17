# KICKOFF — how to run this with Claude Code

## Setup (once)
1. Create an empty repo (e.g. `research-lineage-graph`) and copy in `PLAN.md`, `CLAUDE.md`, `feature_list.json`, `KICKOFF.md`.
2. Add `.env` with: `ANTHROPIC_API_KEY`, `GEMINI_API_KEY` (optional), `OPENALEX_API_KEY`, `S2_API_KEY`, `GITHUB_TOKEN`, `HF_TOKEN`, `ARXIV_CONTACT_EMAIL`, `DAILY_LLM_BUDGET_USD`.
3. Have Docker running.

## Session 1 prompt (initializer)
```
You are building the system specified in PLAN.md. Read PLAN.md, CLAUDE.md and feature_list.json fully.
This is the initializer session:
- Create init.sh (starts Docker services, installs deps, runs migrations) and claude-progress.txt.
- Create config/anchors.yaml with the slice-1 anchor lineages from PLAN.md (paper title, arXiv id when one exists, predecessor links), and stub config/seed_concepts.yaml, artifacts.yaml, web_sources.yaml.
- Then implement P0-01 only, following the session protocol in CLAUDE.md.
Do not edit feature_list.json except the passes field. Commit when done.
```

## Every later session
```
Continue the build. Follow the session protocol in CLAUDE.md exactly:
read claude-progress.txt, git log and feature_list.json; run ./init.sh and make test;
then implement the next eligible feature only. Stop at any gate and write GATE.md.
```
For long unattended runs, repeat this prompt in fresh sessions (or a loop script) until a gate is hit.

## At a gate
Read `GATE.md`, do the human step (the review UI runs at the URL it gives), then add `RESOLVED: <date> <notes>` to the top of `GATE.md` and start the next session with the same prompt.

## Review checkpoints for Mehar (no code reading needed)
- After each phase: `docs/architecture/<module>.md`
- P3: `docs/parsing_report.md` · P4: `docs/cost_model.md`, `reports/extraction_dev.md`
- P5: `reports/verify_heldout.md` · P9: `reports/eval_<date>.md` · P12: `reports/ablations.md`
