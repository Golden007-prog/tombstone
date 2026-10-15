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
