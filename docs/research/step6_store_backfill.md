# Append history, freeze honestly, promote daily

**Short answer:** store every verified edge and result row in one ordinary PostgreSQL 17 table that carries two time ranges. The first, `valid`, records when the fact was true in the literature. The second, `sys`, records when your pipeline believed it (`[recorded_at, superseded_at)`). Never update a fact in place. To change something, close the old row's `sys` and insert a new row, inside the same transaction that promotes a day's verified candidates. For an arXiv claim, `valid_from` should be the date of the **earliest version whose text contains the evidence**, not v1 and not the journal date. Close `valid_to` only for withdrawal, removal in a later version, a verified refutation, or a superseded state such as "SOTA on benchmark B". Never close it because newer work exists, and never close it to fix an extraction error. Errors close `sys` instead. Merges live in a reversible alias table, so edges never get rewritten. At your scale, plain btree indexes do the reading and a GiST exclusion constraint does only the integrity checking. A local benchmark on 1.2M edge rows measured **~0.1 ms per node for as-of lookups, 7 ms for 20 depth-10 lineage queries, 1.2 s to materialize a 1M-edge freeze(T, R) snapshot, and under 1 s to load it into igraph**. Run the backfill anchor-first and newest-first through 50%-off batch APIs, with one atomic promote per run. Schedule the daily job after arXiv's ~22:30 ET metadata refresh. Use pgBackRest for continuous backups. The one trap to design around from day one: because the whole 2022–now backfill is recorded *today*, transaction time cannot make backtests honest for that period. Leakage control for freeze(T, R) must therefore come from valid time, as-of metric snapshots, merge evidence dates, and model knowledge cutoffs.

## The key decisions and numbers at a glance

Numbers marked "local" come from a micro-benchmark run during this research. It used PostgreSQL 16.15, because PG17 was not available in the sandbox; the plans involved should be the same or faster on 17. Hardware was 2 vCPU and 7 GB RAM, and the data was a synthetic citation-like DAG with 100k nodes, 1.0M logical edges, and 20% of edges superseded once (1,200,132 rows). Treat these as order-of-magnitude figures. The benchmark scripts were not kept, so re-run the measurements on your real graph.

| Decision | Recommendation | Number / evidence |
|---|---|---|
| Time model | Four fields per row (`valid_from/valid_to`, `recorded_at/superseded_at`), stored as two generated `tstzrange` columns with `[)` bounds, where open means an unbounded upper bound | Same shape as SQL:2011 and Graphiti/Zep ([Jungwirth](https://illuminatedcomputing.com/posts/2019/08/sql2011-survey/); [Zep](https://arxiv.org/html/2501.13956v1)) |
| `valid_from` for arXiv claims | Date of the earliest version containing the evidence, with `source_version` stored alongside | arXiv versions are permanent, and withdrawals are new versions ([arXiv](https://info.arxiv.org/help/versions.html)) |
| When to close `valid_to` | Withdrawal, removal in a later version, verified refutation, superseded *state* | Never for "A extends B" or "A cites B" |
| Corrections vs world change | Error: close `sys`. World change: insert a new version with `valid_to` set | Wikidata separates "ended" from "wrong" ([Wikidata](https://www.wikidata.org/wiki/Help:Qualifiers)) |
| Merges | Bitemporal `entity_alias` rows, resolved at query time; edges keep source ids | Unmerging = closing one row |
| Postgres version | Stay on 17. Transaction time is hand-managed in every release; PG18 only adds valid-time `WITHOUT OVERLAPS` and `PERIOD` FKs | [PG18 docs](https://www.postgresql.org/docs/18/sql-createtable.html) |
| Read indexes | btree `(src, etype)`, `(dst, etype)`, plus partial `WHERE upper_inf(sys)` | Local: 4.3–4.9 ms per 50-node batch vs 340–410 ms *per node* with no index |
| Integrity | GiST `EXCLUDE (src =, dst =, etype =, valid &&, sys &&)` | Local: GiST build 12–13 s and 100 MB vs btree 0.5 s and 12 MB |
| Lineage paths | Recursive CTE with `UNION`, depth cap and `etype` filter; igraph for whole-graph work | Local: 20 ancestor queries at depth ≤10 in 7.0 ms; all-paths over `cites` explodes ~10x per hop |
| Snapshots | `UNLOGGED` table per (T, R) plus registry; one materialized view for "current" | Local: 1.21 s for 1.0M edges; matview refresh 0.94 s (3.31 s concurrently) |
| Export | ADBC to Arrow to numpy to `ig.Graph(n, edges)`, cached as Parquet | Local: 238 ms fetch + ~420 ms build; igraph PageRank 63–90 ms vs networkx 2.8 s |
| Batch LLM | Anthropic or OpenAI batch at 50% off, deterministic `custom_id`, small daily batches | Anthropic: 100k requests / 256 MB per batch, results kept 29 days ([docs](https://platform.claude.com/docs/en/build-with-claude/batch-processing)) |
| Scope | Category/keyword filter **plus** 1-hop snowball from anchors, then triage | Either method alone: 30–80% recall; union: 100% at 1–3% precision ([Mourão et al.](https://arxiv.org/pdf/2004.09741)) |
| Daily schedule | ~00:30 ET, Sunday–Thursday announcement nights, arXiv holiday calendar encoded | Announcements 20:00 ET; OAI-PMH refresh ~22:30 ET ([arXiv](https://info.arxiv.org/help/availability.html)) |
| Backups | pgBackRest, local + S3-compatible repo, WAL archiving, monthly restore drill | Full/diff/incr + PITR ([pgBackRest](https://pgbackrest.org/user-guide.html)) |

## Two clocks, four columns, and rules for when each one moves

Bitemporal modelling is old and well-understood. SQL:2011 calls the two axes application time (when something was true in the world) and system time (when the database recorded it). Both are closed-open periods built from two timestamp columns ([Jungwirth, SQL:2011 survey](https://illuminatedcomputing.com/posts/2019/08/sql2011-survey/)). The closest modern analogue to your graph is Graphiti/Zep, a vendor-authored preprint. It gives every edge exactly the four fields you already have in CLAUDE.md: t_valid/t_invalid for world time and t′created/t′expired for ingestion time ([Zep paper](https://arxiv.org/html/2501.13956v1)). XTDB, a production bitemporal database, uses the same start-inclusive, end-exclusive convention ("T1 ≤ time < T3") and treats null as "until further notice". Its docs carry a warning worth taking to heart: when defaults hide time, people forget history exists, so every query must pick its time axis on purpose ([XTDB docs](https://docs.xtdb.com/about/time-in-xtdb.html)). In your system that means **no query function without explicit T and R parameters**. "Current" should be a named convenience that passes T = R = now, not a silent default.

One Postgres detail decides whether boundary bugs creep in. A range with a *missing* upper bound (`[x,)`) is unbounded and contains everything. The timestamp *value* `'infinity'` is a different thing: `[x,infinity)` excludes `infinity` itself ([PG17 range types](https://www.postgresql.org/docs/17/rangetypes.html)). Pick the missing bound and store `valid_to`/`superseded_at` as NULL for "open". `tstzrange(from, NULL, '[)')` then produces exactly that, and `upper_inf()` tests it cleanly. Also fix the session timezone. In the local benchmark, a literal `'2025-12-31'::timestamptz` was silently read in the server's local zone (rendered `-06`). Always pass `…Z` timestamps or `SET TimeZone='UTC'`.

### What valid_from means for an arXiv paper

No standards body defines the valid time of a scholarly claim, so this is a design choice you should write into PLAN.md. arXiv makes the choice easy to defend. Every replacement or withdrawal creates a new version under the same ID, full text is kept for every version, and "each version of a work is considered a permanent part of the scientific record and may not be removed" ([arXiv versions](https://info.arxiv.org/help/versions.html)). A claim that first appears in v3 was therefore unreadable before v3. If `valid_from` were v1's date, freeze(T) for any T between v1 and v3 would show the field a claim it could not yet see. That is leakage. The rule: **`valid_from` = the date of the earliest version of the asserting paper whose text contains the supporting quote**, derived in code from a `paper_version` table, never by the LLM. PreScience, AI2's recent forecasting benchmark, keys on "date of arXiv posting" but does not say which version ([PreScience](https://arxiv.org/html/2602.20459)). Your rule is stricter and still simple.

The research notes propose the version's *submission* timestamp. I'd tighten that to the version's **announcement** time and keep submission time as a second column. arXiv announces at 20:00 ET, Sunday to Thursday only, and a paper submitted on a Friday afternoon is not public until Monday evening ([arXiv availability](https://info.arxiv.org/help/availability.html)). The gap is at most a few days, but announcement is when the field could actually read the paper, and day-level freeze dates make that boundary visible. Keep `first_public_date` (the earliest of arXiv v1, venue online date, and proceedings date) as a separate paper attribute. A later journal publication adds an evidence row; it does not reset `valid_from`.

### When to close an interval, and which one

The hardest rule to get right is telling "the field moved on" apart from "we were wrong". Wikidata models these separately. Time-bounded truths get start and end qualifiers (Louis XIV was king from 14 May 1643 to 1 September 1715), and disputed or wrong values are handled through rank ([Wikidata qualifiers](https://www.wikidata.org/wiki/Help:Qualifiers)). Translated to your columns:

| Situation | What changes | `valid` | `sys` | `supersede_reason` |
|---|---|---|---|---|
| Extraction was wrong | Old row closed, corrected row inserted (or nothing) | Copied/adjusted on the new row; **never** end-dated | Old row gets `superseded_at = run time` | `extraction_error` |
| Paper withdrawn, or claim removed in vN | New version of the row | `valid_to` = that version's date | Old row closed | `world_change` |
| Verified refutation or erratum | New version | `valid_to` = refuting paper's first-public date | Old row closed | `world_change` |
| State superseded ("SOTA on B", "dominant method") | New version | Old state's `valid_to` = new holder's `valid_from` (contiguous `[)`) | Old row closed | `world_change` |
| Newer work extends or outperforms | Nothing | Stays open | Unchanged | — |
| Entity merge or unmerge | Alias row only | — | Alias row opened/closed | `merge` |
| Schema or prompt migration re-derives a row | New row | Same | Old row closed | `schema_migration` |

Getting the first row wrong is the most damaging mistake. If an extraction error is "fixed" by setting `valid_to`, then freeze(T) for earlier T will still show the error as if it had once been true in the literature. Two kinds of facts also need to stay apart. *Claims made by a paper* ("A extends B", "A reports 71.2 on SWE-bench Verified") are true from the paper's date onward and mostly never close. *Field-level states* (current SOTA holder) are aggregates, and they get closed when superseded. Compute the states from the claims at query time, or materialize them in their own bitemporal table. Graphiti invalidates edges with an LLM and always lets new information win ([Zep paper](https://arxiv.org/html/2501.13956v1)). Do not copy that. Newer results often coexist with older ones rather than refute them, and your CLAUDE.md already says the LLM may only *propose* "X contradicts Y" into a candidate table, while a deterministic verify rule decides whether anything closes.

### Merges stay reversible because edges never point at canonical ids

Every system surveyed keeps history by appending, never by overwriting. Datomic records retractions as datoms (facts with `added=false`), and its `as-of` shows the database before them ([Datomic filters](https://docs.datomic.com/reference/filters.html)). XTDB keeps pre-correction views reachable through `FOR SYSTEM_TIME AS OF` ([XTDB](https://docs.xtdb.com/about/time-in-xtdb.html)). For entity resolution, the equivalent pattern is to **never rewrite an edge's foreign key from entity B to entity A**. Edges reference the ids their source text named. A separate table `entity_alias(alias_id, canonical_id, recorded_at, superseded_at, decided_by, evidence_date)` maps them to canonical ids as of R. Undoing a merge then means closing one alias row, freeze(T, R_before_unmerge) still reproduces the merged graph exactly, and no edge row is touched. This also fits the version-blocker rules from the earlier entity-resolution report (no "SWE-bench" = "SWE-bench Verified" merges): wrong merges will happen, so they must be cheap to undo.

## Freeze(T, R) leaks unless five other clocks are frozen too

A point-in-time freeze is just `valid @> T AND sys @> R`. The leakage comes from everything *else* that was computed after T. The best evidence on how much leakage costs comes from a study of popularity cascades on the APS citation data (a preprint). Random rather than time-ordered splits **inflated metrics by 38% to 151%** depending on the model (+151.3% CasFlow, +76.4% DeepHawkes), and a simple MLP that looked competitive under random splits fell behind under temporal ones ([alphaXiv summary of 2510.25348](https://www.alphaxiv.org/abs/2510.25348.md)). PreScience shows the defensive discipline in practice. Citation counts and h-indices are "temporally aligned to each paper's publication date". The agent's tool outputs drop the target paper, anything dated ≥ t_p, same-title papers, and papers sharing ≥50 contiguous abstract characters with the target. Oracle future citations appear only as a labelled diagnostic ([PreScience](https://arxiv.org/html/2602.20459)). HindSight (a preprint) shows the channel that is easiest to miss. Its idea generator has a December 2023 knowledge cutoff, six months *after* its June 2023 cutoff T, which the authors present as a "margin". In fact the generator could have seen the first six months of the ground-truth window ([HindSight](https://arxiv.org/html/2603.15164v2)).

Here is the backfill trap in full. Everything you load in the 2022–now backfill gets `recorded_at` = the backfill date, which is correct: that is when your system learned it. As a result, freeze(T, R) for any R before the backfill is empty, and every evaluation over 2022–2025 has to use R = now. At R = now, every later correction and every merge decided in 2026 bleeds into the 2023 graph. Transaction time is honest from go-live onward and useless for the historical period. The fix is to enforce leakage rules in the `freeze()` function itself rather than by convention:

| Leakage channel | Enforcement in freeze(T, R, strict) |
|---|---|
| Facts not yet public | `valid @> T` and source-version announcement ≤ T |
| Later system knowledge | `sys @> R`; outputs built at R = now are labelled "reconstruction", not "forecast evidence" |
| Derived numbers (citations, h-index, venue flags) | Read only from `metric(entity, value, as_of)` with the latest `as_of ≤ T`; never from a current column |
| Entity merges | Apply alias rows with `recorded_at ≤ R`; in strict mode only those whose `evidence_date ≤ T` |
| LLM/embedding hindsight | Store `model_id` and `model_knowledge_cutoff` on every candidate and promoted row; strict mode flags rows where the cutoff is later than T |
| Retrieval inside eval tasks | PreScience filter: drop dated ≥ T, same title, near-duplicate text |

The model-cutoff row deserves emphasis. A 5.5-generation extraction model reading a 2023 paper knows how the following two years played out. That knowledge can leak into edge typing ("replaces" vs "extends") even when the quote is genuine. Nobody has measured this effect, or the leakage from later merges or later paper versions; these are reasoned risks, not quantified ones. So evaluate on global time windows (train < T_val < T_test), never on random edge splits. Also report results computed with and without strict-mode filtering, so the size of the hindsight effect becomes something you measure for your thesis rather than assume.

## Postgres 17 handles this with one table and plain btrees

No released Postgres has native system versioning. PG18 (September 2025) added `WITHOUT OVERLAPS` keys and `PERIOD` foreign keys. Both cover only the *last* range column (valid time), are enforced through GiST, and the temporal FKs support only `NO ACTION` ([PG18 CREATE TABLE](https://www.postgresql.org/docs/18/sql-createtable.html)). PG19 adds `UPDATE/DELETE … FOR PORTION OF` and native SQL/PGQ graph queries, and its GA was planned for around September–October 2026 ([PG19 beta 1](https://www.postgresql.org/message-id/attachment/196838/19beta1.md)). A pgEdge author calls system time "anyone's guess" for PG20 or later ([pgEdge](https://www.pgedge.com/blog/looking-forward-to-postgres-19-its-about-time)). None of this changes the design, because transaction time stays hand-managed whatever version you run. Your promoter is the only writer to canonical tables, so it can maintain `sys` directly. That is simpler and safer than the trigger-plus-history-table extensions: the nearform `temporal_tables` port silently drops history for columns added only to the base table ([nearform](https://github.com/nearform/temporal_tables)).

### Schema sketch

```sql
CREATE EXTENSION IF NOT EXISTS btree_gist;

CREATE TABLE paper_version (
  paper_id      bigint   NOT NULL REFERENCES node(node_id),
  version       smallint NOT NULL,
  submitted_at  timestamptz NOT NULL,
  announced_at  timestamptz NOT NULL,        -- used for valid_from
  withdrawn     boolean  NOT NULL DEFAULT false,
  content_hash  bytea    NOT NULL,
  PRIMARY KEY (paper_id, version)
);

CREATE TABLE edge (
  edge_id        bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  src            bigint   NOT NULL,          -- source entity ids, never canonicalized
  dst            bigint   NOT NULL,
  etype          smallint NOT NULL,
  valid_from     timestamptz NOT NULL,
  valid_to       timestamptz,                -- NULL = open
  recorded_at    timestamptz NOT NULL,       -- run timestamp, not clock_timestamp()
  superseded_at  timestamptz,                -- NULL = current belief
  valid tstzrange GENERATED ALWAYS AS (tstzrange(valid_from, valid_to, '[)')) STORED,
  sys   tstzrange GENERATED ALWAYS AS (tstzrange(recorded_at, superseded_at, '[)')) STORED,
  source_paper   bigint, source_version smallint, evidence_hash bytea,
  run_id         bigint NOT NULL REFERENCES pipeline_run(run_id),
  supersede_reason text CHECK (supersede_reason IN
     ('extraction_error','world_change','merge','schema_migration')),
  superseded_by  bigint REFERENCES edge(edge_id),
  model_id text, model_knowledge_cutoff date,
  CHECK (valid_to IS NULL OR valid_to > valid_from),
  CHECK (superseded_at IS NULL OR superseded_at > recorded_at),
  EXCLUDE USING gist (src WITH =, dst WITH =, etype WITH =, valid WITH &&, sys WITH &&)
);
CREATE INDEX edge_src_bt  ON edge (src, etype);
CREATE INDEX edge_dst_bt  ON edge (dst, etype);
CREATE INDEX edge_cur_src ON edge (src, etype) WHERE superseded_at IS NULL;
-- plus a BEFORE UPDATE trigger that rejects any change except superseded_at NULL -> value
-- (and superseded_by / supersede_reason set in the same statement); no DELETE grant.
```

Result rows (`result(paper, task, dataset, metric, value, …)`), `entity_alias` and `metric` snapshots follow the same pattern. Several papers can assert the same edge, so keep one logical edge per `(src, dst, etype)` and hang per-paper evidence (paper, version, quote hash) off it in an `edge_evidence` table. The exclusion constraint then means exactly "one belief about this edge at any (valid, sys) point". This split is my design choice; the notes did not test it. The natural key `(etype, src, dst, source_paper, source_version, evidence_hash)` makes re-ingesting identical content a no-op instead of a new version. Stamping `recorded_at` with the *run's* timestamp rather than the row's makes "as known after run N" reproducible.

### Measured performance at 1M edges

The local benchmark answered the index question clearly. For an as-of out-edge lookup (`src = $1 AND valid @> T AND sys @> R`), the plain btree on `(src, etype)`, with the two range predicates applied as a filter, handled a 50-node batch in **4.3–4.9 ms (~0.1 ms per node)**. The three-column GiST took **4.5–8.4 ms**, and a sequential scan took **340–410 ms per node**. The GiST took **12–13 s to build and 100 MB** against **0.5 s and 12 MB** for the btree, on a 90 MB heap. So keep the GiST only as the integrity constraint. Neon's PG18 guide makes the same point, that GiST indexes are "generally larger than B-tree indexes" ([Neon](https://neon.com/postgresql/postgresql-18/temporal-constraints)). One cost was not measured: per-insert GiST maintenance during promotion. Time your first big promote.

Lineage queries are cheap as long as they stay on lineage edge types. Twenty ancestor queries over `extends/replaces/combines`, depth ≤ 10, with `UNION` set semantics, took **7.0 ms against the live bitemporal table and 4.5 ms against a frozen snapshot**. All-paths enumeration with the `CYCLE` clause at depth ≤ 6 took 4.0 ms, and shortest-path BFS over 20 pairs took 4.9 ms. Costs blow up once `cites` edges join in (average out-degree ~10): path rows grew about 10x per hop (404 at depth 2, 3,828 at depth 3, 17 ms at depth 4). **Depth ≥ 5 path enumeration over citations is the point to stop doing it in SQL.** The PG17 docs add two rules. Use only the `CYCLE` clause and order by its path column, rather than combining it with `SEARCH DEPTH FIRST`. Do not rely on `LIMIT` inside a recursive CTE in production ([PG17 WITH queries](https://www.postgresql.org/docs/17/queries-with.html)). Use `UNION` for reachability, `UNION ALL … CYCLE` with a depth cap only when you need the actual paths, and igraph for whole-graph work. The synthetic graph had only about 1.5 lineage out-edges per node; real "extends" chains may be deeper.

```sql
WITH RECURSIVE anc(node, depth) AS (
  SELECT $start::bigint, 0
  UNION
  SELECT e.dst, a.depth + 1
  FROM anc a JOIN edge e ON e.src = a.node
  WHERE e.etype = ANY($lineage_types) AND a.depth < 10
    AND e.valid @> $T::timestamptz AND e.sys @> $R::timestamptz
)
SELECT node, min(depth) FROM anc GROUP BY node;
```

Apache AGE is not worth adding. Its PG17 line stops at 1.6.0, and 1.7.0 and 1.8.0 build for PG18 only ([AGE releases](https://age.apache.org/release-notes); [EDB AGE 1.8.0](https://www.enterprisedb.com/docs/pg_extensions/apache_age/rel_notes/apache_age_1.8.0_rel_notes/)). The only quantified AGE-alternative comparison found is the `pg_igraph` README's claim of 227 ms vs 47 s for BFS. It gives no methodology, so treat it as marketing ([pg_igraph](https://pgxn.org/dist/pg_igraph/README_PGXN.html)).

### Snapshots and export

Because the promoter only ever closes `sys` and never rewrites the past, **freeze(T, R) for any R in the past is immutable**, so it can be computed once and cached. Materializing it locally as `CREATE UNLOGGED TABLE snap_… AS SELECT …` with two btrees plus `ANALYZE` took **0.64 s for 450k edges and 1.21 s for 1.0M**. Record `(T, R, strict, row_count, checksum)` in a `snapshot` registry. Unlogged is fine because these tables can be rebuilt. Keep one materialized view for "current knowledge" (`WHERE superseded_at IS NULL`) and refresh it non-concurrently after each promote. That took **0.94 s**, against **3.31 s with `CONCURRENTLY`**, which also requires a unique index on a stable `edge_id` (an attempt on `(src, dst, etype)` failed on duplicates). The non-concurrent refresh blocks readers for about a second, which is acceptable for a batch pipeline.

For analytics, number the snapshot's nodes 0..N−1 with `row_number()`, fetch `(src_idx, dst_idx, etype)` with ADBC's `fetch_arrow_table()`, and build `ig.Graph(n=N, edges=…)` in one call. Locally that took **238 ms to fetch plus 413–436 ms to build**. psycopg `fetchall()` took 521 ms, CSV `COPY` into pandas 829 ms, and row-by-row binary `COPY` 1.8 s. igraph's `Graph.DataFrame` costs about 2x for its name mapping. networkx needed **3.1–3.6 s to build and 2.8 s for PageRank, against 63–90 ms in igraph**, so keep networkx for small subgraphs and tests. Build in a single batch: igraph's maintainers show one-at-a-time `add_edge` running ~1,000x slower than one batched `add_edges` ([igraph Discourse](https://igraph.discourse.group/t/igraph-is-much-slower-than-networkx-when-generating-a-graph/853)). ADBC plus pyarrow is a new dependency, so it needs a `claude-progress.txt` note. psycopg at ~0.5 s is a fine fallback. Save each exported snapshot as Parquet keyed by (T, R) so reruns skip Postgres entirely.

### Testing the time logic

Temporal bugs live at boundaries, so test them with Hypothesis `RuleBasedStateMachine` ([Hypothesis stateful](https://hypothesis.readthedocs.io/en/latest/stateful.html)). Keep a pure-Python model (a list of versions with `[vs, ve)` and `[ss, se)`). Apply the same promote, supersede, correct, merge and unmerge rules to both the model and Postgres. Run invariants after every step. The invariants: SQL freeze(T, R) equals the model's filter. freeze(T, R₁) never changes after later promotes. No `(src, dst, etype)` overlaps in valid × sys. CTE ancestors and shortest paths equal networkx's on the model snapshot. igraph edge counts and degree sequences match SQL. Results do not change with session `TimeZone`. Draw T and R exactly *on* range bounds, at ±1 µs, and at unbounded ends. These belong in the integration tier, with 20–50 steps per program.

## Backfill anchor-first, then promote each day atomically

### Scope: union of filter and snowball, with stubs

How comparable LLM-built lineage graphs were scoped is a useful guide. Intern-Atlas fixed a venue list (1.03M papers) and turned out-of-window cited works into **3.17M metadata-only stub nodes** ([Intern-Atlas](https://arxiv.org/pdf/2604.28158)). PreScience took ~98k target papers from 7 arXiv AI categories and expanded one to two hops through "highly influential" references to a ~502k corpus ([PreScience](https://arxiv.org/pdf/2602.20459)). THE-Tree seeded from surveys chosen across time periods "to mitigate recency bias" ([THE-Tree](https://arxiv.org/html/2506.21763v2)). None of them reports dollar costs or an incremental-update mechanism, so your cost model has to be built from token prices. On recall, the one quantitative comparison found (three software-engineering literature reviews) puts database search alone at **43–80%** and snowballing alone at **30–79%**. Only search plus iterated backward and forward snowballing hit **100% recall, at 1.3–2.7% precision** ([Mourão et al.](https://arxiv.org/pdf/2004.09741)). Three studies with no statistical tests is thin evidence. It still points one way: for the AI-agent slice, take the union of an arXiv category/keyword filter and a 1-hop backward and forward expansion from your anchors, then let the triage stage restore precision. Measure recall against `data/gold/dev` rather than assume it. Use OpenAlex or Semantic Scholar reference lists, not arXiv LaTeX alone: unarXive resolved only **44.4% of references** to OpenAlex records ([unarXive](https://ar5iv.labs.arxiv.org/html/2303.14957)).

### Batch LLM economics and failure handling

Anthropic, OpenAI and Gemini all charge 50% less for batch work with a 24-hour target. They differ in what survives a failure. Anthropic returns per-request `succeeded/errored/canceled/expired` results, bills only `succeeded`, keeps results 29 days, and allows 100k requests or 256 MB per batch. Cache reads in batches are best-effort at **30–98% hit rates**, and the docs recommend the 1-hour cache ([Anthropic batch](https://platform.claude.com/docs/en/build-with-claude/batch-processing)). OpenAI likewise keeps completed responses when a batch expires ([OpenAI batch](https://developers.openai.com/api/docs/guides/batch)). Gemini returns **nothing** for a job that expires after 48 hours ([Gemini batch](https://ai.google.dev/gemini-api/docs/batch-mode)), which argues for small jobs there. Listed batch prices on 2026-10-20 are $1/$5 per MTok (input/output) for Sonnet 5.5 and $0.05/$0.25 for Haiku 5.5 on prompts up to 100k tokens. Cache multipliers stack on top, with reads at 0.05x on 5.5-generation models ([Anthropic pricing](https://platform.claude.com/docs/en/about-claude/pricing)). The Haiku figure is unusually low, so check it on your account before budgeting.

As illustrative arithmetic (mine, not a vendor figure): at 20k input and 2k output tokens per paper, uncached, Haiku 5.5 batch costs about **$0.0015 per paper ($15 per 10k papers)** and Sonnet 5.5 batch about **$0.03 per paper ($300 per 10k)**. Cached static prefixes push both lower. Intern-Atlas measured **70.4% edge-type accuracy for its cheap production model against 93.0% for its audit model** ([Intern-Atlas](https://arxiv.org/pdf/2604.28158)). That gap supports the tiering from the earlier reports: the cheap tier extracts in bulk, and deterministic checks plus a stronger tier verify. Put real token counts into `docs/cost_model.md` after a 200-paper pilot. Make every batch resumable. Derive `custom_id` from `sha256(content_hash, prompt_id@version, model)` cut to 64 characters, and write an `llm_batch` row *before* submitting. Download results as soon as a batch completes. Upsert by `custom_id` into `candidate_*`. Re-queue `errored` (server) and `expired` requests, and dead-letter `invalid_request` ones. Dry-run each new request shape on the synchronous API first, because batch validation is asynchronous.

### Idempotency and the atomic promote

Assume every job runs at least once, and make each handler a no-op on repeat. Key each stage on `(stage, input_content_hash, prompt_id@version, model, schema_version)`, so a prompt bump re-runs only that stage for the papers it affects. The work queue can be Postgres itself: claim jobs with a short `FOR UPDATE SKIP LOCKED` transaction, use leases with heartbeats and a reaper, back off exponentially, and dedupe with a partial unique index ([Postgres SKIP LOCKED in production](https://artur.bearblog.dev/background-jobs-without-redis-postgres-skip-locked-in-production/)). That article has a bug to avoid: its retry UPDATE doesn't fence on `worker_id`, so a reaped worker can overwrite a re-claimed job. Add `AND worker_id = $me AND lease_until > now()`. Verified rows go to `staging_*` tagged with `run_id`. A single `promote(run_id)` transaction then inserts new canonical rows, closes the superseded ones, and marks the run promoted. It is guarded by a uniqueness check on `run_id`, so running it twice changes nothing. If any check fails, nothing is promoted and readers keep seeing yesterday's graph. The precedents are OpenAlex's "partition is complete only when its manifest exists" rule ([OpenAlex snapshot](https://docs.openalex.org/download-all-data/snapshot-data-format)) and Intern-Atlas's validate-then-write batches with a single repair retry.

### Runbook

| Phase | Step | Concrete settings |
|---|---|---|
| 0. Setup | Migrations for the tables above; update-guard trigger; `freeze(T,R,strict)` function; Hypothesis suite green | `SET TimeZone='UTC'` in role config |
| 0. Setup | pgBackRest stanza: repo1 local disk, repo2 S3-compatible (e.g. R2), `archive-async=y`, `repo2-cipher-type=aes-256-cbc` (fixed at creation) | Weekly full, daily diff, keep 2–4 fulls ([pgBackRest](https://pgbackrest.org/user-guide.html)) |
| 1. Scope | Anchors from `config/anchors.yaml`; arXiv category/keyword filter 2022-01-01→now; 1-hop references and citations via S2 (1 RPS) and OpenAlex | Out-of-scope works become stubs (metadata only) |
| 2. Metadata | OAI-PMH `arXivRaw` harvest for version history into `paper_version`; `metric` snapshots with `as_of` dates | ≥3 s between requests, one connection ([arXiv ToU](https://info.arxiv.org/help/api/tou.html)) |
| 3. Pilot | 200 papers end-to-end; measure tokens, reject rates, cost; fix cost model | Sync API dry-run of every request shape |
| 4. Backfill | Anchors first, then newest-first by month; triage, then batch extraction in chunks of a few thousand requests | One `pipeline_run` per month-chunk |
| 5. Promote | Verify, stage, `promote(run_id)`, refresh current matview, `pg_create_restore_point('run_<id>')` | Restore point makes "before the bad run" a named target |
| 6. Stub upgrade | Weekly: promote stubs that cross an in-corpus citation threshold to full extraction | Threshold tuned on gold recall |
| Daily | Start ~00:30 ET (after the 20:00 ET announcement and ~22:30 ET OAI refresh), on nights following Sunday–Thursday announcements | Expect zero on Fri/Sat and on 2026 holidays (Jan 1, Jan 19, Jun 19, Jul 3, Sep 7, Oct 12, Nov 26, Dec 25, Dec 29, Dec 31) ([arXiv](https://info.arxiv.org/help/availability.html)) |
| Daily | OAI-PMH incremental with `from` = last server-reported harvest date, no `until` | Datestamp = last modification, so bulk updates resurface old records ([OAI-PMH](https://info.arxiv.org/help/oa/index.html)) |
| Daily | New versions: content hash changes, re-extract, old facts get `superseded_at`; withdrawals set `valid_to` via new version | Never delete |
| Weekly | Forward-citation re-scan for the last ~4 weeks of papers (S2/OpenAlex lag arXiv) | — |
| Monitoring | healthchecks.io `/start`, success, `/fail` pings; per-run metrics vs 4-week same-weekday median | Alert at ±50% or ±3 MAD, verify-reject spikes, cost over budget ([healthchecks.io](https://healthchecks.io/docs/)) |
| Monthly | Restore drill into a throwaway container (PITR to "yesterday 23:00"), run invariants, log recovery time; weekly `pg_dump -Fc` of canonical schema | — |

The metrics to track per run are the ones that reveal drift: new vs replaced IDs, triage pass rate, parse failures, LLM errored and expired rates, verify rejection rate, promoted node and edge counts, dollar cost, batch latency, and the newest announce date promoted. A rejection-rate jump usually means a prompt or model changed under you. An unexpected zero on an announcement night means the harvest broke. Encode the arXiv calendar so that expected zeros stay silent.

## Pitfalls and open gaps

Most of the failure modes are quiet ones: queries that return a plausible answer from the wrong slice of time. Mixing `'infinity'` with unbounded bounds, or `[]` with `[)`, makes boundary rows appear or vanish. The fix is generated ranges with fixed `[)` bounds and boundary-drawn property tests. Session timezones silently shift date literals. `upper(valid)` in a WHERE clause can bypass the index unless you add an expression index ([Neon](https://neon.com/postgresql/postgresql-18/temporal-constraints)). Treating an R = now reconstruction of 2023 as a 2023 forecast is the costliest conceptual error. The API should always echo `(T, R, strict)` alongside its results. Version semantics remain a known gap: no source confirms how arXiv represents deletions in OAI-PMH, so check the `deletedRecord` field with an `Identify` call before trusting withdrawal detection. The date fields OpenAlex and Semantic Scholar expose were not verified either, which is one more reason to derive `valid_from` from arXiv's own version history.

Several numbers here still need your own measurement. The benchmark ran on PG16 with synthetic, shallow lineage. GiST insert overhead during promotion, lock contention under concurrent reads, and incremental view maintenance (`pg_ivm`) were not measured. No published benchmark compares `periods` or `temporal_tables` against a hand-rolled table at 1M+ rows. Snodgrass's and Johnston's books, the standard references on sequenced temporal queries, were not consulted. Cloudflare R2 pricing and pgBackRest-on-R2 settings (path-style URIs) were not verified. No source measured leakage from later merges, later versions or model cutoffs. Those three are exactly where your thesis could contribute a measurement rather than an assumption.

## Conclusion

The storage step turns out to matter less for speed than for honesty. At 1–2M edges, Postgres 17 with btrees, recursive CTEs and an igraph export is fast enough that performance stops being a design driver; every measured operation finishes in milliseconds to about a second. What actually decides whether your lineage graph can support forecasting claims is whether "when was this knowable" is enforced in code at every layer: version-level `valid_from`, closing `sys` rather than `valid` for errors, alias rows instead of rewrites, as-of metric snapshots, and model cutoffs stored on each row. Leaving any one of these out reopens a leakage channel worth tens of percent, if the cascade study is any guide.

The less obvious implication concerns the backfill. Bitemporality protects the *future* of the project, not its past. From go-live onward, freeze(T, R) at real run times gives honest, replayable backtests for free. That makes the earliest stable daily runs valuable thesis data in their own right. A few months of genuinely recorded R lets you compare "what the system knew then" against "the R = now reconstruction" on the same T, and measure hindsight leakage directly instead of arguing about it.
