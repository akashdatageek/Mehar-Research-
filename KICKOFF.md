# KICKOFF — fresh start with the researched plan (v3.1)

## What's in this repo
- `PLAN.md`: primary spec (v3.1, researched and audited).
- `docs/plan/PLAN_v2_base.md`: data model, stack and Steps 7–12 detail, used where v3.1 is silent.
- `docs/research/`: the research reports behind Steps 4–6, plus the audit.
- `CLAUDE.md`: rules and session protocol.
- `feature_list.json`: 82 ordered features, all `passes: false`.

The earlier build is archived on the branch `archive/v2-build-2026-10-20` (reference only).

## Setup (once)
1. Add these to the cloud environment's variables, not to chat:
   - `ANTHROPIC_API_KEY` (optional)
   - `GEMINI_API_KEY` (a new key)
   - `OPENALEX_API_KEY`
   - `S2_API_KEY`
   - `GITHUB_TOKEN`
   - `HF_TOKEN`
   - `ARXIV_CONTACT_EMAIL`
   - `DAILY_LLM_BUDGET_USD`
2. Network allow-list:
   - arxiv.org, export.arxiv.org, ar5iv.labs.arxiv.org
   - api.openalex.org, api.semanticscholar.org
   - api.github.com, raw.githubusercontent.com, huggingface.co
   - generativelanguage.googleapis.com, api.anthropic.com
3. Docker must be available. If its service is down, start it.

## Session 1 prompt (initializer)
```
You are building the system specified in PLAN.md (v3.1). Read CLAUDE.md, PLAN.md, docs/plan/PLAN_v2_base.md and feature_list.json fully, and skim docs/research/.
This is the initializer session for a fresh start:
- Create init.sh (starts Docker services, installs deps, runs migrations) and claude-progress.txt (note the fresh start and the archive branch).
- Create config/anchors.yaml with the slice-1 anchor lineages (paper title, arXiv id, predecessor links), and verify each arXiv id against the arXiv API.
- Create config/niche.yaml as described in PLAN.md Step 2 (definition, ~40 in-anchors, 20–30 near-miss out examples).
- Stub config/seed_concepts.yaml, artifacts.yaml and web_sources.yaml.
- Then implement P0-01 only, following the session protocol in CLAUDE.md. Commit when done.
Do not edit feature_list.json except the passes field.
```

## Every later session
```
Continue the build. Follow the session protocol in CLAUDE.md exactly:
read claude-progress.txt, git log and feature_list.json; run ./init.sh and make test;
read the PLAN.md section (and docs/research report, if any) for the current phase;
then implement the next eligible feature only. Stop at any gate and write GATE.md.
```

## At a gate
Read `GATE.md` and do the human step. Then add `RESOLVED: <date> <notes>` at the top of `GATE.md` and start the next session with the same prompt.

## Start early, in parallel
The gold set (Gate H2) is about 25–35 hours of labelling. Begin as soon as the review page exists (P4-06).
