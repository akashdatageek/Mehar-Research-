# Research-Lineage Graph — Researched Build Plan (v3.1, audited)

**Project:** a living, typed research-lineage graph for **AI agents, harnesses, tools and skills** (2022 → today), feeding Amoeba's research planning.
**Principle:** *LLM proposes, deterministic code disposes.* AI output only ever lands in `candidate_*` tables; only `verify/` promotes it into the graph.
**Status (2026-10-20): fresh start, 0 of 82 steps.** An earlier build of this project (Box 1 plus three Collect steps) is archived on the branch `archive/v2-build-2026-10-20`. Lessons from it are kept in Steps 0 and 1. Everything is rebuilt from this plan.

**This is the primary spec.** Where it is silent (the full data model, the stack, and the detail for Steps 7–12), `docs/plan/PLAN_v2_base.md` applies. This plan adds the findings of the step-by-step research. It was checked line by line against the research by a separate auditor; the corrections are listed at the end.

**Acceptance tests in `feature_list.json` are unchanged**, except that P3-04 now forces the PDF path (approved). Four feature descriptions were updated to the researched method, and Mehar approved them on 2026-10-20 (see "Approved deviations").

**Labels used below:**
- **[finding]** — reported by a source.
- **[derived]** — our own calculation or design choice built on a finding.
- **[assumption]** — a starting value to tune or verify.

**Supporting research:**
- `docs/research/step4_reading_extraction.md` (Step 4)
- `docs/research/step5_checking_entity_resolution.md` (Step 5)
- `docs/research/step6_store_backfill.md` (Step 6)
- `docs/research/plan_audit.md` (the audit)
- Steps 2–3 were researched in conversation; their sources are listed in those sections.

---

## Approved deviations (signed off by Mehar, 2026-10-20)

`feature_list.json` descriptions already reflect these. Build them this way.

| Feature | Description says | Plan does | Why |
|---|---|---|---|
| P2-05 | "SPECTER2 embeddings" | Three-way test: TF-IDF vs SPECTER2 vs GTE-Large; keep the winner | Scholar Inbox found GTE-Large best; ASReview found TF-IDF as good as deep embeddings |
| P3-02 / P3-03 | "LaTeX parser" / "LaTeX table extraction" | arXiv HTML (LaTeXML output, built from the authors' LaTeX) as primary input; our own LaTeX pass is a fallback | 99.9% of citations linked on our 20 papers, with less code |
| P5-05 | "Record ER with Splink" | Deterministic identifier keys plus reused Semantic Scholar/OpenAlex author IDs; Splink only if those leave gaps | S2AND reaches B³ 0.900; no Splink numbers exist for bibliographic data |
| P3-04 test | "3 PDF-only fixtures" | The PDF path must be **forced** in the test | All 3 "PDF-only" fixtures actually have arXiv HTML |

---

## The system at a glance

| Lane | Steps | Runs |
|---|---|---|
| **Librarian** (always on) | 0 Foundation → 1 Collect → 2 Filter → 3 Parse → 4 Read → 5 Check → 6 Store | Daily, about 00:30 ET |
| **Analyst** (nightly) | 7 Serve → 8 Field analysis → 9 Prove it | After the Librarian |
| **Researcher** (on demand) | 10 Plan → 11 Run → 12 Ablations | When you choose |

The lanes communicate **only through the database**. Agent results go through the same Step 5 checks as everything else.

| Step | Researched? | Uses an LLM? |
|---|---|---|
| 0 Foundation | built and tested | AI connector only |
| 1 Collect | built (3 of 7) | no |
| 2 Filter | ✅ | cheap model on borderline papers only |
| 3 Parse | ✅ | **no** |
| 4 Read | ✅ | yes (the core of the system) |
| 5 Check | ✅ | small checkers, a second-opinion model, optional escalation |
| 6 Store | ✅ | no |
| 7–12 | not yet | various |

---

## Step 0 — Foundation (P0) — rebuild

**What to build** (proven in the archived build):
- Postgres 17 + pgvector 0.8.7
- settings and config
- one provider-agnostic AI connector: schema-checked JSON, one repair retry, cache, cost ledger, daily budget guard
- job queue with retries and crash recovery
- 20 fixture papers

**Archived build's verification:** 63 automated tests passed; 22 of 22 hands-on checks passed; a live Gemini call worked.

**Notes:**
- `gemini-2.5-flash-lite` is retired for new keys. Use `gemini-3.5-flash-lite` or newer.
- Training cutoffs for Haiku 5.5 and Sonnet 5.5 in `models.yaml` are placeholders. Confirm them before Step 9.
- In the archived build, DB tests skipped instead of failing when Postgres was down. In the rebuild, `make test` must **fail** if the DB is unreachable.

---

## Step 1 — Collect (P1) — rebuild

**What to build first** (proven in the archived build):
- arXiv OAI-PMH harvester (idempotent, versioned)
- daily listing
- PDF and e-print fetch
- registry with immutable, fingerprinted files

**Then:**
- OpenAlex / Semantic Scholar enrichment (P1-04)
- GitHub / Hugging Face snapshots (P1-05)
- cross-source dedup (P1-06)
- architecture doc (P1-07)

**Needs from you:**
- `S2_API_KEY` (request it first; approval can take days)
- `OPENALEX_API_KEY`
- `GITHUB_TOKEN`
- `HF_TOKEN`
- a new Gemini key (the old one was pasted in chat)

**Known issues from the archived build — avoid them in the rebuild:**
- Titles keep LaTeX escapes (`R\'enyi`). Normalize them to Unicode on insert, because P1-06 matching needs it.
- `rlg ingest fetch` stops the whole batch on one unknown ID. It should skip that ID and continue.
- OpenAlex returned a wrong title for ReAct's DOI, so dedup must not trust OpenAlex titles alone.

**Daily harvest details** (shared with Step 6):
- arXiv announces new papers Sunday–Thursday at 20:00 ET; OAI-PMH updates around 22:30 ET.
- Incremental harvests use `from` = the last server-reported datestamp, with no `until`.
- Rate limit: one request per 3 seconds, across all your machines combined.
- Before trusting withdrawal detection, check whether the server supports `deletedRecord` (via `Identify`).

---

## Step 2 — Filter: which of today's papers belong to our niche (P2)

**Input:** each day's records, roughly 1,300–1,700 [assumption from our live harvests; one `cs` day was about 1,700 including updated papers].
**Output:** each paper routed to `ignore`, `metadata_only` or `deep_read`.

### Method

**0. Write the niche down** in `config/niche.yaml`:
- a definition: LLM-based agents, harnesses, tool use, planning, memory, multi-agent systems, agent evaluation, agent skills
- about 40 **in** anchor papers
- 20–30 **near-miss out** examples, e.g. RL robotics agents, agent-based simulation, chatbots without tools

**1. Layer 1 — rules (free).** A category allow-list (cs.CL, AI, LG, SE, MA, IR, HC) [assumption] plus a keyword list, made deliberately generous.

**Scope safety net:**
- Papers within **one citation hop of the anchors** (cited by, or citing, an anchor) bypass Layer 1.
- Out-of-scope works become metadata-only **stub nodes** in the graph.
- Layer-1 recall is measured on the gold set.

**Why:**
- [finding] In a software-engineering study of three reviews (Mourão et al.), keyword/database search alone found 43–80% of relevant papers, snowballing alone 30–79%, and only the combination found 100% (at 1.3–2.7% precision). The authors say three reviews are too few to be conclusive.
- [fact] PreScience selects AI papers by 7 arXiv categories alone. That is too broad for our niche.

**2. Layer 2 — meaning-based scorer (free, runs locally).**
- Turn each abstract into numbers and score it with logistic regression.
- Test three representations: **TF-IDF, SPECTER2 and GTE-Large** (sign-off needed). Keep the best on the held-out set.
- Add about 5,000 random unlabelled papers as extra negatives, and add kNN-to-anchor similarity as a feature.

**3. Layer 3 — cheap AI, on the uncertain band only.**
- The model returns a **0–100 relevance score with reasoning off**.
- Code sets the cut-off on labels to hold **≥ 95% recall**.
- If accuracy is shaky, two cheap models vote.

**4. Routing and cap.**
- Code makes the final decision.
- A daily deep-read cap applies; overflow is queued by priority.

### Labels and evaluation
**Starter labels (P2-02):**
- anchor papers
- papers citing two or more anchors
- random cs negatives
- 600 abstracts labelled by a cheap AI

**The 150 items for Gate H0:**
- Stratified by label (this is what the P2-02 test checks).
- Within each label, chosen by **an uncertainty signal that already exists at P2-02**. Either disagreement between the cheap-AI label and the anchor/citation heuristic, or a throwaway TF-IDF + logistic regression fitted on the bootstrap labels. (The real scorer only exists after the gate.)

**A separate random held-out set** is reserved for the P2-05 recall/precision test. The uncertainty-sampled labels are used only for training and threshold tuning; testing on them would bias the result toward hard cases.

**Model bake-off for Layer 3, on your labels:**
- Gemma (local, free) vs Gemini Flash-Lite.
- Compare agreement with you, total time and cost. The cheapest model that meets the target wins.
- [finding] Gemma 2 9B ran at about 82–87 abstracts/min on an RTX A2000 12 GB.

### Risk and stop rule
[finding] No published LLM screener reached recall above 0.95 at precision around 0.5 (SESR-Eval), and Scholar Inbox's best F1 was about 0.85. The P2-05 target (≥ 0.95 recall, ≥ 0.6 precision) **on the embedding scorer alone** is therefore not guaranteed. The Layer 3 vote can't rescue it, because Layer 3 comes in P2-06. **If P2-05 misses, Claude Code logs the result and stops for your decision**, as CLAUDE.md requires.

### Tests (unchanged; full list in `feature_list.json`, P2-01 to P2-07)
- Category and keyword unit tests.
- Labels saved with a source per label; 150 review items stratified by label.
- Review page labels persist.
- Gate H0: 150 items labelled.
- Held-out recall ≥ 0.95 and precision ≥ 0.6; model saved with version and metrics.
- A simulated 1,300-paper day stays within budget; cap overflow is queued, never dropped.
- Architecture doc.

### Evidence
- **Scholar Inbox** (arXiv 2504.08385): GTE-Large reduced to 256 dimensions + per-user logistic regression, trained on ratings plus 5k random negatives; F1 84.51, AUC 86.75. TF-IDF scored higher on nDCG (88.67).
- **ASReview simulation** (medRxiv 2025; medical reviews): WSS@95 ≈ 92–93% for every model, TF-IDF + SVM best. WSS@95 is the work saved over random screening while still finding 95% of relevant papers. [not re-verified online: fetch blocked]
- **SESR-Eval** (arXiv 2507.19027):
  - No model reached recall > 0.95 at about 0.5 precision.
  - The smallest models were poor.
  - The reasoning model, o3-mini, was no better and cost about 26× more per review; its "≈10× tokens" figure wasn't found in the fetched text.
  - Threshold choice matters.
- **Compact LLMs study** (Research Synthesis Methods): high recall, low precision; majority voting as good as or better than single models.
- **ISPOR 2025:** isotonic calibration gave 83% recall / 56% precision. [not re-verified]
- **Oxford ensembles:** ensembles reached perfect sensitivity on a development set. [not re-verified]

**Changed from v2:**
- near-miss negatives
- one-hop anchor safety net with stub nodes
- uncertainty-ranked H0 labels from a signal that exists at P2-02
- a separate random held-out set
- three-way embedding comparison
- 0–100 score with a tuned cut-off
- reasoning off
- model bake-off
- an explicit stop rule

---

## Step 3 — Parse: paper to clean structured text (P3) — no LLM

**Input:** an arXiv ID marked deep_read.
**Output:** one `CanonicalDoc` per paper version:

```
CanonicalDoc
  text            the only text quotes are checked against
  sections[]      id, title, type (abstract|intro|related|method|experiments|appendix|other), start, end
  paragraphs[]    id, section_id, start, end
  citations[]     marker_start, marker_end, sentence_start, sentence_end, bib_id
  bibliography[]  bib_id, raw, authors, year, title, venue, arxiv_id?, doi?, url?, link{paper_id, method, score}?
  tables[]        table_id, caption, caption_start, caption_end, cells[row][col], section_id
  footnotes[]     id, text, urls[]
  source          html | latex | pdf
  quality         errors, missing_sections, fallback_reason?
  parser_version, content_sha256
```

### Method
1. **Fetch arXiv's HTML** from `arxiv.org/html/<id>v<n>`, falling back to ar5iv.
   - At least 3 seconds between requests, with your contact email in the request header.
   - Store the raw HTML once, by fingerprint.
   - Save the fixture HTML so offline tests run without network.
2. **Quality gate:** count `ltx_ERROR` markers, and require an abstract, at least 3 sections and a reference list. Thresholds start at "5 or more errors means fallback" [assumption: tune on the 500-paper report]. If the gate fails, use the fallbacks in item 8.
3. **Build the clean text** by walking the HTML in reading order:
   - Paragraphs: whitespace collapsed, no space before punctuation.
   - Section types: from keyword rules on the section title.
   - Math: replaced by its LaTeX `alttext`.
   - Citation markers: kept, with their `bib_id`.
   - Footnotes: taken out of the sentence and kept, with their URLs (these are often repo links).
   - Figures: dropped, captions kept.
   - Tables: taken out of the running text.
4. **Split sentences** with a rule-based splitter that knows "et al.", "e.g." and "Fig.". Store the sentence around every citation.
5. **Reference entries:** split into authors+year, title and venue blocks. Pull arXiv IDs, DOIs and URLs out with patterns.
6. **Tables:** read cell by cell, expand merged cells, keep math as LaTeX, and record each table's caption and section.
7. **Link references to papers, cheapest first.** Each link records which method made it.
   1. An ID already present in the reference.
   2. **The citing paper's reference list from Semantic Scholar/OpenAlex**, once the keys exist.
   3. arXiv title search: clean the title, search on its key words, and score with the S2ORC method (character 3-grams, harmonic mean of Jaccard and containment), accepting **≥ 0.8**. This costs about 3 s per lookup because of rate limits.
   4. OpenAlex / Semantic Scholar title lookup.
   5. Otherwise leave it unlinked. Never guess.
8. **Fallbacks:**
   - (a) The LaTeX source, with citations resolved through the `.bbl` file.
   - (b) For the PDF: Marker for the body text (LLM mode off), plus GROBID for references and citation contexts. Anystyle is the best-ranked reference parser and can replace GROBID's reference step if needed.
   - [finding] About 10% of arXiv papers are PDF-only.
9. **Save** with `parser_version` and a fingerprint. A parser fix creates a new version, and old quotes stay checkable against the version they came from.

### Tests (unchanged)
- At least 95% of citations resolved.
- At least 90% of tables extracted with the right cell count.
- Offsets round-trip (property test).
- The PDF fallback produces a CanonicalDoc for 3 papers, **with the PDF path forced**.
- Parsing report on 500 papers.

**Added to that report:**
- reference-link coverage, split by link method
- 50 hand-checked links to measure precision (S2ORC publishes no precision for its linking, so this is the measurement)

### Evidence

**Our test on the 20 fixture papers:**

| Measure | Result |
|---|---|
| HTML available | 20 of 20 |
| Converted with no errors | 19 (MetaGPT had 8 `ltx_ERROR`) |
| Citations linked to a reference entry | 1,478 of 1,479 |
| Reference entries with a separate title block | 1,343 of 1,346 |
| Reference entries that already carry an arXiv ID | 32% |
| arXiv title search matched | 17 of 25 sampled, after title cleaning (11 of 25 on the first pass); most misses weren't on arXiv |
| Tables | clean cells |

**Literature:**
- arXiv HTML: about 97% of submissions produce some HTML; about 75% convert with no errors (arXiv 2605.16562).
- unarXive 2022: links 44.4% of references and 48.3% of citation markers (arXiv 2303.14957).
- S2ORC: the 3-gram / 0.8 linking rule.
- In a comparison of reference parsers, Anystyle ranked best and GROBID mid-pack (arXiv 2205.14677).

**Changed from v2:**
- arXiv HTML is the primary input (sign-off needed)
- LaTeX becomes a fallback
- reference linking fully specified, with S2/OpenAlex reference lists ahead of title search
- the PDF test is forced onto the PDF path

---

## Step 4 — Read: AI extraction into holding tables (P4)

**Input:** a CanonicalDoc.
**Output:** rows in `candidate_claim`, `candidate_edge` and `candidate_result`. Every row carries an exact **sentence-level** quote with offsets, or a table cell ID.

### Section routing (done by code)
Each call stays at a few thousand tokens.

| Pass | Gets |
|---|---|
| Problem, method | abstract, intro, method |
| Limitations | discussion and limitation sections only |
| Lineage edges | intro, related work and method, plus citation sentences |
| Results | one table, the paragraphs that mention it, and the setup section |

### Pass A — Paper card
Entities are extracted first, then relations.

**Fields, each with a 1–2 sentence quote:**
- problem
- method and its components
- datasets and benchmarks, each with a **role**: proposed, used, compared, or only mentioned
- metrics
- headline results
- **author-stated limitations only**

**Prompt technique:**
- Tag entity spans inline in the input.
- Put the annotation guidelines in the prompt.

**Artifacts** (code, model and data links) are found by code, from URL patterns and footnotes, and resolved through GitHub and Hugging Face. The AI only labels what each link is.

### Pass B — Lineage edges, classified per reference

**Input, gathered by code** for each reference:
- every mention of it, as the citation sentence ±1 sentence
- the section each mention is in
- the cited paper's abstract

**The AI returns** `type`, `component`, a one-line `delta` and a `quote`.
- **AI-typed edge types:** `extends`, `combines`, `replaces_component`, `transplants_domain`, `refutes_or_contradicts`.
- **Components:** planner, memory, tool_interface, action_space, critic_verifier, environment, orchestration, training_signal, prompting, other.
- Only the strongest relation per reference is kept.

**Rules around the AI step:**
- A dedicated **high-recall pass for rare types** (extends, contradicts).
- Semantic Scholar's `isInfluential` flag is used only to rank references, never to type them.

**Code-derived edges, no AI:**
- `evaluates_on` and `compares_against` come from verified result rows: a benchmark header, or a baseline row that carries a citation.
- `uses_artifact` comes from dependency files and explicit links (P4-05).

### Pass C — Results
One record per numeric cell.

**Fields:**
- method, benchmark, split, metric
- `value_literal`, the exact cell substring (this is what the P4-04 "literally present in cell" test checks)
- `value_numeric`, normalized: bold, ±, and % scaling stripped
- settings: harness/scaffold, attempts/pass@k, base model, shots, **each with a supporting quote**, or set explicitly to **"not stated"**
- cell ID

**Code checks:**
- The value matches the cell.
- Benchmark and metric agree with the cell's header path.
- Rows with every setting "not stated" are flagged.

**Normalization:**
- Benchmark and metric names normalize against a **closed alias table** (curated, with additions reviewed).
- Each normalization decision is cached, so no decision is made twice.
- The averaging rule (micro/macro) is recorded.

**Rules:**
- Rows with an unknown harness are never ranked against rows with a known harness.
- Every row is kept, including baselines and negative results.
- The caption is an input, not ground truth.

### Output format and models
- **Schema:** flat JSON with fields in the order **quote, then rationale, then label/value**. Validated with Pydantic, with one retry.
- **Models:**
  - A mini-tier model does the bulk of the work.
  - Edge typing escalates only on Step 5 disagreement.
  - Reasoning mode is off by default; test it only on edge typing.
- **Model bake-off** on the 20 fixtures plus the dev gold set: compare cost per *verified* item, and **recall**, not precision alone.
- **Scoring:** each stage is scored against its own gold labels, because errors multiply across stages.

### Cost
Measured in P4-07 and written to `docs/cost_model.md`.

[finding] Published per-paper costs range from about $0.01 (GPT-4.1-mini) to about $0.29 (GPT-4o for tables).

[derived] Expect well under $1 per paper with batch pricing.

### Human steps
- **Gate H1:** label 30 pilot papers in the review page, which highlights each claim in context. Then freeze schema v1.
- **Gate H2 — gold set: 100 papers** (60 dev, 40 held-out), as the P4-10 test requires.
  - [derived] Estimated at **25–35 hours**, about 2–4 months at the daily review budget. **Start it early, in parallel with the build.**
  - Split dev/held-out **by paper**.
  - **Annotate fully:** all card fields, and the name merges those papers touch.
  - **Annotate lineage only for lineage-relevant citations:** those pointing to papers in the graph, or appearing in method/experiment sections. Without this rule, 100 papers is about 2,700 citation contexts.
  - Over-sample rare edge types.
  - With one annotator, measure **intra-annotator (self) agreement**: re-label 10–20% of dev papers blind after at least two weeks.

### Tests (unchanged)
- Schema-valid ≥ 99%.
- At least 95% of quotes match exactly.
- Every edge references a resolved citation or is dropped.
- Values literally present in their cells.
- Fixture repo yields `uses_artifact` edges.
- Review page relabel and export works.
- Cost model document.
- Gates H1 and H2.
- Dev extraction report.
- Architecture doc.

### Later
The **fine-tune path**: once 10k–40k verified rows exist, fine-tune a 7–8B open model, using SFT plus a reward rather than plain SFT, and check it against the held-out gold set.

### Evidence
- **LLMEvalDB** (ACL 2025): 98.8% value accuracy from table source plus a schema. Small audit, n = 40.
- **SciER:**
  - Prompted LLMs reach about 38–41 strict relation F1, against 61.1 for the best supervised model.
  - A preprint reports 66 for an RL-tuned 7B model.
  - Entities-first beat joint extraction (41.2 vs 34.9).
- **ACL-ARC:** GPT-4 scores 38.6 zero-shot and 50.2 five-shot, against about 76 for fine-tuned models. "Extension" is about 4% of citations.
- **MultiCite:** ±1 sentence is the best fixed context window.
- **Cohan et al. 2019:** adding section labels raised "Uses" F1 from 65.4 to 75.0.
- **Intern-Atlas** (self-audited preprint): production model 70.4% vs audit model 93.0% on edge type; deterministic quote checks.
- **NoLiMa:** long-context accuracy drops early.
- **"Let Me Speak Freely?":** field order matters.
- **arXiv 2510.01235:** GPT-4.1-mini scored 0.889 vs GPT-4.1 at 0.909. The recall loss was **Gemini 2.0 Flash's** (R 0.695).
- **SciREX:** an end-to-end pipeline collapsed to 0.008 F1.

**Changed from v2:**
- section routing
- per-reference edge classification
- three edge types derived by code
- a high-recall pass for rare types
- artifacts found by code
- author-stated limitations only
- evidence-first field order
- literal plus normalized values
- settings quotes
- closed normalization table
- recall measured
- gold-set scoping and a realistic time estimate

---

## Step 5 — Check and clean names (P5) — code decides

**Input:** candidate rows.
**Output:** promoted canonical rows and merge decisions. Uncertain items **stay pending in `candidate_*`**; nothing is rejected just for being uncertain.

### 5a. Claim checking, cheapest layer first

**1. Hard rules:**
- The quote is an exact substring at its offsets.
- The quote sits next to its citation; otherwise the edge is downgraded to `cites`.
- The citing paper is dated after the cited paper.
- For extends, combines and replaces_component, B must be in A's reference list.
- Node types fit the edge type.
- No self-loops, no duplicates, no opposite-direction conflicts.
- No extends **and** refutes on the same pair without separate evidence for each.
- `replaces_component` must name a component that appears on B's card.
- `transplants_domain` needs two different domains.
- Very long time gaps are flagged.

**2. Small grounding checker.**
- One of: MiniCheck-FT5 (0.8B), FactCG-DeBERTa (0.4B) or Bespoke-MiniCheck-7B.
- Run on a **templated hypothesis per AI-typed edge type**.
- **Code-derived edge types are marked "deterministic, no template"**, which satisfies P5-02's "templates for all types".
- For `refutes_or_contradicts`, the quote must **entail** "A reports a result inconsistent with B's claim R". An NLI "contradiction" label means the *edge* is wrong.
- The starting threshold is 0.5.

**3. Per-type thresholds**, tuned on dev labels with a statistical bound for a target precision (the Trust-or-Escalate method), not by eye.
- Rare types won't have about 500 dev labels each, so **pool them**, or **don't auto-promote them**; they go to review.

**4. Second opinion.**
- A model from a **different family** votes over **about 5 samples**.
- **Promotion needs a high checker score plus at least 4 of 5 agreement.**
- Disagreements go to an optional stronger model, then to the human queue.
- A model's own stated confidence is not used.

**5. Every `refutes_or_contradicts` candidate is adjudicated by the strong tier** (required by P5-03).
- The "unlike / in contrast to" guard is applied **first**, so wording-only cases arrive labelled "likely method difference".
- They are adjudicated, never silently downgraded.

**Expected effect** [finding, from a general evaluation task]: at strict precision targets, about 20–45% of the items reaching the cascade are escalated.

### 5b. Name matching (entity resolution)

**1. Identifiers first:** arXiv ID without the version suffix, DOI, GitHub and Hugging Face IDs, specific URLs.
- **Ban any identifier that maps to two or more entities**, e.g. a generic kaggle.com URL.
- A new **dataset** entity is created only when a name and a specific URL appear in at least 3 papers [finding, ChatPD, for datasets]. Using the same rule for methods and harnesses is an [assumption].

**2. Curated alias table:** about 300 seed concepts, also seeded from the frozen Papers with Code archive. Auto-merge only on a curated alias hit.

**3. Version markers block "same".** Names that differ by Verified, Lite, v2, 7B, -Instruct and similar are never merged; they become `variant_of` / `subset_of` links. Embedding similarity is never used to merge [derived: versions look almost identical to embeddings].

**4. The AI only judges leftover candidate pairs.** Labels: same / variant_of / subset_of / broader / related / different. Decisions go to the candidate tables, and code applies the rule.

**5. Authors, papers and repos.**
- **Authors:** reuse Semantic Scholar / OpenAlex author IDs.
- **Papers:** matched by DOI, arXiv ID, or normalized title + year + first author.
- **Preprint vs published version:** linked by `version_of`, not merged.
- **Repos:** linked through explicit identifiers.

**6. Reversible:** merges are events in a bitemporal alias table, resolved at query time.
- Edges keep their original IDs.
- Every AI decision is cached and replayed on rebuild.

**7. Reporting:** B³ score, with false merges and false splits reported separately.

**8. Alerts:**
- one identifier mapping to two entities
- spikes in merges

### 5c. Your review time
[derived] 15–30 min/day is about 15–40 labels.

**Queue order, by blast radius:** merges first (one bad merge corrupts many edges), then edges used by analytics, then card facts.

**Split of time** [assumption, a design choice]:
- **About 60%: random audit.** Stratified, sampled as *pick a paper, then label 3–5 of its facts* [finding: this cut labelling time by up to 60–80% in Gao et al., VLDB 2019]. **Each label's sampling probability is stored in `review_labels`.**
- **About 40%: uncertain items**, for fixing errors. These are kept out of the precision estimate.

**Precision reporting:**
- Report Wilson intervals.
- [derived, from binomial math] Targets: ±10% per edge type (about 35–62 labels) and ±5% for the whole graph (about 139 labels at roughly 90% precision).

**Anchoring check:** hide the AI's label on 10–20% of audit items.

**Monitoring:**
- Each daily batch is its own stratum, with a rolling 4-week precision and an alert on the lower bound.
- **Re-run the held-out evaluation** after every prompt, model or threshold change.

**Tooling:** a thin custom review page that writes to `review_labels`.

### Gate H3 (unchanged)
- Verified-edge precision ≥ 0.85 on held-out papers.
- Name-merge false-merge rate ≤ 2%.

### Evidence
- **LLM-AggreFact:** small checkers score about 75–77, level with Claude 3.5 Sonnet (77.2) and GPT-4o (75.9), at about 1/400 of GPT-4's cost.
  - Bespoke-MiniCheck's 77.4 was submitted by its own vendor.
  - None of the benchmark's datasets is scientific text; expert text scores about 60.
  - Real accuracy is unknown until measured on our dev labels.
- **SciTraj** (preprint): 79.9% of edges correct overall; disputes only 63%. About 37% of dispute edges were "in contrast to / unlike" wording.
- **MSciNLI:** fine-tuned model 77.2 vs prompted LLM 51.8.
- **Trust or Escalate** (ICLR 2025): met its 90% agreement target in 90.8% of trials, vs 47–79% for naive thresholds.
- **ChatPD** (preprint): P 0.983 / R 0.873, vs 0.57 F1 for name matching alone.
- **OpenAIRE:** about 23% false merges in production.
- **S2AND:** B³ 0.900.

**Changed from v2:**
- full hard-rule list
- refutes entailment semantics, with every refutes edge adjudicated
- named checkers
- statistically tuned thresholds, with rare-type pooling
- cross-family 4-of-5 vote
- pending status
- ChatPD identifier rules
- version-marker blocking, no embedding merges
- merges reviewed first
- sampling probabilities stored
- Wilson intervals
- anchoring check
- held-out re-runs

---

## Step 6 — Store, backfill, daily run (P6)

### Schema (Postgres 17)

**Tables:**
- **One logical edge per (src, dst, etype)**, with per-paper evidence in `edge_evidence`; result rows in their own table.
- **Two time ranges per row:**
  - `valid_from` / `valid_to`: world time
  - `recorded_at` / `superseded_at`: pipeline time
- Both stored as generated `tstzrange` columns with `[)` bounds.

**Conventions:**
- **"Open-ended" is a NULL end**, never the value `'infinity'`.
- All timestamps are explicit UTC. A bare date literal is read in the session's time zone.

**Append-only:**
- A trigger allows changes only to `superseded_at` (NULL → a value) together with `superseded_by` and `supersede_reason` (extraction_error / world_change / merge / schema_migration).
- Corrections close the old row and insert a new one.

### Dates
- **Paper dates:** store `announced_at`, `submitted_at` and `first_public_date`.
- **`valid_from`** is the **announcement time** of the **earliest arXiv version whose text contains the evidence**, with `source_version` stored.
  - [derived] The research suggested submission time; announcement time is the stricter choice.
  - Not v1, if the claim only appeared in a later version.
- **`valid_to` closes only for:**
  - withdrawal
  - a claim removed in a later version
  - a verified refutation
  - a superseded state, e.g. "best score on benchmark X"

  Never for permanent relations like extends or cites.
- **Extraction errors close pipeline time**, not world time.
- **New paper versions:** re-extract, and supersede what changed.

### Indexes and queries
- **Indexes:**
  - btree on `(src, etype)` and `(dst, etype)`
  - a partial index on current rows
  - a GiST exclusion constraint, for integrity only
- **Lineage queries:** recursive CTEs using `UNION`, with a depth cap and an edge-type filter. Use `CYCLE` only when the actual paths are needed. Avoid all-paths over plain citations beyond depth 4.
- **No graph database and no Apache AGE** at this scale.

### freeze(T, R, strict)
**Every query and every API response states T and R.**

**For the anchor check (P6-05):** `freeze(T=2025-12-31, R=now, strict=true)`, labelled a "reconstruction".

**Strict mode** also requires:
- only paper versions announced before T
- metrics and citation counts as of T
- merge evidence dated before T
- each row's model training cutoff, recorded and checked
- a PreScience-style retrieval filter: drop anything dated on or after T, same-title papers, and papers sharing 50 or more characters of abstract

**Why strict mode is needed:** the backfill records everything as learned *today*. Pipeline time therefore cannot make 2022–2025 backtests honest; strictness has to come from these rules. **Report results with and without strict mode**, to measure hindsight.

**Snapshots:**
- UNLOGGED tables, with a registry row.
- Past snapshots are immutable and cached.

**Export:**
- ADBC → Arrow → numpy → igraph, with dense integer IDs per snapshot, cached as Parquet.
- ADBC is a new dependency: note it in `claude-progress.txt`, or use the psycopg fallback (about 0.5 s).

### Backfill and daily run
1. **Scope and harvest.** Scope is the Step 2 filter **plus the one-hop anchor neighbourhood**; out-of-scope works become metadata-only stubs. Then harvest metadata for that scope.
2. **200-paper pilot.**
3. **Backfill order:** anchors and their one-hop references first, then newest first, by month.
   - Resumable and budget-capped.
   - Uses **batch APIs**:
     - Batch pricing is 50% off.
     - [finding] Anthropic batches take up to 100k requests and target 24 hours; unfinished requests then expire unbilled. Batch and caching discounts stack.
     - Gemini batch jobs that run past 48 hours return **nothing**, so keep Gemini batches small.
   - Robustness:
     - `custom_id` = sha256 of (content hash, prompt version, model), cut to 64 characters.
     - Write an `llm_batch` row before submitting.
     - Re-queue errored or expired requests; dead-letter invalid ones.
     - Dry-run every new request shape on the regular, non-batch API.
4. **Promote, with restore points:** `pg_create_restore_point('run_<id>')`.
5. **Upgrade stub nodes** when they enter scope.
6. **Daily run, about 00:30 ET**, Sunday–Thursday announcement nights, with a holiday calendar so expected empty days don't alert.
   - Results are staged, then promoted in **one atomic `promote(run_id)` per day**.
   - Content-hash cache keyed on content, prompt version, model and schema.
   - At-least-once queue with idempotent handlers.
7. **Weekly forward-citation rescan.**
8. **Monitoring:**
   - A dead-man's-switch ping (start / success / fail).
   - Alerts on row counts, rejection and disagreement rates, merges and cost, when they move ±50% or more than 3 MAD from the 4-week same-weekday median [assumption].
9. **Backups:**
   - pgBackRest with WAL archiving and point-in-time restore, or a nightly `pg_dump` to start.
   - Copies on local disk plus an encrypted off-site copy. Cloudflare R2 is the candidate target [assumption: R2 settings unverified]. `repo2-cipher-type` is fixed at creation.
   - Weekly `pg_dump`.
   - **Monthly restore drill.**

### Cost
[derived, illustrative] Assuming about 20k input and 2k output tokens per paper, for one extraction pass only, batch pricing comes to about **$15 per 10k papers on Haiku 5.5** and **$300 per 10k on Sonnet 5.5**. **Confirm the Haiku price on your account**; it looked unusually low.

### Tests (unchanged)
- Superseding sets `superseded_at` and inserts a new row.
- freeze property tests: no rows with valid_from > T or recorded_at > R; agent rows excluded by default.
- Kill-and-resume causes zero duplicate paid calls.
- A simulated day runs end to end.
- A backup restores.
- At least 70% of anchor lineage links found.

**Test style:** a Hypothesis state machine checks the database against a pure-Python model:
- T and R exactly on range boundaries, and ±1 µs from them
- time-zone independence
- recursive-CTE paths equal networkx paths

### Measured
Local benchmark on Postgres 16 with a synthetic 1M-edge graph. The scripts were not kept, so treat these as order-of-magnitude only.

| Operation | Time |
|---|---|
| Lookup as of a date | ~0.1 ms per node |
| 20 lineage queries, depth ≤ 10 | ~7 ms |
| 1M-edge snapshot | ~1.2 s |
| Export to igraph | under 1 s |
| PageRank, igraph | 63–90 ms (networkx: 2.8 s) |

### Evidence
- **SQL:2011** bitemporal model. **Graphiti/Zep** (vendor preprint) uses the same four timestamps.
- **Leakage:**
  - [finding, preprint] Random rather than time-based splits inflated metrics by 38–151% on a citation dataset.
  - [finding] HindSight's generator model's training cutoff falls inside its own evaluation window.
- **PreScience:** metrics as of each paper's date, plus the retrieval filter.
- **Anthropic and Gemini batch documentation.**
- **arXiv announcement schedule.**
- **Mourão et al.** (scope).

**Changed from v2:**
- `edge_evidence` table
- precise version dates
- closing rules
- append-only trigger with explicit allowed fields
- query-time alias merges
- strict freeze with explicit T and R, reported with and without strict mode
- one-hop scope with stub nodes
- anchors-first backfill
- batch robustness
- atomic daily promotion
- arXiv timing and `deletedRecord` check
- MAD-based alerts
- restore drills

---

## Steps 7–12 — not yet researched (as in v2)

| Step | Phase | What | Tests (unchanged) |
|---|---|---|---|
| **7 Serve** | P7 | Query API (lineage path, neighbours by type, results by benchmark; `as_of` on every endpoint), read-only **MCP tools for Amoeba**, field-map web pages where every claim links to its quote | contract tests; an MCP client calls each tool; every UI claim links to its evidence |
| **8 Field analysis** | P8 | Research families (Leiden) with identity tracking; topics (BERTopic); rising terms (Kleinberg bursts); main lineage (SPC); frontier; SOTA curves and saturation per benchmark/split/metric/harness; contradiction clusters; gaps via link prediction; transplants | main path recovers ≥ 70% of anchor links; SOTA matches hand-checked values; reruns identical |
| **9 Prove it** | P9 | Look-back test with freeze(T), matched against real later papers, plus graph completion; **leakage probe**; **forward prediction ledger** (hash-chained, scored monthly; the headline thesis metric) | end-to-end report; tampering detected |
| **10 Plan → Amoeba** | P10 | Amoeba task/team spec (**Gate H4**); seed mix including low-attention branches; ideas as typed-delta tuples; **structural novelty gate**; pairwise AI judging for pruning only; lineage personas mapped to Amoeba contracts | novelty gate rejects 100% of planted already-published ideas; spec validates |
| **11 Run and write back** | P11 | Rules locked before each run; sealed sandbox; separate grader; MLflow; results, including failures, written back as agent-made | agent can't change the locked protocol; negative results stored; analytics exclude agent rows by default |
| **12 Ablations** | P12 | Typed graph vs plain search / GraphRAG; lineage vs role personas; write-back on/off; novelty gate on/off | report with confidence intervals |

**Next to research, in order:** Step 8 (field analysis), Step 9 (evaluation and leakage), then Step 10 (planning and Amoeba).

---

## Your human checkpoints

| Gate | When | You do | Time |
|---|---|---|---|
| Keys | now | Add S2, OpenAlex, GitHub and HF keys and a new Gemini key | 30 min (S2 approval may take days) |
| H0 | Step 2 | Check 150 triage labels | ~1 h |
| H1 | Step 4 | Label 30 pilot papers; freeze schema v1 | ~4–6 h |
| H2 | Step 4 | Gold set of 100 papers (60 dev, 40 held-out), scoped as described in Step 4 | ~25–35 h [derived]; **start early** |
| Daily | Step 5 onward | Random audit plus uncertain-item review | 15–30 min/day |
| H3 | Step 5 | Accept precision and merge results | ~30 min |
| H4 | Step 10 | Approve the Amoeba spec format | ~30 min |

---

## Possible thesis contributions surfaced by the research

1. **The first gold set for typed lineage edges and agent settings** (harness, attempts, base model), with self-agreement measured.
2. **Rejection rates at each stage**, showing how much "LLM proposes, code disposes" improves on the model alone.
3. **Measured leakage** in time-split evaluation from later paper versions, later merges and model training cutoffs, reported with and without strict mode.
4. **Version-aware entity resolution** for ML models and benchmarks. No benchmark exists.
5. **Section routing vs full-paper input** for frontier-model extraction. No controlled study exists.
6. **A small open model fine-tuned on verified rows** that matches frontier models on edge typing.

## Open decisions (unchanged from v2)
1. Gemini vs Claude per tier, after the Step 4 bake-off.
2. Whether to adopt Dagster, after Step 6, if cron plus the queue isn't enough.
3. The second slice (SLMs or VLMs), after Step 9.

---

## Audit corrections applied in v3.1

**Conflicts with the existing tests, fixed:**
- The gold set stays at 100 papers, with the scoping rule added.
- The H0 uncertainty signal is one that exists at P2-02, with a separate held-out set and a stop rule for P2-05.
- Every refutes edge is adjudicated.
- Literal and normalized values are kept separately.
- The append-only trigger's allowed fields are spelled out.
- The freeze signature is explicit for P6-05.
- Edge templates or "deterministic" are defined for every type; `uses_artifact` is code-derived.
- The P3-04 PDF test is forced.
- The four description deviations are listed for sign-off.

**Factual corrections:**
- unarXive 44.4% / 48.3%.
- "Section labels help" is Cohan et al. 2019, not MultiCite.
- The recall loss belongs to Gemini 2.0 Flash, not GPT-4.1-mini.
- 5-sample vote with 4-of-5 promotion.
- Escalation share is of cascade items.
- Backfill is anchors first; batches target 24 h, then expire.
- ASReview figure is WSS@95.
- GPT-4 on ACL-ARC: 38.6 zero-shot / 50.2 five-shot.
- Title search 17/25 was after cleaning (11/25 before).
- Gemma figure is for Gemma 2 9B on an RTX A2000.
- Agreement is intra-annotator.
- SciTraj's 37% is of dispute edges.
- The label set includes "broader".

**Labelled as assumptions or derived:** audit split, label counts, gold-set hours, ≥3-paper rule beyond datasets, category allow-list, daily volume, gate thresholds, R2 target, batch cost, PG16 benchmark.

**Added from the reports:**
- one-hop anchor scope with stubs
- S2/OpenAlex reference lists in linking
- pending status and blast-radius queue order
- rare-type threshold pooling
- full hard-rule list
- refutes entailment semantics
- Papers with Code alias seed
- B³ with merges and splits reported separately
- ambiguity alerts
- sampling probabilities
- held-out re-runs
- per-stage scoring
- normalization cache and closed taxonomy
- averaging rule
- settings quotes and sentence-level quotes
- fine-tune path
- announcement/submission dates
- explicit T and R
- PreScience filter
- with/without-strict reporting
- batch robustness and small Gemini batches
- `edge_evidence`
- arXiv Sunday–Thursday schedule and `from`-only harvests
- `deletedRecord` check
- MAD alerts
- Hypothesis invariants
- Anystyle fallback
- offline HTML fixtures
