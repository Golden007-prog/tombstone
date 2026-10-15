# Tombstone

**The decisions your org already made and forgot. Asked as a graph.**

Graph Hacks 2026 (WeMakeDevs × FalkorDB) — **Track 3, Company Brain**.

Large engineering orgs keep re-proposing things they already rejected, because the rejection was
never a thing you could look up. The rejected option isn't a document — it's a 200-word subsection
buried inside a 4,000-word proposal about something else. It has no identity, so you can't count how
often an idea was refused, you can't ask who refused it, and you can't find out whether anyone who
knows why is still around.

Tombstone makes the rejected alternative a first-class node, attaches the person who killed it, and
answers four questions that are each a traversal:

| question | what comes back |
|---|---|
| **Has this been tried?** | the rejected option, its recorded reason, and whether any decider still works here |
| **Who owns this?** | at depth 1, silence. At depth 4, that it's **orphaned** — and what its departed owners decided elsewhere |
| **Which areas have no living owner?** | 7 of them, with every recorded owner gone |
| **Whose departure cost the most?** | ranked by **betweenness centrality**, not by file count |

![The reasoning path behind one answer](docs/img/path.svg)

*Asked "who owns `pkg/controller/podgc`?", Tombstone returns silence at depth 1 and this at depth 4:
the area is orphaned, both recorded owners have left, and one of them personally rejected six
alternatives in KEP-383. Generated from the live API by `scripts_gen_readme_figure.py`.*

It runs on **Kubernetes' own governance record** — a real organisation of thousands of people that
publishes its decision history, its ownership map, and, unusually, its own attrition. Apache-2.0,
fully public. Every number below is checkable with one `git clone`.

## Quickstart

```bash
git clone <this repo> && cd "graph hack"
pip install -r requirements.txt
./run.sh
```

Then open <http://localhost:8099>. No API key needed: the scripted questions call the tools
directly and run the same Cypher. `run.sh` starts FalkorDB, seeds it from the committed snapshot in
**~1.1s**, and serves the app.

To enable free-text questions, copy `.env.example` to `.env` and add one key (Anthropic, OpenAI,
Gemini or Groq — it auto-detects).

```bash
PYTHONPATH=src python -m pytest tests/ -q     # 18 invariant tests
PYTHONPATH=src python verify_claims.py        # re-checks every number in this README
```

```bash
PYTHONPATH=src python eval_retrieval.py       # 12 paraphrases + 3 negative controls
```

`verify_claims.py` exists so you can falsify any factual claim here in one command. It queries the
live graph and compares against the number printed in this file.

`eval_retrieval.py` scores the headline tool on twelve paraphrases a contributor might plausibly
type, written without looking at the corpus first: **12/12 return a real titled rejected option with
a substantive recorded rationale.** It also runs three negative controls — ideas this corpus should
not know about — and **3/3 correctly return nothing**. A retrieval layer that never returns nothing
is not telling you anything.

## Turn FalkorDB off and here is exactly what stops working

Rule 3 says a product that still works without the graph is decoration, so here is the honest answer.

- **“Has this been tried?” becomes `grep` over 688 markdown files** — which is what contributors
  already have, and precisely why the problem exists.
- **The rejected alternative loses its identity.** You cannot count how many times an idea was
  refused, because there is nothing to count.
- **You lose the ability to answer *nothing*.** A vector index always returns its k nearest rows no
  matter how far away they are. "No living owner" is the *absence* of an edge, and absence is not
  something a similarity score can express.
- **The ranking of whose departure hurt most disappears entirely.** That is betweenness centrality —
  a whole-graph property that no traversal, no SQL join and no embedding can compute.

There is **no in-memory mirror and no cached fallback** anywhere in this repo. With the database
unreachable, every endpoint returns `DEGRADED` and says so. There is a test for it
(`test_agent_fails_loudly_without_the_database`).

## The graph data model

Required by Rule 10. The two **latent** labels are the whole idea: neither is a document, a person
or a file, so neither exists in any search index anywhere.

```
NODES
  (:Kep           {key, num, title, status, status_raw, sig, stage, created_ms:int, url})
  (:Alternative   {key, title, body, kep, titled:bool})          ← LATENT: a rejected design option
     :NamedOption                                                 ← titled subset; carries .emb
  (:MissingRecord {key, cited_by:int})                            ← LATENT: a decision record that
                                                                     others cite but which is GONE
  (:Person        {key})                                          alias-expanded, bots removed
  (:OwnersFile    {key, path, url})
  (:Sig           {key})

RELATIONSHIPS
  (:Kep)-[:CONSIDERED]->(:Alternative)        (:Kep)-[:OWNED_BY]->(:Sig)
  (:Kep)-[:REPLACES|SUPERSEDED_BY|SEE_ALSO]->(:Kep)
  (:Kep)-[:CITES_MISSING]->(:MissingRecord)
  (:Person)-[:AUTHORED|APPROVED|REVIEWED]->(:Kep)
  (:Person)-[:APPROVES]->(:OwnersFile)        ← a CURRENT owner
  (:Person)-[:EMERITUS_OF]->(:OwnersFile)     ← a DEPARTED owner. The project writes its own
                                                 knowledge loss into this field and nothing reads it.
  (:Person)-[:CO_AUTHORED {w:int}]->(:Person) ← projection, computed in Cypher (see below)

INDEXES
  CREATE VECTOR INDEX FOR (a:NamedOption) ON (a.emb)
         OPTIONS {dimension: 384, similarityFunction: 'cosine'}
  CREATE INDEX FOR (k:Kep)        ON (k.key)
  CREATE INDEX FOR (p:Person)     ON (p.key)
  CREATE INDEX FOR (o:OwnersFile) ON (o.key)
```

**Why `:NamedOption` is a label and not a property.** FalkorDB vector indexes cannot filter by
property — a shared index forces you to post-filter, so you ask for *k* and keep *k/N*. Minting a
label gives a genuinely pre-filtered ANN index with no recall loss.

**Why `CO_AUTHORED` exists.** Centrality over the raw bipartite `Person-[:AUTHORED]->Kep` graph is
degenerate: every score 1.0, every community size 1. The projection is a 2-hop co-occurrence over
shared decisions, **computed in Cypher by the database** (5,870 edges, ~95ms) — not in numpy and
written back, which would mean the algorithm was partitioning a matrix the database never computed.

```cypher
MATCH (a:Person)-[:AUTHORED|APPROVED|REVIEWED]->(k:Kep)<-[:AUTHORED|APPROVED|REVIEWED]-(b:Person)
WHERE a.key < b.key
WITH a, b, count(DISTINCT k) AS shared
MERGE (a)-[e:CO_AUTHORED]->(b) SET e.w = shared
```

## What's in the graph

| | count |
|---|---|
| decisions (`:Kep`) | 679 |
| rejected alternatives (`:Alternative`) | 959 — of which **753 are titled, named options** |
| missing decision records (`:MissingRecord`) | 52 (cited 63 times) |
| people | 794 |
| ownership files | 585 |
| `APPROVES` / `EMERITUS_OF` | 2,584 / 298 |
| `CO_AUTHORED` | 5,870 |

Findings that fall straight out of it, each checkable:

- **63 of 363 internal decision pointers (17.4%) don't resolve.** One missing record,
  `/keps/sig-api-machinery/0006-apply.md`, is cited by **four** separate decisions.
- **83 of 111 departed owners hold no current approver role anywhere.**
- **7 areas have no current approver at all**, including `pkg/controller/podgc` (gmarek, foxish).
- `lavalamp` is emeritus in **31** ownership files and has the highest betweenness of any departed
  contributor (196.1, sampled, seed pinned).

## The Cypher this product depends on

Required by Rule 10. These are generated from `src/tombstone/tools.py` by
`python scripts_gen_readme_cypher.py`, so they are the queries that actually run — not a retelling.
Every one is hand-written and parameterised. **The model never composes a query**; it picks a
tool name and fills its arguments, and no model output is ever concatenated into Cypher.

### `has_this_been_tried` — Has this idea been proposed and rejected before — and is anyone who made that call still here?

*Why a graph:* Vector KNN seeds the search, then the graph supplies what no embedding holds: which decision recorded it, who decided, and whether any of them still approve anything. A vector store alone returns the k nearest rows and can never return *nothing*.

```cypher
CALL db.idx.vector.queryNodes('NamedOption', 'emb', $k, vecf32($qvec)) YIELD node AS alt, score
WITH alt, score WHERE score <= $maxDist
MATCH (kep:Kep)-[:CONSIDERED]->(alt)
OPTIONAL MATCH (kep)-[:OWNED_BY]->(sig:Sig)
OPTIONAL MATCH (author:Person)-[:AUTHORED|APPROVED]->(kep)
OPTIONAL MATCH (author)-[liveRole:APPROVES]->()
WITH kep, sig, alt, score,
     collect(DISTINCT author.key) AS deciders,
     count(DISTINCT liveRole)     AS decider_live_roles
RETURN alt.title                             AS rejected_idea,
       alt.body                              AS rationale,
       kep.num                               AS kep,
       kep.title                             AS kep_title,
       kep.status                            AS status,
       sig.key                               AS sig,
       kep.url                               AS source_url,
       CASE WHEN kep.created_ms = 0 THEN -1
            ELSE ($now - kep.created_ms) / $msYear END AS years_ago,
       deciders,
       decider_live_roles,
       CASE WHEN decider_live_roles = 0 THEN 'NO_LIVING_OWNER' ELSE 'HAS_LIVING_OWNER' END
                                             AS rationale_ownership,
       round(score * 1000) / 1000            AS distance
ORDER BY score ASC
LIMIT $limit
```
`query_sha` = `52f160988857` — stamped on every answer this query produces.

### `orphaned_ownership` — Which areas have NO current approver at all, only departed ones?

*Why a graph:* This is the ABSENCE of an edge. A similarity score cannot express absence; it always returns its nearest neighbours however far away they are.

```cypher
MATCH (dep:Person)-[:EMERITUS_OF]->(f:OwnersFile)
OPTIONAL MATCH (cur:Person)-[:APPROVES]->(f)
WITH f, collect(DISTINCT dep.key) AS departed, count(DISTINCT cur) AS live_approvers
WHERE live_approvers = 0
RETURN f.path AS orphaned_area, departed, f.url AS source_url
ORDER BY f.path
LIMIT $limit
```
`query_sha` = `77d26d485483` — stamped on every answer this query produces.

### `departed_bridges` — Whose departure cost the most CONNECTIVE knowledge — not just the most files?

*Why a graph:* Betweenness centrality is a whole-graph property. No traversal, no SQL join and no embedding can compute it. Composed with an ownership traversal in the SAME query.

```cypher
CALL algo.betweenness({nodeLabels:['Person'], relationshipTypes:['CO_AUTHORED'], samplingSeed: $seed})
YIELD node, score
WITH node AS p, score AS bridge
MATCH (p)-[:EMERITUS_OF]->(f:OwnersFile)
OPTIONAL MATCH (p)-[liveRole:APPROVES]->()
WITH p, bridge, count(DISTINCT f) AS abandoned_areas, count(liveRole) AS live_roles
WHERE live_roles = 0 AND abandoned_areas >= $minAreas
RETURN p.key                        AS departed_bridge,
       round(bridge * 100) / 100     AS betweenness,
       abandoned_areas
ORDER BY bridge DESC
LIMIT $limit
```
`query_sha` = `09250c925dc8` — stamped on every answer this query produces.

### `successor_for` — Who already co-owns the areas a departed person left behind?

*Why a graph:* A co-ownership overlap across two relationship types. In SQL this is two self-joins whose result still cannot be returned as a path.

```cypher
MATCH (dep:Person {key: $handle})-[:EMERITUS_OF]->(f:OwnersFile)
WITH dep, collect(DISTINCT f) AS abandoned
UNWIND abandoned AS area
MATCH (cand:Person)-[:APPROVES]->(area)
WITH dep, cand, size(abandoned) AS total_abandoned, count(DISTINCT area) AS shared
MATCH (cand)-[:APPROVES]->(owned:OwnersFile)
RETURN cand.key                 AS candidate,
       shared                   AS shares_areas_with_departed,
       total_abandoned          AS departed_total_areas,
       count(DISTINCT owned)    AS candidate_total_areas
ORDER BY shared DESC, candidate_total_areas DESC
LIMIT $limit
```
`query_sha` = `81f20b2d0b57` — stamped on every answer this query produces.

### `broken_lineage` — Which cited decision records do not exist?

*Why a graph:* Inbound edges to a node that stands for something MISSING. Finding it requires resolving references across 679 decisions and counting arrivals at the gap.

```cypher
MATCH (k:Kep)-[:CITES_MISSING]->(m:MissingRecord)
WITH m, collect(DISTINCT k.num) AS citing_keps, count(DISTINCT k) AS cited_by
WHERE cited_by >= $minCites
RETURN m.key AS missing_record, cited_by, citing_keps
ORDER BY cited_by DESC, m.key
LIMIT $limit
```
`query_sha` = `032f655b6aa7` — stamped on every answer this query produces.

### `who_owns` — Who owns this area? (depth 1 — what any database serves)

*Why a graph:* A single join. Included deliberately as the control arm of the depth contrast.

```cypher
MATCH (p:Person)-[:APPROVES]->(o:OwnersFile {path: $path})
RETURN p.key AS approver, o.path AS area, o.url AS source_url
ORDER BY approver
LIMIT $limit
```
`query_sha` = `3076dff4e413` — stamped on every answer this query produces.

### `who_owns` — Who owns this area? (depth 4 — what the graph serves)

*Why a graph:* Four hops: area → departed owner → decisions they shaped → alternatives they personally rejected → the SIGs those reached. Returns the reason the depth-1 answer was silent.

```cypher
MATCH (o:OwnersFile {path: $path})
OPTIONAL MATCH (live:Person)-[:APPROVES]->(o)
OPTIONAL MATCH (dep:Person)-[:EMERITUS_OF]->(o)
WITH o, collect(DISTINCT live.key) AS live_approvers, collect(DISTINCT dep) AS departed
UNWIND (CASE WHEN size(departed) = 0 THEN [null] ELSE departed END) AS d
OPTIONAL MATCH (d)-[:AUTHORED|APPROVED]->(k:Kep)-[:CONSIDERED]->(a:Alternative)
OPTIONAL MATCH (k)-[:OWNED_BY]->(sig:Sig)
WITH o, live_approvers, d,
     collect(DISTINCT k.num)   AS decisions_they_shaped,
     collect(DISTINCT a.title) AS ideas_they_rejected,
     collect(DISTINCT sig.key) AS sigs_touched
RETURN o.path                    AS area,
       live_approvers,
       d.key                     AS departed_owner,
       size(decisions_they_shaped) AS n_decisions,
       decisions_they_shaped[0..5] AS sample_decisions,
       ideas_they_rejected[0..4]   AS sample_rejected_ideas,
       sigs_touched,
       CASE WHEN size(live_approvers) = 0 THEN 'ORPHANED' ELSE 'COVERED' END AS status
LIMIT $limit
```
`query_sha` = `e45ae59740b7` — stamped on every answer this query produces.

## The agent

Six tools. The model picks one and fills its arguments; hand-written Cypher answers; a
deterministic renderer phrases it. **The model never writes a query and never phrases a finding**,
so it cannot soften a negative into a maybe or name someone who isn't in the graph.

Every answer is one of four shapes:

| shape | meaning |
|---|---|
| `ANSWERED_WITH_PATH` | found it, and here is the traversal |
| `NOT_IN_GRAPH` | the traversal ran and returned nothing — **always** with a coverage statement |
| `UNKNOWN_ENTITY` | the name didn't resolve, so nothing else ran |
| `DEGRADED` | the graph is unreachable. No fallback. |

Entity names are resolved against the graph *before* any traversal, because a plausible wrong name
is worse than no answer. And a negative never stands alone — an empty traversal only means this
corpus doesn't record it, which the UI says in those words every time.

## Why FalkorDB, measured honestly

An adversarial reviewer argued the real incumbent at this scale isn't Postgres, it's `networkx`.
Fair, so I measured it — 3,300 nodes / 39,987 edges, same machine:

| operation | networkx | FalkorDB v4.22.1 | winner |
|---|---|---|---|
| build graph | 21.0 ms | 189.7 ms | **networkx, 9x** |
| 2-hop neighbourhood (p50) | 0.017 ms | 0.368 ms | **networkx, 22x** |
| **PageRank** | 1,529.1 ms | **10.0 ms** | **FalkorDB, 153x** |
| **betweenness (k=32)** | 351.6 ms | **19.8 ms** | **FalkorDB, 18x** |

networkx wins in-process pointer chasing. Of course it does — it's an in-memory adjacency dict, and
any claim otherwise is checkable in five minutes. The point is the other row: **PageRank at 1.5s is
an offline batch job; at 10ms it's a tool an agent can call inside a single conversational turn.**
That's a difference in kind. Plus the things networkx structurally cannot do: a vector index
composed with traversal in one query, physically isolated per-tenant graphs, concurrent access to
live shared state, durable persistence, and a path object returned by the query that found the answer.

Multi-tenancy, measured 1 → 1000 graphs: read p50 stays **flat** (0.42 → 0.38 ms), p99 *improves*
(2.34 → 0.82 ms), `select_graph` is ~1µs regardless of count, memory is linear at ~491 KB/tenant.
Isolation is physical — a second tenant running the identical Cypher gets `[]`, and `db.labels()`
doesn't even list the label. Honest caveat: 10,000 tenants × 491 KB ≈ 4.8 GB, so FalkorDB's "10K+
graphs" headline is memory-bound, not architecture-bound.

Full methodology and six engine gotchas I hit: [`docs/GROUND-TRUTH.md`](docs/GROUND-TRUTH.md).

## Honest limits

- **Betweenness is sampled**, not exact (`samplingSize` 32). The seed is pinned so the number is
  reproducible, but it is an approximation and the UI says so.
- **206 of 959 alternatives are untitled prose**, not named options. They're in the graph but
  excluded from `:NamedOption`, so they never seed a "has this been tried?" answer.
- **8 of 679 decisions have no usable date** — 3 omit the field, 5 still carry the template's
  literal `'yyyy-mm-dd'`. These render as "date not recorded", never as an age.
- Some sub-headings inside an `Alternatives` section are structural ("Implementation sketch") rather
  than real options. The deterministic parser cannot always tell.
- "No current approver" means *this corpus* records none. People own things informally.
- The corpus is a snapshot. Re-run `python src/tombstone/snapshot.py` against fresh clones to update.

## AI assistance disclosure

Built with AI coding assistance, as the rules permit and require disclosing.

The graph model, the tool boundaries, every Cypher query, the benchmark methodology and the
engineering decisions are mine. Every performance number here comes from a benchmark in `spikes/`
that I ran and can re-run. Where a research agent's figure disagreed with my own parse, **my parse
is used and the discrepancy is recorded** — the `OWNERS_ALIASES` correction in
`docs/K8S-CORPUS-VERIFIED.md` is one example, where an unexpanded group alias had turned 71 of 866
"people" into committees and understated ownership by 1,595 edges.

## Stack

Python · FalkorDB **v4.22.1** (pinned — `:latest` is untrustworthy and 6.x drops `algo.AStar`/`CCH`
and carries crash and silently-wrong-result bugs) · `fastembed` + BGE-small for embeddings, running
locally at ~5ms/query with no API cost · FastAPI · hand-written SVG for the path view, no graph
library.

Data: [kubernetes/enhancements](https://github.com/kubernetes/enhancements) and
[kubernetes/kubernetes](https://github.com/kubernetes/kubernetes) OWNERS, both Apache-2.0. No email
addresses are ingested, even though `sigs.yaml` publishes them — Rule 6 says "personal".
