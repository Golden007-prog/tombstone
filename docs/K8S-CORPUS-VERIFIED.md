# Kubernetes governance corpus — numbers I verified MYSELF (2026-10-15)
Clones: `kubernetes/enhancements` --depth 1 (93MB, Apache-2.0) and `kubernetes/kubernetes` --depth 1 (396MB).
All figures below are from my own YAML parse, not from docs or a subagent. A research agent reported
different (inflated) figures; where we differ, THESE are authoritative because I parsed YAML and
classified reference types instead of grepping.

## Decision lineage (kubernetes/enhancements)
- **684** `kep.yaml` files parsed cleanly (2 YAML failures), 688 KEP READMEs, 22 SIG dirs.
- **538** total lineage reference VALUES across `replaces` / `superseded-by` / `see-also`
  (field occurrence by file: see-also 419, replaces 260, superseded-by 56).
- Classified honestly:

| category | count |
|---|---|
| internal -> resolves by KEP number | 248 |
| internal -> resolves by dir | 45 |
| internal -> legacy flat layout (migrated) | 3 |
| **internal -> DOES NOT RESOLVE** | **74** |
| external URL (legitimate reference) | 119 |
| placeholder `n/a` / `TBD` | 37 |
| markdown link (legitimate) | 12 |

- **Honest headline: 74 of 370 internal KEP pointers (20.0%) do not resolve.** Not "16%", not "36%" —
  both of those conflate external URLs and unfilled template placeholders with real breakage.
- The standout: **`/keps/sig-network/0752-endpointslices` is cited by FIVE separate KEPs and resolves
  to nothing.** Five decisions claim descent from a record that is not there. Detecting this needs the
  graph: you must resolve refs across 684 KEPs and count INBOUND edges to a missing target.
- **202** KEPs are still `provisional`/`implementable` AND older than 3 years. Oldest:
  9.1y `sig-storage/284-enable-volume-expansion`, 8.8y `sig-cloud-provider/2392-cloud-controller-manager`,
  8.7y `sig-cluster-lifecycle/clusterapi/2495-Kubernetes-Cluster-Management-API`, 8.4y `sig-node/4265-proc-mount`.
- Recorded NEGATIVE decisions exist with rationale: 11 withdrawn, 7 replaced, 3 rejected, 1 superseded,
  1 deferred, 1 removed.
- Rejected-alternative substrate (the "latent node" candidate): **546** READMEs have an `Alternatives`
  section, 573 `Risks and Mitigations`, 476 `Drawbacks`, 654 `Implementation History`.
- Data is genuinely messy (good for credibility): `status: imlpemented` typo, unreplaced template
  strings like `status: provisional|implementable|implemented|...`.

## Ownership attrition (kubernetes/kubernetes OWNERS)
- **585** OWNERS files parsed as YAML, **0 parse failures**. 447 declare `approvers`.
- **138 (23.6%)** declare `emeritus_approvers` — the project records its own knowledge loss in a
  machine-readable field that nobody queries.
- **298** emeritus entries, **111** distinct departed people.
- **88 of 111 departed owners (79%) appear in ZERO current `approvers` list anywhere in the repo** —
  their institutional knowledge has no in-repo successor path at all. This is my own derived finding
  and it is sharper than anything the research agents produced.
- Top departed owners by number of OWNERS files they are emeritus in:
  `lavalamp` 31, `stewart-yu` 20, `vishh` 14, `spiffxp` 9, `matchstick` 8, `timothysc` 7, `gmarek` 7,
  `ixdy` 6, `pmorie` 6, `jbeda` 5. (`lavalamp` is emeritus in 31 files and in zero current approver lists.)

## Why this corpus is the right answer to Track 3's hard constraint
Track 3 wants docs/tickets/chats + ownership + expertise + decision tracing + staleness, but the rules
forbid private company data and ~95% of the field is faking an "Acme Corp". Kubernetes is a real
organisation of ~thousands of people that publishes its decision records, its ownership map, AND its
own attrition — under Apache-2.0. Every number above is checkable by a judge in one `git clone`.

## Caveats to state in the README
- `find -name OWNERS` returns 586; an `os.walk` parse yields 585 parseable files. Quote 585 parsed.
- Do NOT ingest the email addresses in `kubernetes/community` sigs.yaml — Rule 6 says "personal".
  Keep GitHub handles, names, company field. Say so in the README; it is a free credibility point.
- Unauthenticated GitHub REST is 60 req/hour — use git clones, never the API, for ingest.

## WORKING END-TO-END PROOF (built and run 2026-10-15)
Full ingest of both repos into FalkorDB: **1.65 seconds** using the two-phase id() technique.
Graph: 684 Kep, 866 Person, 585 OwnersFile, 23 Sig, 58 MissingRecord
Edges: 4393 WORKED_ON, 989 APPROVES, 684 OWNED_BY, 298 WAS_APPROVER, 300 lineage (291 SEE_ALSO,
8 REPLACES, 1 SUPERSEDED_BY), 70 CITES_MISSING.

| query | time | result |
|---|---|---|
| Q1 orphaned expertise | 20.4ms | 88 departed owners with zero current approver role. `lavalamp`: 31 areas abandoned, 57 KEPs authored. |
| **Q2 proof-by-absence** | **12.6ms** | **7 code areas where EVERY recorded owner departed and there are ZERO current approvers** (`pkg/controller/podgc` -> gmarek, foxish; `cluster/gce`; `pkg/kubelet/cm/devicemanager` -> vishh, jiayingz) |
| Q3 broken lineage by inbound | 5.3ms | 58 missing records. `/keps/sig-api-machinery/0006-apply.md` cited by 4 KEPs (491, 2155, 1027, 1101). |
| Q4 multi-hop ancestry 2..4 | 72.3ms | 2,679 chains. e.g. 6313 -> 4817 -> 4680 -> 3573 -> 606 (4 hops). |
| Q5 successor recommendation | 6.5ms | `deads2k` already approves **21 of lavalamp's 31** abandoned areas; liggitt 19; smarterclayton 17. |
| Q6 stale-but-load-bearing | 6.4ms | KEP-606 (2018-07-19, still `implementable`) is cited by 5 other decisions. 37 such KEPs. |
| Q7 pageRank / WCC | 4.1 / 2.3ms | hot-path fast on the real graph |

### Honest caveats found while testing
- `betweenness` and `labelPropagation` are DEGENERATE on this schema (all scores 1.0, communities of
  size 1) because `Person-[:WORKED_ON]->Kep` is bipartite. They need a Person<->Person co-authorship
  projection to be meaningful. Only claim pageRank + WCC unless the projection is built.
- Q4 returns 2,679 rows — must be capped and ranked for any UI or demo.
- **New FalkorDB gotcha:** `exists((p)-[:R]->())` FAILS with `_AR_EXP_UpdateEntityIdx: Unable to locate
  a value with alias` when `p` arrives via an AGGREGATING `WITH`. Use `OPTIONAL MATCH` + `count()` = 0
  instead. This is in addition to `EXISTS { MATCH ... }` being unsupported entirely.
- Refined reference resolution (handling a leading `/keps/`) gives **70 broken of 370 internal
  pointers = 18.9%**, slightly better than my earlier 74/20.0%. Quote 18.9% / "70 of 370".

## Person<->Person CO_AUTHORED projection — fixes the degenerate-algorithm problem
Built from 3,576 WORKED_ON edges over 684 KEPs -> **5,894 co-author pairs** (weight = shared KEPs).
Projection build: 0.14s total. Now every algorithm is meaningful:

| algorithm | time | top results |
|---|---|---|
| betweenness (who bridges groups) | 10.2ms | dchen1107 1393.5, liggitt 1252.0, derekwaynecarr 821.8, johnbelamaric 647.6 |
| labelPropagation (communities) | 11.9ms | real communities of 256 / 242 / 114 / 25 / 17 / 16 (was all size-1 before) |
| pageRank (central contributors) | 5.6ms | thockin 0.0239, wojtek-t 0.0204, yastij 0.0146 |
| HarmonicCentrality | 14.5ms | andrewsykim 311.5, ahg-g 295.0, aojea 291.3 |
| WCC (islands) | 7.2ms | one giant component of 731 + a handful of singletons |

### THE HEADLINE QUERY — algorithm + traversal in ONE query, 14.0ms
"Departed owners who were STRUCTURAL BRIDGES between contributor communities."
```cypher
CALL algo.betweenness({nodeLabels:['Person'],relationshipTypes:['CO_AUTHORED']}) YIELD node, score
WITH node AS p, score AS bridge_score
MATCH (p)-[:WAS_APPROVER]->(f:OwnersFile)
OPTIONAL MATCH (p)-[cur:APPROVES]->()
WITH p, bridge_score, count(DISTINCT f) AS abandoned, count(cur) AS active
WHERE active = 0 AND abandoned > 2
RETURN p.key AS departed_bridge, round(bridge_score*100)/100 AS betweenness, abandoned
ORDER BY bridge_score DESC
```
Result: `ehashman` 222.72 / 3 areas, **`lavalamp` 190.93 / 31 areas**, `logicalhan` 131.57 / 5,
`timothysc` 64.47 / 7, `pmorie` 25.37 / 6, `jbeda` 12.21 / 5.

Why this is the strongest "graph is load-bearing" artifact available:
1. Betweenness centrality CANNOT be computed by a traversal, a SQL join, or a vector search. It is a
   whole-graph property.
2. It is composed with a traversal (WAS_APPROVER present, APPROVES absent) in the SAME query, so the
   provenance is real, not reconstructed.
3. It answers a question a human actually asks — "whose departure cost us most?" — and the answer is
   actionable (pair it with Q5's successor recommendation).
4. 14ms: it runs inside the agent's turn, not as an offline batch job.
