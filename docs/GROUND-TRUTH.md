# FalkorDB ground truth — measured locally, not from docs
Probed 2026-10-15 on falkordb/falkordb:latest, module ver 42201 (v4.22.1), Docker, 11 CPU / 8GB.

## Operational gotchas (cost me time; document in README)
- **Homebrew `redis-server` 8.2.1 squats 127.0.0.1:6379** and silently shadows Docker's `-p 6379:6379`.
  Symptom: `redis.exceptions.ResponseError: unknown command 'GRAPH.QUERY'`. Fix: map to **6380**.
  `docker run -d --name falkordb -p 6380:6379 -p 3100:3000 -v falkordb-data:/data falkordb/falkordb:latest`
- Browser UI on container port 3000. Bundled modules: `graph` (42201) + `vectorset`.
- Defaults: MAX_QUEUED_QUERIES=25, TIMEOUT=1000, RESULTSET_SIZE=10000. The 10k resultset cap will silently truncate big returns.
- Constraints need a supporting index FIRST ("missing supporting exact-match index").

## Procedures that EXIST (verified by call)
algo.pageRank, algo.WCC, algo.labelPropagation, algo.betweenness, algo.HarmonicCentrality,
algo.BFS, algo.SPpaths, algo.SSpaths, algo.AStar, algo.maxFlow, algo.MSF
db.idx.vector.queryNodes / queryRelationships
db.idx.fulltext.createNodeIndex / queryNodes / queryRelationships / drop
db.idx.cch.query, db.constraints, db.indexes, db.labels, db.meta.stats, db.propertyKeys, db.relationshipTypes
Commands: GRAPH.QUERY/RO_QUERY/EXPLAIN/PROFILE/CONSTRAINT/COPY/EFFECT/BULK/INFO/MEMORY/SLOWLOG/UDF/LIST/DELETE/RESTORE/DEBUG

### NOT advertised on the hackathon page but real (differentiation surface)
`algo.maxFlow`, `algo.MSF` (min spanning forest), `algo.AStar`, `algo.HarmonicCentrality`,
`db.idx.cch.query` (contraction hierarchies), `GRAPH.UDF`, `GRAPH.EFFECT`, `GRAPH.COPY`.
The brief only names "shortest path, PageRank, centrality, connected components, community detection".

## Cypher coverage (verified)
WORKS: CALL{} subqueries, FOREACH, UNWIND, list + pattern comprehension, `exists(pattern)`,
var-length `[:R*1..3]`, shortestPath(), allShortestPaths(), MERGE ON CREATE/ON MATCH, CASE,
reduce(), UNION / UNION ALL, WITH+ORDER BY+SKIP+LIMIT, duration arithmetic, point()/distance().
**MISSING: `EXISTS { MATCH ... }` subquery form** — use the `exists((a)-[:R]->(b))` function instead.
No APOC. Community detection = `algo.labelPropagation` only (no Louvain/Leiden).

## Vector + fulltext (verified working)
```cypher
CREATE VECTOR INDEX FOR (n:Doc) ON (n.emb) OPTIONS {dimension:4, similarityFunction:'cosine'};
CREATE (:Doc {id:'a', emb: vecf32([1.0,0.0,0.0,0.0])});
CALL db.idx.vector.queryNodes('Doc','emb',3, vecf32([1.0,0.0,0.0,0.0])) YIELD node, score;
-- score is DISTANCE: 0.0 == identical
```
**HYBRID RETRIEVAL IN ONE QUERY WORKS** — this is the headline capability:
```cypher
CALL db.idx.vector.queryNodes('Doc','emb',2, vecf32($q)) YIELD node AS seed, score
MATCH (seed)-[:CITES*0..2]->(hop)
RETURN seed.id, score, collect(DISTINCT hop.id) AS reachable
```
`vec.cosineDistance(a,b)` / `vec.euclideanDistance` usable as plain functions for in-query rerank.
Fulltext: `CALL db.idx.fulltext.createNodeIndex('Doc','body')` then `queryNodes('Doc','agent memory')` -> BM25-ish score.

## MEASURED performance (20k nodes / 40k edges, local Docker)
| op | result |
|---|---|
| node ingest, UNWIND batch 1000 | **248,013 nodes/sec** |
| edge ingest, UNWIND + MATCH + CREATE | **4,919 edges/sec  <-- THE BOTTLENECK** |
| 2-hop read, 1 client | 2,130 q/s, p50 0.37ms |
| 2-hop read, 32 clients | **7,742 q/s, p50 1.74ms, p99 6.82ms** |
| MERGE write, 1 client | 1,496 w/s, p50 0.60ms |
| MERGE write, 32 clients | **3,373 w/s, p50 6.77ms, p99 13.47ms** |
| create 200 isolated tenant graphs | 0.11s = 1,862 graphs/sec |
| algo.pageRank | **7.3 ms** |
| algo.WCC | **7.8 ms** |
| algo.betweenness | **18.4 ms** |
| algo.labelPropagation | **58.3 ms** |
| memory for 20k/40k + indices | 10 MB total, 2 MB indices |

### Strategic reads from these numbers
1. **Graph algorithms are fast enough to be agent tools in the hot path.** PageRank in 7ms means an
   agent can call centrality mid-conversation, per-turn, and the user never waits. Most entries will
   treat algorithms as a batch/offline step. Running them live inside the agent loop is a visible,
   defensible use of FalkorDB's sparse-matrix engine.
2. **Edge ingest at ~5k/s is the schedule risk.** 1M edges = ~3.4 min of pure write time, and that is
   before LLM extraction. Budget ingest realistically; pre-resolve node IDs; consider GRAPH.BULK.
3. **Per-tenant isolation via multigraph is essentially free** (1,862 graphs/sec). T2's "separate
   memory per user or tenant" is a one-line `db.select_graph(f'tenant_{id}')`, so it is table stakes,
   not a differentiator. Everyone will claim it.
4. Concurrency scales ~2.3x on writes and ~3.6x on reads from 1->32 clients, then flattens. Real but
   not linear — be honest about it if claiming "high concurrency".

## Edge-ingest optimization — MEASURED, all variants verified to create 20,000 correct edges
(20k nodes, 20k edges; spot-checked 200/200 expected edges present)

| strategy | edges/sec | vs baseline |
|---|---|---|
| **C. resolve ids in app, then `WHERE id(a)=.. AND id(b)=..`** | **222,374** | **73x** |
| E. `MERGE (a) MERGE (b) MERGE (a)-[:L]->(b)` one pass | 14,789 | 4.9x |
| A. `MATCH (a:N{id:..}),(b:N{id:..}) CREATE` + index | 3,021 | 1x |
| F. 4 or 8 concurrent writer clients | ~3,300 | 1.1x (no gain — writes serialize) |
| D. same as A but batch=10,000 | 378 | **0.12x — WORSE** |
| B. A but with NO supporting index | 176 | 0.06x |

`GRAPH.EXPLAIN` shows why: `NodeByIdSeek` (O(1) direct offset) vs `Node By Index Scan` (B-tree probe).

### Ingest rules this implies
1. **Two-phase ingest is the only sane pattern.** Phase 1: `UNWIND ... CREATE` nodes (248k/s) and keep
   the `business_key -> id(n)` map in app memory. Phase 2: create edges by internal id (222k/s).
   This turns a 1M-edge graph from ~5.5 min of DB time into ~4.5 seconds.
2. **Do NOT raise batch size past ~1000.** The planner builds a Cartesian Product per row; at
   batch=10,000 it collapses to 378 edges/sec, 8x slower than batch=1000. Counter-intuitive and a
   trap most teams will hit by "optimizing".
3. **Do NOT parallelize writes to the same graph for ingest** — zero gain, writes serialize.
   Concurrency only helps READS (3.6x) and small independent MERGE writes (2.3x).
4. **Always create the supporting index before any MATCH-based write** — 17x penalty without it.
5. **`RESULTSET_SIZE=10000` silently truncates.** `MATCH (n:N) RETURN n.id, id(n)` over 20k nodes
   returned exactly 10,000 rows with no error or warning. Paginate with SKIP/LIMIT or raise the
   config. This is a silent-data-loss trap, not an error.

## Embeddings without any API key — MEASURED
`fastembed` + `BAAI/bge-small-en-v1.5`, CPU only, no key, no network after first download:
- model download + load: 11.6s one-time (cached after)
- batch embed: 181 docs/sec, dim=384
- **single-query embed p50 4.7ms** (min 3.4ms) — fast enough for the agent hot path
- 12+ models available incl. bge-base/large, mxbai-embed-large, snowflake-arctic
=> The ENTIRE retrieval layer (vector index + embeddings) needs ZERO API budget.
   Only LLM reasoning/generation needs a key. Plan around that single dependency.

## End-to-end spike VERIFIED (fastembed -> FalkorDB vector index -> hybrid traversal)
Query: "why did we switch auth to JWT and what broke?"
- vector-only returned 3 loosely-relevant docs: no owner, no blast radius, no contradiction.
- ONE hybrid Cypher query returned: decision ADR-7, cited source d1, owner Priya,
  blast_radius=[payments, billing], contradicted_by=[d2].
- provenance path returned as explicit node+edge chains:
  d2 -CONTRADICTS-> ADR-7 -AFFECTS-> auth <-DEPENDS_ON- payments
This is the before/after the brief is asking for, and it is ~40 lines of code. The
`CONTRADICTS` edge (a doc that invalidates a decision) is a staleness signal that vector
search structurally cannot produce. Keep this as the demo spine whatever the final concept.

## LLM access — OPEN DEPENDENCY (ask the user)
No OPENAI/ANTHROPIC/GEMINI/GROQ key present in env. Ollama installed but not running and no
models pulled. Several unrelated project .env files exist in the home dir (not inspected).
Options: (a) user supplies a key, (b) Gemini/Groq free tier, (c) Ollama local for dev +
keyless demo mode, (d) pre-baked read-only demo sessions so judges need no key.

## MULTI-TENANCY SCALING — independently measured 1 -> 1000 tenant graphs
(200 nodes + 199 edges per tenant graph, local Docker, 11 CPU / 8GB. Nobody in the ~110-repo field has
published this; third-party reviewers call FalkorDB's multi-tenancy "claimed, not measured".)

| tenants | read p50 | read p99 | write p50 | total mem | mem/tenant | select_graph |
|---|---|---|---|---|---|---|
| 1 | 0.42ms | 2.34ms | 0.28ms | 3.7MB | 537.0KB | 2.2us |
| 10 | 0.43ms | 1.64ms | 0.33ms | 8.2MB | 512.3KB | 1.2us |
| 50 | 0.51ms | 5.48ms | 0.38ms | 28.3MB | 513.5KB | 1.3us |
| 100 | 0.46ms | 1.09ms | 0.34ms | 53.0MB | 510.4KB | 0.6us |
| 250 | 0.37ms | 0.90ms | 0.27ms | 125.2MB | 499.7KB | 0.4us |
| 500 | 0.40ms | 0.94ms | 0.30ms | 244.6MB | 494.4KB | 1.8us |
| **1000** | **0.38ms** | **0.82ms** | **0.29ms** | 482.7MB | 491.1KB | 1.3us |

Creation: 1000 tenant graphs in 1.86s = **539 tenants/sec**.

### Concurrent mixed read/write (75/25) spread across all 1000 tenant graphs
| workers | throughput | read p50/p99 | write p50/p99 |
|---|---|---|---|
| 1 | 2,531 ops/s | 0.40 / 0.63ms | 0.32 / 0.48ms |
| 8 | **8,175 ops/s** | 0.74 / 1.33ms | 0.74 / 1.89ms |
| 32 | 7,008 ops/s | 1.85 / 8.00ms | 1.64 / 6.51ms |
| 64 | 6,514 ops/s | 2.60 / 15.91ms | 2.46 / 13.54ms |

### Findings
1. **Read latency is FLAT from 1 to 1000 tenant graphs** (0.42ms -> 0.38ms) and p99 improves
   (2.34ms -> 0.82ms). Tenant count does not degrade per-query performance.
2. `select_graph()` costs ~1us regardless of how many graphs exist => keyspace lookup is O(1).
3. Memory is **linear and predictable at ~491KB per tenant** for this shape. Honest caveat worth
   publishing: 10,000 tenants x 491KB ~= 4.8GB, so FalkorDB's "10K+ multi-graphs" headline is
   MEMORY-bound, not architecture-bound. That is a real, citable limitation.
4. Throughput peaks at 8 workers (8,175 ops/s) and degrades gracefully, not catastrophically, to 64.
5. **Isolation is physical, not a filter.** Tenant 1 running the identical Cypher that returns
   tenant 0's secret gets `[]`, and `CALL db.labels()` in tenant 1 does not even list the `Secret`
   label. This is a far stronger claim than `WHERE n.tenant = $id` and is demoable in 10 seconds.

## Concurrency model — MEASURED, resolves a doc ambiguity
Docs state "FalkorDB uses a per-graph reader-writer model / only one write query executes at a time on a
given graph" but never say whether writes to DIFFERENT graphs run in parallel. Measured it (30k-node
UNWIND CREATE per write, solo baseline 0.021s):

| writers | all on SAME graph | each on OWN graph | speedup |
|---|---|---|---|
| 2 | 0.034s | 0.036s | 0.96x (overhead dominates) |
| 4 | 0.084s | 0.050s | **1.67x** |
| 8 | 0.146s | 0.089s | **1.64x** (1.89x vs serial projection) |

**Conclusion: graph-per-tenant gives a real but BOUNDED write-throughput win of ~1.6-1.9x at 4-8
concurrent writers, not linear scaling.** The per-graph write lock is confirmed (8 writers on one graph
took ~7x the solo time). The plateau is consistent with the third-party claim that Redis's
single-threaded core caps scaling past ~8 threads. Quote 1.6-1.9x, never "linear".

## Purge/DELETE traps — VERIFIED
- `UNWIND [1,2,3] AS v CREATE (a:T{p:v}) RETURN a LIMIT 1` creates **3** nodes. LIMIT is NOT respected
  by CREATE/SET/DELETE/MERGE. A purge bounded with a trailing LIMIT deletes the wrong amount.
- The CORRECT bounded-purge idiom is `MATCH (a:T) WITH a LIMIT 2 DELETE a` -> "Nodes deleted: 2". Verified.

## Temporal support — PARTIAL, docs and my first probe were both wrong
| expression | result |
|---|---|
| `date() + duration({days:1})` | **OK** -> 2026-10-16 |
| `duration({days:2}) - duration({days:1})` | **OK** -> P1D |
| `datetime() + duration({hours:2})` | **FAILS** |
| `WHERE n.ts > datetime() - duration({days:7})` | **FAILS** |
=> DATE arithmetic works; DATETIME arithmetic does not. Store timestamps as **epoch millis integers**
and compare numerically. Do not design any decay/TTL logic around datetime arithmetic.

## Vector index cannot property-filter — CONFIRMED, and it is a 10-second demo
Docs: "Vector queries don't filter by properties." Measured consequence in a SHARED graph:
```
CALL db.idx.vector.queryNodes('Fact','emb',2,vecf32([1,0,0])) YIELD node RETURN node.t, node.s
-> A "tenantA secret"   +   B "tenantB secret"      <-- CROSS-TENANT LEAK
```
Post-filtering the same top-2 to tenant A returns only 1 row — you asked for k and kept k/N.
**So a shared graph + `WHERE n.tenant=$id` post-filter gives you either a measurable leak or recall
collapse.** Graph-per-tenant is therefore structurally necessary for vector memory, not hygiene.
This is the single best "why the graph is load-bearing" demo beat found so far.

## ForgetEval — verified to exist
github.com/deeplethe/lethe -> HTTP 200, **MIT**, 17 stars, "the first AI memory built to forget."
Benchmark claimed at arXiv:2606.15903v2: 385 cases, no LLM judge, CPU-only.
Published scores: **Graphiti 4.4% strict**, HippoRAG 8.0%, Mem0(infer) 43.6%, best LLM-hook 93.2%.
Not yet independently re-run by me — treat the numbers as the paper's until reproduced.

## Version fork — PIN v4.22.1, do NOT use 6.x
- `falkordb/falkordb:latest` resolves to **v4.22.1 (C engine)**, module ver `42201` — verified by
  `MODULE LIST`. The vendor's own 6.0 release notes claim `latest` points at 6.0. **The tag is not
  trustworthy; pin `falkordb/falkordb:v4.22.1`.**
- 6.0.x (Rust engine) **drops `algo.AStar` and `algo.CCH`**, and `algo.louvain`/`algo.leiden` are
  listed as "still in development" (so still no Louvain/Leiden anywhere).
- 6.0.x open issues that would wreck a 3-day build: #3279 a trailing MATCH after `CALL..YIELD`
  **crashes the server**; #3304 a long clause chain **overflows a worker stack and crashes**;
  #3311 **SIGSEGV** in a hash join; #3325/#3343 **silently wrong results** (0 rows, lost bindings);
  #3330 unique-constraint inserts **35-120x slower** than 4.20.7 with quadratic scaling.
- License is **SSPLv1** — worth one line in a README; it is not OSI-approved open source.

## The image bakes in three limits that all bite
Default `FALKORDB_ARGS` in the official image: `TIMEOUT 1000 RESULTSET_SIZE 10000 MAX_QUEUED_QUERIES 25`.
- `RESULTSET_SIZE 10000` — **silently truncates** larger returns, no error (bit me live: a 20k-row
  id map came back with exactly 10,000 rows).
- `TIMEOUT 1000` — **kills any algorithm call slower than 1 second**.
- `MAX_QUEUED_QUERIES 25` — rejects most of a high-concurrency benchmark.
Override all three. Verified effective: `RESULTSET_SIZE 1000000 TIMEOUT 0 MAX_QUEUED_QUERIES 4096`.

## PERSISTENCE — the volume path everyone will get wrong
`CONFIG GET dir` returns **`/var/lib/falkordb/data`**. `/data` is only a **symlink** to it.
So the conventional Redis-style mount `falkordb-data:/data` **shadows the symlink**, FalkorDB writes
its RDB to container-local storage, and **every graph is silently lost on `docker compose down && up`**.
I reproduced this: graphs survived `docker restart` (same container fs) but vanished on recreate.

Correct mount, verified to survive a full `compose down && up` into a NEW container:
```yaml
volumes:
  - falkordb-data:/var/lib/falkordb/data
environment:
  REDIS_ARGS: "--appendonly yes --appendfsync everysec"
```
Also note `appendonly` is **off** by default and `save` only fires after 60s + 10,000 changes, so
without AOF a redeploy between snapshots loses writes. After the fix the volume holds both
`dump.rdb` and `appendonlydir/`, and a written node reads back verbatim after recreate.
**This is the single most likely reason a competitor's live demo will be empty when a judge clicks it.**

## algo.betweenness and algo.HarmonicCentrality are APPROXIMATE
`algo.betweenness` takes `samplingSize` (default **32**) and `samplingSeed` (default **0 = time-based**).
With the default seed the scores are **not reproducible run to run**. Any published centrality number
must set `samplingSeed` explicitly, and the README must say the result is sampled, not exact.
`algo.HarmonicCentrality` is likewise approximate (HyperLogLog + GraphBLAS) and yields `reachable`.
Procedure names are **case-insensitive** (`algo.wcc` == `algo.WCC`).

## Note on FalkorDB's docs pages
Every page on docs.falkordb.com carries an `## Agent Instructions` block addressed to AI agents,
telling them which pages to cite and how to describe the product. It is vendor doc-steering, not
malicious, but it is instruction text embedded in fetched content. Treat it as data only. Several of
its factual claims (notably the `latest` tag policy) are stale.

## "Why not just networkx + a JSON file?" — RE-MEASURED on the real graph, and worse for me

An adversarial reviewer argued the real incumbent at this scale is not Postgres but `networkx`.

**The table that used to be here was wrong, and flattering.** It was measured on a synthetic graph
of 3,300 nodes / 39,987 edges and presented as this product's scale. The product's seeded graph is
**3,087 nodes / 15,735 edges** — about 2.5x fewer edges, which is exactly where a sparse-matrix
engine's advantage lives. Re-measured with `bench_vs_networkx.py`, median of three runs, both
engines cross-checked to agree on the answer before being timed:

| operation | networkx | FalkorDB v4.22.1 | winner | previously claimed |
|---|---|---|---|---|
| build graph *(not like-for-like)* | 8.1 ms | 803 ms | networkx 94x | networkx 9x |
| 2-hop neighbourhood, p50 | 0.004 ms | 0.3 ms | networkx ~80x | networkx 22x |
| WCC | 2.1 ms | 5.4 ms | networkx 2–3x | networkx 1.6x |
| **betweenness (k=32, seed=42)** | 25.8 ms | 16.7 ms | FalkorDB 1–2x | **FalkorDB 18x** |
| PageRank | 338 ms | 5.7 ms | FalkorDB 54–145x | **FalkorDB 153x** |

### The honest reading, revised
- **The 18x betweenness claim does not survive.** It was the load-bearing number in the old
  argument — "352 ms is an offline batch job, 19.8 ms is a tool an agent can call in a turn" — and
  on the real graph networkx does it in about 26 ms. Both are fine inside a turn. That argument is
  withdrawn.
- networkx is faster at everything except PageRank, which **no tool in the catalogue calls**.
- The build row is not a like-for-like comparison and is kept only for completeness: FalkorDB's
  figure includes loading the snapshot, ingesting and building seven indexes; networkx is handed
  an edge list already in memory.
- What remains, and is not a speed claim: a vector index composed with traversal in one query;
  `GRAPH.COPY` for a counterfactual evaluated against a mutated whole-graph copy and discarded
  inside one request; memory in the same graph as the facts; durable persistence; physically
  isolated tenant graphs; concurrent access to live shared state; a returnable path object as
  provenance from the query that produced the answer.

### A benchmarking bug this turned up
`CALL algo.WCC(NULL, NULL)` — the two-argument form, by analogy with `algo.pageRank(NULL, NULL)` —
**silently returns zero rows on v4.22.1 instead of erroring.** The old "WCC 4.5 ms" figure above
was therefore the cost of computing nothing at all. `CALL algo.WCC()` is the working form. The
benchmark now requires networkx and FalkorDB to agree on the component count before it times
either, which is how this surfaced; a timing harness that never checks the result will happily
publish the speed of a no-op.

### Reproducibility confirmed
`algo.betweenness` with `samplingSeed:42` returns byte-identical scores across runs
(`[[3083,1265.24],[830,1040.86],[2100,982.36]]` twice). Unseeded runs were stable within a session
but produced *different* values than the seeded run, so always pin the seed for any published number.
