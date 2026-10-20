# Audit of RESEARCHED_PLAN.md (v3) against its research

**Audited:** `/home/claude/RESEARCHED_PLAN.md` (432 lines). Line numbers below refer to that file (`L###`).
**Compared against:**
- `reports/LLM extraction from scientific papers.md` ("Extraction report") and its 4 notes
- `reports/Claim verification and entity resolution.md` ("Check report") and its 3 notes
- `reports/Bitemporal graph store and backfill.md` ("Store report") and its 3 notes
- The Step 2 and Step 3 conclusions given in the audit brief ("Step 2 brief", "Step 3 brief")
- `mehar-research-/PLAN.md` (v2) and `mehar-research-/feature_list.json` (unchanged in git; no diff against HEAD)
- Online spot-checks, listed under each step

**Date:** 2026-10-20. No project files were edited.

**Summary:** most numbers are quoted correctly. The serious problems are conflicts with the unchanged acceptance tests:
- H2 "or ~60 papers" vs P4-10's 60/40 split.
- Uncertainty-sampled H0 labels vs P2-02's ordering and P2-05's held-out evaluation.
- The "unlike" contradiction guard vs P5-03 "every refutes edge reaches adjudication".
- Feature titles and descriptions that now describe a different implementation (P3-02, P3-03, P2-05, P5-05).

There are also a few wrong attributions and claims stated more strongly than the sources support, and several important recommendations from the reports are missing.

---

## Step 0–1 (not in audit scope; light check only)

- **Correct:**
  - 82 features in total and 11 with `passes: true` (P0-01..08 and P1-01..03); P1 is 3/7 (L5).
  - pgvector 0.8.7 (L42).
  - The skip-instead-of-fail note matches `claude-progress.txt` L37.
  - The Haiku/Sonnet 5.5 cutoff placeholders match `claude-progress.txt` L60.
- **Not verified:** "63 tests pass, 22 of 22 hands-on checks" (L44). Neither number appears in `claude-progress.txt`.

---

## Step 2 — Filter (L72–106)

### Correct
- GTE-Large + per-user logistic regression, plus about 5k random unrated negatives (L85, L104). Online check: Scholar Inbox embeds with GTE-Large (1024-d, reduced by PCA to 256), trains a logistic regression per user, and samples 5k random non-interacted papers as negatives.
- "23k users" (L104). Online check: about 23k registered users. Note that the evaluation dataset covers 14.3k users.
- The three-way TF-IDF / SPECTER2 / GTE-Large comparison (L84) is well justified. In Scholar Inbox Table 2:
  - GTE-Large: F1 84.51, AUC 86.75
  - SPECTER2: F1 83.22, AUC 86.36
  - TF-IDF (10k dims): best nDCG at 88.67
- Reasoning off, a 0–100 score, a cut-off tuned for ≥95% recall, and an optional 2-model vote (L88–90) all match the Step 2 conclusion.
- The Gemma vs Gemini Flash-Lite bake-off on the 150 labels (L96) matches the brief.
- "No gain at about 10× the tokens" (L106) matches the brief. Online check: SESR-Eval o3-mini F1 0.47 was not better than Llama 4 Maverick (0.53) or GPT-4o (0.50). The ~10x token figure itself was not visible in the fetched text; see below.
- "Accuracy varies by topic" (L106) is supported. SESR-Eval says differences between secondary studies are larger than differences between LLMs: accuracy 0.34–0.85, F1 0.07–0.92. The source word is "secondary study (review)", not "topic".

### Errors
| Plan text | What the source says | Suggested fix |
|---|---|---|
| L105 "ASReview (TF-IDF + SVM saves about 93% of reading at 95% recall)" | WSS@95 = 92.77% for SVM+TF-IDF, and all models were about 92–93%. WSS is *work saved over random sampling* at 95% recall, not "share of reading saved". The data is medical systematic reviews. | "TF-IDF + SVM reached WSS@95 ≈ 93% (work saved over random sampling) on medical systematic-review data. All models were within 92–93%, so the simple model is enough." |
| L96 "Gemma (... about 85 abstracts per minute on a modest GPU)" | Gemma **2 9B**, ~82–87 requests/min on an **RTX A2000 12 GB** (compact-LLMs study, Research Synthesis Methods) | Name the model and hardware: "Gemma 2 9B, ~82–87 req/min on an RTX A2000 12 GB". A newer Gemma will differ. |
| L106 "score plus tuned cut-off and voting helped" | The ISPOR 2025 isotonic-calibrated GPT-4o reached only **83% recall / 56% precision** on test. Voting was "as good or better" (compact-LLMs study). The Oxford ensembles reached perfect sensitivity, but no precision is given in the brief. | "Calibrated scores did not reach 95% recall in the one study (83% R / 56% P). Ensembles and voting raised sensitivity." State that no study reached 0.95 recall with ≥0.5 precision (SESR-Eval). |
| L104 "Scholar Inbox (GTE-Large + logistic regression ...)" offered as evidence that L2 will hit the target | GTE-Large F1 is about 0.85. That is a per-user recommendation task, not niche classification at 0.95 recall. | Keep the citation, but do not imply it shows the 0.95/0.6 target is reachable. |

### Missing (from the Step 2 conclusion and related reports)
- **Scope snowball.** The Store report's "Scope" row (L23 of that report, Mourão et al.) says category/keyword search alone reached only **43–80% recall**, and snowballing alone **30–79%**. Search plus snowballing reached 100% at 1–3% precision. It recommends a union of the category/keyword filter and a 1-hop backward/forward expansion from anchors. The plan's Layer 1 (L82) is category plus keyword only, and its Backfill item 1 (L341) does not mention it either. Add "papers within 1 hop of anchors bypass Layer 1" and measure Layer-1 recall on gold.
- **PCA to 256** for GTE-Large (efficiency detail, minor).
- **Isotonic calibration** of LLM scores (ISPOR) as one way to tune the cut-off. Optional.
- **SESR-Eval:** the smallest models (GPT-4.1 nano, Ministral 8B) performed poorly. This argues for keeping the bake-off and not choosing the smallest local model by default.
- **Hold out a random evaluation set** separate from the uncertainty-sampled H0 labels. See Conflicts.

### Unsupported / assumptions (label as such)
- The category allow-list `cs.CL/AI/LG/SE/MA/IR/HC` (L82) is a design choice. The brief only says PreScience used 7 arXiv categories and does not say which. Also, P1-02 harvests `stat.ML`, which is not in the list.
- "About 1,300–1,700 records a day" (L74) has no source in the brief. P2-06 uses 1,300.
- "20–30 near-miss out examples" and "about 40 anchors" (L80–81) are design numbers. `config/anchors.yaml` has 37 IDs.
- "The cheapest model that meets the target wins" (L96) is a decision rule, not a finding.
- "Add kNN-to-anchor similarity as a feature" (L86) is carried from v2 and has no new evidence.

### Conflicts with tests (feature_list.json)
1. **P2-02 ordering vs uncertainty-sampled H0 (L95).** P2-02 creates the 150 review items ("stratified by label") *before* any scorer exists: P2-05 (the T1 classifier) depends on P2-04 = Gate H0. "The ones the scorer is least sure about" cannot be computed at P2-02. Fix: state the uncertainty source available at P2-02, for example:
   - disagreement between the cheap-LLM label and the anchor/citation heuristic, or
   - a throwaway TF-IDF+LR model fitted on the bootstrap labels.

   Keep the 150 stratified by label so the P2-02 test still holds.
2. **P2-05 evaluation bias.** P2-05 needs held-out recall ≥ 0.95 and precision ≥ 0.6. If the held-out set is the uncertainty-sampled H0 labels, the estimate is biased toward hard cases, and there is no clean held-out set. Fix: reserve a random (or stratified-random) held-out slice for the P2-05 test, and use the uncertainty-sampled labels for training and threshold tuning only.
3. **P2-05 is tested on T1 alone.** The test belongs to P2-05, the embedding classifier, which must pass *before* P2-06 adds the LLM layer. The fallback "if that falls short, two cheap models vote" (L90) cannot help pass P2-05. The evidence (Scholar Inbox F1 ~0.85; SESR-Eval) suggests 0.95 recall at 0.6 precision is not guaranteed. Say this explicitly as a risk, and note that the plan needs a pre-agreed action if P2-05 misses (per CLAUDE.md: log it and stop).
4. **P2-05 description** says "SPECTER2 embeddings to pgvector". If TF-IDF or GTE-Large wins the bake-off, the implementation departs from the description. This is not a test conflict, but the coding agent will see a mismatch. Mehar should approve the deviation in `claude-progress.txt`.
5. **The plan's "Tests (unchanged)" list (L98–99) is incomplete.** It omits:
   - P2-01 (unit tests)
   - P2-02 (label source per label; 150 items stratified by label)
   - P2-03
   - P2-05 (model artifact saved with version and metrics)
   - P2-06 (cap overflow queued by priority, none dropped)

   Either list them all or say "selected".

### Online spot-checks (Step 2)
| Claim | Result |
|---|---|
| Scholar Inbox: GTE-Large, PCA 256, LR, 5k negatives, F1 84.51, AUC 86.75, TF-IDF nDCG 88.67 (arXiv 2504.08385 Table 2) | **Verified.** Note that the Fig. 5 caption gives TF-IDF nDCG as 88.2. |
| Scholar Inbox ~23k users | **Verified** (registered users; dataset 14.3k) |
| SESR-Eval: none reached recall > 0.95 at precision 0.50; smallest models poor; o3-mini not better; threshold matters | **Verified** (arXiv 2507.19027 HTML). The **~10x output tokens** figure was **not** visible in the fetched text and is unverified. |
| ASReview WSS@95 92.77% (medRxiv 2025.10.13.25337935) | **Not verified.** The fetch was blocked (permission prompt not answered). |
| Compact LLMs, Gemma 2 9B ~82–87 req/min on RTX A2000 (PMC12873614) | **Not verified.** The PMC page returned a CAPTCHA. The paper exists (Cambridge / Research Synthesis Methods). |
| ISPOR 83% / 56%; Oxford ensembles | Not checked |

---

## Step 3 — Parse (L110–179)

### Correct
- Fixture evidence L165–169 matches the brief:
  - HTML for 20/20
  - 19 with 0 `ltx_ERROR`; MetaGPT had 8
  - 1,478 of 1,479 citations linked (99.9%)
  - 1,343 of 1,346 references with a title block = 99.78% ≈ "99.8%"
  - 32% of references carry an arXiv ID
- S2ORC title scoring (L147) is verified online (Lo et al., ACL 2020, §2.6):
  - normalised titles, as character 3-grams
  - harmonic mean of Jaccard and containment (containment = |∩| / min(|N1|, |N2|))
  - highest pair above **0.8**, otherwise left unlinked
- "~97% produce some HTML, ~75% with no conversion errors" (L176) is verified online in arXiv 2605.16562: "About 97% of submissions currently produce some HTML" (described as an "availability ceiling rather than a quality claim") and "roughly 75%" error-free, with a target of 90%.
- No LLM in the step, and Marker LLM mode off (L110, L152): matches the brief.
- "GROBID ranked mid-pack" (L179) matches the brief.

### Errors
| Plan text | What the source says | Suggested fix |
|---|---|---|
| L177 "unarXive ... links only about 44–48% of references" | **44.4% of references** and **48.3% of in-text citation markers** (verified online, unarXive 2022 §Matching). 48% is a marker rate, not a reference rate. | "links 44.4% of references (48.3% of citation markers) to OpenAlex" |
| L177 "unarXive (Tralics + GROBID + OpenAlex)" | The pipeline is latexpand + Tralics + GROBID (reference parsing) + OpenAlex (matching). | Add latexpand (minor). |
| L170 "arXiv title search matched 17 of 25 sampled references" | 17/25 **after title cleaning**; the first pass got 11/25. | "17/25 after cleaning (11/25 first pass)". This shows the cleaning step matters. |
| L178 "S2ORC's title-linking method is the proven one" | S2ORC reports **no precision or recall for the 0.8 linking threshold**. Its Table 6 "title accuracy 1.00" measures title *parsing*, not linking (verified online). | "S2ORC's widely used title-matching rule (no published link precision; we measure it with 50 hand-checked links)" |
| L176 "about 97% of submissions produce some HTML" | Correct as quoted. The source adds that ~10% of arXiv articles are PDF-only (no TeX) and that 97% is an availability ceiling. | Add: "~10% of arXiv is PDF-only, so the PDF fallback is not rare." |

### Missing
- **Anystyle** was the best reference parser in the comparison (arXiv 2205.14677; online check confirms Anystyle best, Cermine second). The plan uses GROBID for the PDF fallback (L151) without noting this. At minimum, record it as a considered alternative for reference-string parsing in fallbacks (a) and (b).
- **Use S2/OpenAlex reference lists as a linking source.** The Store report says to use OpenAlex/Semantic Scholar reference lists rather than arXiv LaTeX alone, because unarXive resolved only 44.4%. P1-04 already collects references. Linking step 7 (L145–149) goes ID → arXiv title search → OpenAlex/S2 title lookup and never uses the enriched reference list. Add "match against the S2/OpenAlex reference list for this paper" before the per-reference arXiv search.
- **Rate-limit cost of arXiv title search** (my inference, not from a source). About 68% of references lack an arXiv ID. Searching each at ≥3 s/request means roughly 30–60 s per paper, and tens of hours over a multi-thousand-paper backfill. The plan should state the budget or prefer the S2/OpenAlex list.
- **Fixture provenance.** P3 tests run offline, but the HTML for the 20 fixtures is not part of the P0-07 fixtures (LaTeX + PDF). Fetching and recording it is needed and should be noted.

### Unsupported / assumptions
- The quality-gate thresholds "abstract, ≥3 sections, a reference list" (L133) are design choices.
- "The misses were mostly not on arXiv" (L170) is not in the stated conclusions, so it is unverifiable here. Keep it only if the in-conversation test showed it.
- Section types from keyword rules, the sentence splitter, and math as `alttext` (L136–142) are design choices, not findings. That is fine, but they are not "researched".

### Conflicts with tests
1. **P3-02 is titled "LaTeX parser"**, with the description "Multi-file resolution, macro stripping, section tree, bibliography and \cite resolution". **P3-03 is "LaTeX table extraction"**. The plan makes HTML primary and LaTeX "fallback (a)" (L151, L173). The test steps (≥95% cite resolution; ≥90% of tables with the correct cell count) are satisfiable by the HTML path. The 1,478/1,479 figure suggests the cite test passes. But under CLAUDE.md the coding agent must implement the feature *as described* and may only edit `passes`. Either:
   - (a) implement P3-02/P3-03 as the LaTeX parser (fallback (a)) and treat the HTML parser as unlisted work, or
   - (b) have Mehar formally amend the titles and descriptions.

   The plan's claim that "the feature list ... stay[s] the same" (L7) is true only for test_steps, not for what the features describe. Also, P4-02 depends on P3-02 and P4-04 depends on P3-03, so the HTML path would have no feature gating it.
2. **P3-04 "3 PDF-only fixtures"** (ToolLLM, MetaGPT, MemGPT per `claude-progress.txt` L173) are listed as having arXiv HTML (L165, "20 of 20", and MetaGPT has 8 errors). An HTML-first pipeline would never take the PDF path for them. The test must force the fallback (for example `source=pdf`). State this.
3. **P3-05** requires the report to contain "availability %, failure categories, timing", and the description says "Measure LaTeX availability". The plan's report additions (L162) cover reference-link coverage. Make sure the report includes **both HTML and LaTeX availability %** so the description and test are met.
4. **L156–160 "Tests (unchanged)"** says "Parsing report on 500 papers". The test step only checks report contents (the 500-paper sample is in the description). Fine, but say which is the test.

---

## Step 4 — Read (L183–249)

### Correct
- LLMEvalDB 98.8% value accuracy from table source plus a schema (L242).
- SciER prompted 38–41 vs 61–66 tuned; pipeline 41.2 vs joint 34.9 (34.87) (L243).
- "Extends" ≈ 4% (3.7%) (L244).
- Intern-Atlas 70.4% vs 93.0% (L246).
- The NoLiMa early drop (L247).
- Field order matters (Tam et al.) (L248).
- Section routing table (L191–196): matches the report's "Context" paragraph and design table.
- Per-reference classification, strongest relation kept, ±1 sentence, section label, cited abstract, `isInfluential` only for ranking, high-recall pass for rare types, `evaluates_on` / `compares_against` from code (L205–213): all match the recommended design.
- Pass C (L215–220) matches:
  - per-cell records
  - "not stated" settings
  - caption as an input, not ground truth
  - value equals normalized cell text
  - header-path check
  - no ranking across unknown/known harness
  - keep every row (Timmer)
- Evidence-first field order, Pydantic, one retry, mini-tier bulk, reasoning off except edge typing, and measuring recall (L223–225) all match.
- "Well under $1 per paper" (L226) matches the Extraction report's cost paragraph.
- Re-label 10–20% of dev papers blind after ≥2 weeks; split by paper; oversample rare types (L232–234): from the Check report.

### Errors
| Plan text | What the source says | Suggested fix |
|---|---|---|
| L245 "MultiCite: ±1 sentence is the best fixed window; section labels help." | ±1 is MultiCite's finding. "Section labels help" is **Cohan et al. 2019**: the section scaffold raised ACL-ARC "Uses" F1 from 65.4 to 75.0. | "MultiCite: ±1 best fixed window. Cohan et al. 2019: section labels raised Uses F1 65.4→75.0." |
| L244 "GPT-4 scores 50 vs 76 for fine-tuned models on ACL-ARC" | 50.18 is **five-shot**; zero-shot is **38.55**. Fine-tuned: 75.57 (MTL SciBERT), 76.35 (Falcon-7B, July 2026 preprint). | "GPT-4 38.6 zero-shot / 50.2 five-shot vs ~76 fine-tuned" |
| L249 "arXiv 2510.01235: mini-tier models within about 2 F1 of frontier, but they lose recall." | GPT-4.1-Mini 0.889 vs GPT-4.1 0.909 micro-F1. The recall loss is reported for **Gemini 2.0 Flash** (P 0.903, R 0.695), not for the mini model. | "GPT-4.1-Mini within ~2 F1 of GPT-4.1. Gemini 2.0 Flash kept precision but lost recall (0.695)." |
| L246 "Intern-Atlas: ... cheap model 70.4% vs audit model 93.0% on edge types" | Accuracy is measured by its own audit model (Claude Sonnet 4.6). There is no human P/R or agreement, and it is a preprint. | Add "(self-audited preprint; no human agreement)". |
| L242 "LLMEvalDB: 98.8% value accuracy" | The audit covered **40 records** (2 annotators, κ 0.68). The report says to read it as "very high", not exact. | Add "(40-record audit)". |
| L208 Pass B LLM types include **`uses_artifact`** | The Check report (stage 1, "Deterministic types") and P4-05 make `uses_artifact` deterministic (ID/string match + registry), with no NLI. The Extraction report's design table does list it among LLM-typed edges. | Pick one. Recommended: deterministic first (P4-05), with LLM only for blog/spec text, consistent with P4-05's description. |
| L230 "Revised estimate: 25–35 hours" | This is the Check report's **derived** estimate ("derived, not sourced"). It assumes 100 papers × ~20 facts at 45–60 s, **and** that only lineage-relevant citations are annotated. | Label it as an estimate and add the scoping rule (see Missing). |

### Missing (from the Extraction report's recommended design and conclusions)
- **Score each stage against its own gold.** The SciREX full pipeline scored 0.008 F1 while its components scored 0.57–0.71.
- **Cache every normalization/alias decision** so the LLM never re-decides an alias (Timmer et al.).
- **Normalization from a curated, closed taxonomy for results.** SciLead: closed taxonomy 55.27 vs on-the-fly 40.07. LLMEvalDB dropped LLM clustering. This should be stated in Pass C, not only in 5b.
- **Record the averaging rule** (micro vs macro moved recall by 12.61 points).
- **Settings quotes.** Each setting needs a supporting-text quote, or the field is "not stated". Look in captions, footnotes and the setup section. The plan has "not stated" but no settings quote.
- **Short, sentence-level quotes.** LongCite: GPT-4o citations averaged ~6 sentences, and same-pass citation cut correctness from 78.2 to 69.4. Consider a second evidence-finding pass for hard fields.
- **Gold-set scoping that makes 25–35 h realistic.** Fully annotate card fields and the merges those papers touch, but only lineage-relevant citations (to in-graph papers, or in method/experiment sections). Also 2–4 months at the daily budget. Without this, 100 papers ≈ 2,700 citation contexts.
- **Measure agreement before judging models.** Record self-agreement before judging any model against the gold. If a type's self-agreement is poor in the pilot, merge it into a coarser class (SciCite precedent).
- **Fine-tune / distil from verified rows.** The report's conclusion calls this the most strongly evidenced path to frontier-level edge typing at open-model cost (SFT + RL reward, not plain SFT, because of the OOD collapse 41.01→18.12). It is absent from the plan, including the thesis contributions.
- **Artifacts:** the label comes from a fixed enum, and the licence comes from repo metadata (design table). Minor.
- **Pilot gold.** The report notes ACL-ARC was built from a 10-paper pilot with two rounds of guideline refinement. The H1 30-paper pilot covers this; fine.

### Unsupported / assumptions
- L232 "or cut it to about 60 papers": no source. See the conflict below.
- L229 "the review UI, which highlights each claim in context" restates P4-06 and is fine.
- L226 "Expect well under $1 per paper with batch pricing" is the report's reasoned estimate. Mark it as an estimate until P4-07.
- Contribution 1 (L422) "with inter-annotator agreement": the Check report says that, as a solo annotator, you measure **intra**-annotator agreement and must **not** report LLM–human κ as inter-annotator agreement. Fix: "with intra-annotator (self) agreement".

### Conflicts with tests
1. **H2 size.** L232 and L413 say "or cut it to about 60 papers" / "(100 papers, or ~60)". **P4-10's test requires "data/gold/dev has 60 and heldout has 40 papers"** (100 total). Cutting to 60 fails the test. Remove the option, or note it would need a feature change approved by Mehar.
2. **Self-agreement count.** L234 says 10–20% of dev papers, which is 6–12 papers. P4-11's description says "self-agreement on 20 re-annotated papers". This is not a test step, but it is inconsistent. Use "≥20 papers (~33% of dev)" or note the change.
3. **P4-04 "value literally present in referenced cell for 100% of emitted rows".** The plan's check (L218) allows normalization including "% scaling". If a value is stored rescaled (for example 0.452 for "45.2%"), it is not literally present. Fix: store the literal cell substring as the value, with any normalized numeric in a separate field.
4. **P4-04 "rows without setting_json flagged".** The plan fills missing settings with "not stated" (L217). Make sure a row whose settings are all "not stated" is still *flagged*, so the "not stated" sentinel does not silently satisfy "has setting_json".
5. **P4-03 description** includes `confidence`. The plan omits it, and the Check report says verbalized confidence is near-useless (AUROC 0.548). There is no test conflict. Keep the field but do not use it for routing.
6. **L236–237 "Tests (unchanged)"** omits the P4-03, P4-04, P4-05, P4-06 and P4-07 steps. List them or say "selected".

---

## Step 5 — Check (L253–308)

### Correct
- Checker models and the 0.5 starting threshold (L267): MiniCheck-FT5 0.8B, FactCG-DeBERTa 0.4B, Bespoke-MiniCheck-7B.
- Thresholds tuned with a binomial bound, Trust-or-Escalate style (L268).
- Verbalized confidence not used (L272).
- ChatPD identifier rules: ban identifiers that map to ≥2 entities; new entity needs name + specific URL + ≥3 papers (L278–279).
- Version markers block "same", and no embedding merges (L281).
- Authors from S2/OpenAlex; `version_of` for preprint vs published (L283–284).
- Reversible alias-table merges with cached LLM decisions (L285).
- 15–30 min ≈ 15–40 labels (L287).
- Paper → 3–5 facts sampling (L288).
- Wilson intervals; ±10% per type (35–62); ±5% pooled (~139 at 90%) (L290).
- Blind 10–20% (L291).
- Daily stratum with a rolling 4-week window and a lower-bound alert (L292).
- `review_labels` table (L293).
- Why list: LLM-AggreFact ~75–77 and ~60 expert (59–61); 1/400 cost; MSciNLI 77.2 vs 51.8; Trust or Escalate 90.8% vs 47–79% (47.5–79.0); ChatPD P 0.983 / R 0.873 vs 0.57 (0.568); OpenAIRE ~23%; S2AND B³ 0.900 (L301–307).

### Errors
| Plan text | What the source says | Suggested fix |
|---|---|---|
| L270–271 "Disagreement → a stronger model voting over about 5 samples, then the human queue" | The **~5 samples** (Simulated Annotators, varied few-shot) belong to the **second-opinion, different-family model** (stage 3, "Agreement ≥ 4/5 to start"). The stronger LLM on disagreements is **optional** (stage 4). | "Second opinion: different-family model, ~5 samples with varied few-shot examples; promote only if checker high AND ≥4/5 agree. Disagreement → (optional) stronger model, then human queue, else stays pending." |
| L270 "Agreement → accept." | The report: promote only if the checker score is high **and** the LLM majority agrees. Agreement is a routing signal and "cannot certify precision on its own" (SciFact-Open: 4-system agreement only 60% relevant). Measure the agreeing bucket on audit. | Add the checker condition and the audit of the agreeing bucket. |
| L274 "about 20–45% of uncertain items escalated" | "At strict targets, 20–45% of **items** escalate" (Trust-or-Escalate coverage), meaning all items reaching the cascade, not just uncertain ones. | "about 20–45% of items reaching the cascade at strict targets". Add that this far exceeds 40 labels/day, so items wait as *pending*. |
| L268 "Per-type thresholds tuned on about 500 dev items" | "≥300–500 dev labels" **per decision rule**. Dev gold (60 papers) will **not** have 500 of `transplants_domain` / `refutes_or_contradicts`: pool rare types under one conservative threshold, or skip auto-promotion. | Add the rare-type rule. |
| L302 "SciTraj: ... disputes only 63%, about a third of them from 'unlike' wording" | The report says ~37% of **bad** dispute edges. The note (`claim_verification.md` L96) says "about 37% of dispute edges". The report and note disagree. | Write "~37% of dispute errors (per SciTraj's error analysis)" and check the source to settle report vs note. |
| L308 "cluster sampling cuts labelling time by up to 60–80%" | Up to **60% on static** KGs and **80% on evolving** KGs. Stratification saves up to 40% more. | "up to 60% (static) / 80% (evolving)" |
| L301 "small checkers about 75–77, level with Claude 3.5 Sonnet and GPT-4o" | Correct. The report adds that Bespoke-MiniCheck-7B's 77.4 is vendor-submitted and that none of the 11 datasets is scientific text. | Add "(no scientific-text dataset; real accuracy unknown until measured on dev gold)". |
| L282 label set "same / variant / subset / related / different" | The report's set (from MapperGPT) includes **broader**: same / variant_of / subset_of / broader / related / different. | Add "broader". |

### Missing
- **Pending, not rejected.** Uncertain items stay in `candidate_*` with a pending status. "Nothing is rejected just for being uncertain." This is one of the report's two deliberate asymmetries.
- **Merges have a higher bar than edges.** Order the routed queue by blast radius: merges → analytics-critical edges → card facts.
- **Exact `refutes_or_contradicts` hypothesis semantics.** The quote must *entail* "A reports a result inconsistent with B's claim R". An NLI "contradiction" label means the edge is wrong.
- **Hard rules the plan omits:**
  - no self-loops or duplicates
  - "no extends+refutes on the same pair without separate evidence"
  - B-in-references applies specifically to extends/combines/replaces_component
  - `replaces_component` must name a component on B's card
  - `transplants_domain` needs two different domains
  - **a review flag for very long year gaps** (SciTraj let 9/300 implausible edges through)
  - rejected rows kept with a reason code
- **Claim decomposition is not worth it** on short quotes (+0.3 / −1.4 at 2–4x cost). This is useful as an explicit "don't".
- **ER:**
  - seed the alias table from the frozen Papers with Code archive (~9,327 benchmarks / 5,628 datasets; nothing after 2025)
  - expand bracket-defined acronyms
  - continuous ambiguity alerts (one identifier → two entities; cluster-size jumps)
  - report **B³ F1 plus false merges and false splits separately** (S2AND)
  - expect ~half of dataset mentions to have no catalog entry
  - no single best ER prompt; tune per model (Peeters et al.)
- **Audit design:**
  - sample papers with probability proportional to new facts
  - strata = fact family × verifier band
  - 5–10 audit items per batch
  - store the blind flag, stratum and **sampling probability** in `review_labels`
  - make reject one keystroke, with the quote always beside the claim
  - re-run the held-out eval after every prompt, model or threshold change
  - label-free leading indicators (rejection rate, disagreement rate, per-type volume, merge spikes)
  - calibration check by confidence band
- **Calibrate on `data/gold/dev` only.** Held-out is for `eval/` (consistent with CLAUDE.md, but worth stating at the threshold step).

### Unsupported / assumptions
- **60% audit / 40% routed (L289–290)** is explicitly "my design inference" in the Check report. Label it as an assumption.
- **±10% / ±5% targets and 35–62 / 139 label counts (L290)** are the report author's own binomial arithmetic ("not from a source"). They are correct, but label them as derived.
- **"Create a new concept only when a name and a specific URL appear in at least 3 papers" (L279).** ChatPD's rule is for **datasets**. Applying it to all concept kinds (methods, harnesses, tool protocols, skill formats) is an extrapolation. Many methods have no "specific URL" and would never become concepts. Label it as an assumption and scope it, for example datasets/benchmarks only, with an alternative rule for methods.
- **L283 "Authors: reuse Semantic Scholar or OpenAlex author IDs"** is well supported. "Papers: ... normalized title + year + first author" is supported.

### Conflicts with tests and features
1. **P5-03 "every refutes edge reaches adjudication".** The plan's contradiction guard (L266) "downgrades" `refutes_or_contradicts` before the checker and second opinion. If a downgraded edge is no longer a refutes edge when routing happens, the test can fail, or pass vacuously in a way that hides the intent. Fix: route **all** `refutes_or_contradicts` candidates to adjudication first. Apply the guard as an additional downgrade-to-review rule, or apply it after adjudication. P5-03 also says "Strong tier for ... all refutes_or_contradicts", while the plan uses a cross-family model. Make sure refutes edges always get the strong tier.
2. **P5-02 "unit test of hypothesis templates for all types".** The plan and Check report make `evaluates_on` / `compares_against` deterministic and (per the Check report) `uses_artifact` deterministic, with no NLI. Decide whether "all types" means all LLM-typed edge types. Provide a template, or an explicit "deterministic — no template" entry, for every enum value so the test is well defined.
3. **P5-02 "Cross-encoder NLI (CPU-size)".** Bespoke-MiniCheck-7B is not CPU-size. FactCG-DeBERTa-0.4B fits. MiniCheck-FT5 is seq2seq, not a cross-encoder. Not a test conflict; state the default (FactCG-DeBERTa or MiniCheck-FT5 on CPU).
4. **P5-05 "Record ER with Splink" (papers, authors, repos).** The plan's 5b.5 replaces this with S2/OpenAlex author IDs and deterministic paper keys and never mentions Splink. The Check report found **no accuracy figure for Splink on bibliographic data**. The test ("pairwise precision/recall reported on fixture pairs") is still satisfiable. This is the same title/description issue as P3-02 and needs Mehar's sign-off.
5. **P5-06 "Blocking + embeddings + LLM"** vs plan L281 "Embedding similarity is never used to merge". This is compatible if embeddings are used **only for candidate generation/blocking**. Say so explicitly. P5-06's test "revert restores prior edge endpoints" is satisfied by alias-at-query-time (edges never change, so resolved endpoints revert). Note that "restores" is then about the resolved view.
6. **Auto-merge rule.** L280 "Auto-merge only on a curated alias hit" (= P5-06) vs the Check report's design table "Shared specific identifier and no marker conflict → merge". The plan is ambiguous about whether identifier matches auto-merge. Recommended: identifier merges for papers/authors/repos (deterministic keys); concepts auto-merge only on curated alias hits (keeps P5-06).

---

## Step 6 — Store (L312–385)

### Correct
- Four timestamps, generated `tstzrange` `[)`, NULL-open not `'infinity'`, explicit UTC (L315–316).
- `valid_from` = announcement of the earliest version containing the evidence, plus `source_version` (L320).
- `valid_to` closing rules; errors close pipeline time (L321–322).
- btree `(src, etype)` / `(dst, etype)`, partial current index, GiST for integrity only (L325).
- Recursive CTE with `UNION`, depth cap, type filter; stop path enumeration over citations beyond depth 4 (L326). This is equivalent to the report's "depth ≥ 5 is the point to stop".
- No AGE (L327).
- Strict freeze rationale (L336); UNLOGGED snapshots plus registry (L337); ADBC export plus progress note (L338).
- Daily run ~00:30 ET after 20:00 ET / ~22:30 ET; holiday calendar (L346).
- Atomic `promote(run_id)`; cache key; at-least-once (L347–349).
- Weekly forward rescan (L350); monitoring list (L351–356); monthly restore drill (L357).
- Cost arithmetic (L360) checks out:
  - Haiku 5.5 batch $0.05/$0.25 per MTok: 20k×0.05/1e6 + 2k×0.25/1e6 = $0.0015/paper = $15 per 10k
  - Sonnet 5.5 batch $1/$5: $0.03/paper = $300 per 10k
- Benchmark table (L371–377) matches: ~0.1 ms/node; 7.0 ms; 1.21 s; 238 ms + ~420 ms < 1 s; PageRank 63–90 ms vs 2.8 s.
- Why list: 38–151% inflation, HindSight cutoff, PreScience, Graphiti/Zep (L382–384).

### Errors
| Plan text | What the source says | Suggested fix |
|---|---|---|
| L343 "Backfill newest first" | "**Anchors first, then newest-first by month**" (runbook phase 4; note `backfill_daily_ops.md` L47–52) | "Anchors (and their 1-hop references) first, then newest-first by month" |
| L343 "Anthropic batches ... finish within 24 h" | 24 h is a **target window**. Requests not processed within 24 h **expire** ("most finish under 1 h" is a vendor claim). Results are kept 29 days; the limit is 100k requests **or 256 MB**. | "aim to finish within 24 h; unfinished requests expire and must be re-queued" |
| L343 "batch and caching discounts stack" | True, but **cache reads in batches are best-effort, 30–98% hit rate**, and the 1-hour cache is recommended. | Add the hit-rate caveat. |
| L317 "a trigger allows only `superseded_at` to change from NULL to a value" | The trigger allows `superseded_at` NULL→value **plus `superseded_by` / `supersede_reason` set in the same statement**, and there is no DELETE grant. | Include those columns. Otherwise the trigger blocks setting `supersede_reason`. |
| L317 supersede_reason list "extraction_error / world_change / merge" | The schema CHECK also has **`schema_migration`** (prompt/schema re-derivation). | Add `schema_migration`. |
| L331–335 strict freeze "paper versions announced before T", "merge evidence dated before T" | The source rules are announcement **≤ T** and `evidence_date ≤ T`. Strict mode **flags** (does not necessarily drop) rows whose model cutoff is later than T. | Use ≤ and state flag vs exclude. |
| L337 "Past snapshots are immutable" | Immutable **for R in the past**. A snapshot at R = now changes as promotes continue. | "Snapshots with R < now are immutable and cached." |
| L357 "encrypted Cloudflare R2" stated as settled | The report and notes: "Cloudflare R2 pricing and pgBackRest-on-R2 settings (path-style URIs) were **not verified**." | Mark R2 as "S3-compatible, e.g. R2 (settings unverified)". |
| L360 "$15 per 10k ... (assuming ~20k input / 2k output tokens per paper)" | This is the author's illustrative arithmetic. The Extraction report says per-reference edge typing (~21 references/paper) is the cost driver, so one 20k/2k pass per paper likely undercounts Passes A+B+C. | Say "per extraction pass". Multiply by passes, or wait for the P4-07 / 200-paper pilot numbers. |
| L369 "Measured on a 1M-edge synthetic graph (PG16)" | Correct, and the report also notes: 2 vCPU / 7 GB, shallow synthetic lineage (~1.5 lineage out-edges/node), **benchmark scripts not kept**, GiST insert overhead during promote not measured. | Add "scripts not kept; re-run on the real graph; time the first big promote". |

### Missing
- **Scope = union of filter and 1-hop snowball from anchors**, with out-of-scope works as metadata-only stubs (runbook phase 1). L341 says only "Metadata harvest for the slice". L345 mentions "upgrade stub nodes" without ever creating stubs.
- **`paper_version` needs `announced_at` and `submitted_at`**, from an OAI-PMH `arXivRaw` harvest. Keep `first_public_date` as a separate paper attribute; a journal version adds evidence and never resets `valid_from`. v2's `paper_version.published_at` is ambiguous.
- **No silent time defaults.** Every query function takes explicit T and R; "current" is a named convenience. The API echoes `(T, R, strict)`. Outputs at R = now are labelled "reconstruction", not "forecast evidence".
- **Strict mode leakage channels left out:**
  - the **retrieval filter inside eval tasks** (PreScience: drop dated ≥ T, same title, near-duplicate text)
  - evaluate on global time windows, never random edge splits
  - report results **with and without strict mode** to measure hindsight
- **Batch robustness:**
  - `custom_id` = sha256(content_hash, prompt_id@version, model) cut to 64 characters
  - write an `llm_batch` row before submitting
  - re-queue errored/expired requests and dead-letter invalid ones
  - dry-run every new request shape on the sync API
  - **Gemini returns nothing for jobs that expire at 48 h**, so keep Gemini batches small (relevant because Gemini is a candidate tier)
- **Logical edge plus `edge_evidence`.** One logical edge per (src, dst, etype), with per-paper evidence in `edge_evidence`. This is the author's design choice, and the exclusion constraint depends on it.
- **Daily ops:**
  - Sunday–Thursday announcement nights
  - OAI incremental with `from` = last server-reported date and no `until`
  - new versions → re-extract and supersede
  - check `deletedRecord` support via `Identify` before trusting withdrawal detection
  - monitoring thresholds: ±50% or ±3 MAD vs the 4-week same-weekday median
- **pgBackRest details:** WAL archiving/PITR, `repo2-cipher-type` fixed at creation, `pg_create_restore_point('run_<id>')`.
- **Hypothesis `RuleBasedStateMachine`.** Boundary-drawn invariants: T and R on bounds and at ±1 µs; timezone independence; CTE paths equal networkx.
- **psycopg fallback** (~0.5 s) if ADBC is not wanted.
- **Thesis framing.** The earliest stable daily runs are the only honest pipeline-time data. Compare "known then" against the R = now reconstruction to measure hindsight.

### Unsupported / assumptions
- "Snapshots are UNLOGGED" and "Export: ADBC → ... cached as Parquet" are the report's recommendations from a local micro-benchmark. Fine, but they are not externally evidenced.
- L384 "PreScience: as-of metrics and date filters" is correct. PreScience does not say which arXiv version it keys on, so the version rule is the report author's own, stricter choice.
- Leakage contribution (L424): the report says these leakage channels are "reasoned risks, not quantified". The plan presents them correctly as a contribution to measure.

### Conflicts with tests
1. **P6-05 "freeze(2025-12-31)" with one argument** vs the plan's `freeze(T, R, strict)`. The report also recommends no silent R default. Backfill rows have `recorded_at` = backfill date, so the test must use R = now (or after the backfill). Make the convenience explicit (for example `freeze_reconstruction(T)`, or the test passes R = now) and state which `strict` value the 70% check uses.
2. **P6-02** "no rows with valid_from > T". With the version-level `valid_from` this holds. Strict mode's extra filters must not *add* rows. Fine.
3. **P6-01** "superseding an edge sets superseded_at and inserts new row". This works only if the trigger permits `superseded_by` / `supersede_reason` (see Errors).
4. **L362–367 "Tests (unchanged)"** omits P6-01 ("migration applies"; the supersede test) and P6-03 ("progress report written"). List them or say "selected".
5. **P6-01 table list** (`concept, concept_alias, merge_event, edge, result`) vs the plan's bitemporal alias table (L285 / Store report `entity_alias`). This is compatible if `concept_alias` / `merge_event` carry `recorded_at` / `superseded_at`. State the mapping.

---

## Cross-cutting / plan-level

- **L7 "The feature list and every acceptance test stay the same."** True for `test_steps` (`feature_list.json` is unchanged in git). But the titles and descriptions of P2-05 (SPECTER2), P3-02 and P3-03 (LaTeX), and P5-05 (Splink) now describe a different implementation, and the H2 "~60 papers" option contradicts P4-10. Under CLAUDE.md the coding agent will stop on these. Add a short "Feature-description deviations needing Mehar's approval" section.
- **"Tests (unchanged)" blocks** in Steps 2, 3, 4 and 6 list only some test steps. Rename them "Key tests (unchanged)", or list all.
- **Two different review-label stores.** `review_item` (v2 / P2-02 / P2-03) and the new `review_labels` (L293). Say whether `review_labels` extends `review_item` or replaces it.
- **Steps 7–12 table (L393–400).** It matches v2 and the feature list. Not audited further.

---

## Prioritized fix list

**P1: conflicts with acceptance tests or hard rules (fix before the coding agent reaches these features)**
1. **H2 size.** Remove "or cut it to about 60 papers" (L232, L413): P4-10 requires 60 dev + 40 held-out. Make the 25–35 h estimate realistic with the report's scoping rule instead (full card fields and merges; lineage-relevant citations only).
2. **H0 uncertainty sampling.** Define an uncertainty source that exists at P2-02 (before any T1 model), keep the 150 stratified by label, and **reserve a separate random held-out set** for the P2-05 recall/precision test.
3. **Refutes routing.** Ensure every `refutes_or_contradicts` candidate reaches strong-tier adjudication (P5-03) before or regardless of the "unlike" guard.
4. **Feature-description deviations.** P3-02/P3-03 (LaTeX → HTML-first), P2-05 (SPECTER2 → bake-off), P5-05 (Splink → S2/OpenAlex IDs plus deterministic keys). Get Mehar's sign-off and log it in `claude-progress.txt`. Note that P3-04 must force the PDF path, because the "PDF-only" fixtures have HTML.
5. **P4-04 literal-value test.** Store the literal cell substring as the value. Keep normalized numbers in a separate field. Still flag rows whose settings are all "not stated".
6. **Append-only trigger.** Allow `superseded_by` / `supersede_reason` with `superseded_at`, and add `schema_migration`. Otherwise P6-01 supersede logic is blocked.
7. **P6-05 freeze signature.** Make R (= now, labelled "reconstruction") and `strict` explicit for `freeze(2025-12-31)`.
8. **P5-02 "templates for all types".** Define a template or an explicit "deterministic, no template" entry for every edge enum value. Resolve whether `uses_artifact` is LLM (L208) or deterministic (P4-05, Check report).

**P2: factual errors and misattributions**

9. L177 unarXive "44–48% of references" → 44.4% of references / 48.3% of citation markers.
10. L245 "section labels help" → Cohan et al. 2019 (Uses 65.4→75.0), not MultiCite.
11. L249 recall loss → Gemini 2.0 Flash (R 0.695), not the mini model.
12. L270–271 the 5-sample vote belongs to the second-opinion model, and promotion needs checker-high **and** ≥4/5 agreement. The stronger model is optional.
13. L274 "20–45% of uncertain items" → "of items reaching the cascade at strict targets". Add pending status.
14. L343 "Backfill newest first" → anchors first, then newest-first. "Finish within 24 h" → 24 h target, then expiry.
15. L105 ASReview "saves ~93% of reading" → WSS@95 ≈ 93% (work saved over random sampling; medical reviews).
16. L244 GPT-4 "50" → 38.6 zero-shot / 50.2 five-shot.
17. L170 17/25 → "after cleaning (11/25 first pass)". L96 Gemma → "Gemma 2 9B on an RTX A2000 12 GB".
18. L302 SciTraj "a third of them". Report (bad dispute edges) and note (dispute edges) disagree; check the source.
19. L422 "inter-annotator agreement" → intra-annotator (self) agreement.

**P3: overstatements to soften and assumptions to label**

20. L178 "S2ORC's ... method is the proven one". There is no published link precision; the plan's 50 hand-checked links are the measurement.
21. L106 "score plus tuned cut-off ... helped". No study reached 0.95 recall at ≥0.5 precision. State the P2-05 risk and the stop rule.
22. Label as assumptions or derived:
    - the 60/40 audit split
    - the ±10/±5% label counts
    - the 25–35 h estimate
    - the ≥3-paper new-concept rule applied beyond datasets
    - the category allow-list
    - the 1,300–1,700/day figure
    - quality-gate thresholds
    - the R2 backup target (unverified)
    - the $15/$300 cost (one pass, illustrative; Haiku price to confirm)
    - the local PG16 benchmark (scripts not kept)
23. Add caveats: Intern-Atlas is self-audited; LLMEvalDB's audit had n = 40; Bespoke-MiniCheck's 77.4 is vendor-submitted with no scientific-text dataset; the ~10% of arXiv that is PDF-only.

**P4: important missing recommendations**

24. Scope union of the filter and a 1-hop anchor snowball, with stubs (Step 2 Layer 1 and Step 6 backfill item 1).
25. Use S2/OpenAlex reference lists in reference linking before rate-limited arXiv title search. Budget the 3 s/request cost.
26. Step 5:
    - pending status and blast-radius queue order
    - rare-type threshold pooling (dev gold lacks 500 per type)
    - the remaining hard rules (self-loops, long-gap flag, type constraints)
    - the refutes entailment semantics
    - the Papers with Code alias seed
    - B³ plus false merges and splits reported separately
    - the ambiguity alerts
    - sampling probability recorded in `review_labels`
    - re-running the held-out eval on every prompt, model or threshold change
27. Step 4:
    - per-stage gold scoring (SciREX)
    - normalization caching
    - closed taxonomy for result normalization
    - averaging rule recorded
    - settings quotes
    - sentence-level quotes
    - the fine-tune/distil-from-verified-rows path (also as a thesis contribution)
28. Step 6:
    - `announced_at` / `submitted_at` / `first_public_date`
    - explicit T/R in every query and API echo
    - PreScience retrieval filter
    - with/without-strict reporting
    - batch `custom_id` / `llm_batch` / re-queue / dry-run
    - small Gemini batches
    - `edge_evidence`
    - Sunday–Thursday calendar and OAI `from`-only incrementals
    - `deletedRecord` check
    - MAD alert thresholds
    - Hypothesis state-machine invariants
29. Step 3: record Anystyle as the best-ranked reference parser for the fallback paths. Fetch and record the HTML fixtures for offline tests.

---

## Online sources checked
- Scholar Inbox, arXiv 2504.08385 (HTML): verified
- arXiv HTML Papers report, arXiv 2605.16562 (HTML): verified 97% / 75%, ~10% PDF-only
- unarXive 2022, arXiv 2303.14957 (ar5iv): verified 44.4% / 48.3%, latexpand / Tralics / GROBID / OpenAlex
- S2ORC, ACL 2020 (aclanthology 2020.acl-main.447): verified 3-gram Jaccard/containment harmonic mean, >0.8; no link precision reported
- SESR-Eval, arXiv 2507.19027 (HTML): verified main claims; ~10x token figure not seen
- Reference-parser comparison, arXiv 2205.14677 (abstract): verified Anystyle best, Cermine second; GROBID rank not in abstract
- Not verified: ASReview medRxiv 2025.10.13.25337935 (fetch blocked); compact LLMs PMC12873614 (CAPTCHA); ISPOR 2025 calibration; Oxford ensembles
