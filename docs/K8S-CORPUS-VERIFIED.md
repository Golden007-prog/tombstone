# Kubernetes governance corpus — numbers I verified MYSELF (2026-10-15)

> **Read this as a working record, not as current figures.** It is what the raw corpus looked like
> while I was still working out what it was, and several numbers in it were later found wrong and
> corrected. The corrections are in [the table near the bottom](#corrected-figures), which says
> plainly that it supersedes what is above it — but the README now links here, so the warning
> belongs at the top rather than two hundred lines down.
>
> The two that matter most, because they appear in the prose below as if settled:
>
> - **"88 of 111 departed owners"** — it is **83 of 111**. The first pass had not expanded
>   `OWNERS_ALIASES`, so some people counted as having no current role did hold one through a group.
> - **"74 of 370 internal pointers (20.0%) do not resolve"** — it is **55 of 358 (15.4%)**. Some
>   targets had moved rather than vanished, and the resolver was treating a move as a break.
> - **"`/keps/sig-network/0752-endpointslices` is cited by FIVE separate KEPs"** — there is no such
>   missing record in the graph at all; nothing matching `endpointslice` is missing. The real
>   standout is `/keps/sig-api-machinery/0006-apply.md`, cited by **four**, which the README says
>   and which the timing table further down this same file says. It is listed here because the
>   paragraph below calls it "The standout", and this warning exists for figures that read as
>   settled — leaving out the one wearing that word would defeat the point of writing it.
>
> Both corrected figures are the ones the README quotes, and both are re-derived from the live
> graph on every push. The numbers here that are *about the raw files* — 684 `kep.yaml` parsed,
> 688 READMEs, 586 against 585 OWNERS — are not stale versions of the graph's counts; they are
> different quantities, measured before templates were excluded.

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

## Hybrid retrieval over real KEP text — built and tuned
Extracted the `Alternatives` / `Drawbacks` / `Risks and Mitigations` sections from 684 KEP READMEs.

**Trap found and fixed:** the first pass returned 4 hits at IDENTICAL distance 0.296, all of them the
KEP template's own HTML comment (`<!-- What other approaches did you consider... -->`) which authors
routinely leave in place. Stripping `<!--.*?-->` before chunking took 1,817 chunks -> 1,520 clean ones
and removed the contamination entirely. Any build on this corpus MUST strip HTML comments first.

**Embedding throughput reality check:** 8.4 chunks/sec on real ~1,400-char chunks, NOT the 181/sec I
measured on short synthetic strings. 1,520 chunks took 181s. Longer text = more tokens = slower.
Cache embeddings to disk (pickle) or you pay 3 minutes on every run.

Retrieval quality after the fix (vector index, 384-dim, cosine):
| question | top hit |
|---|---|
| "we considered using a sidecar container but rejected it" | **KEP-4633** (dist 0.281): "A sidecar proxy could have handled this but would push complexity into all consumers" |
| "why not just use a CRD instead of a built-in API type" | KEP-2221 risks (0.224), KEP-5304 drawbacks (0.229) |
| "rejected because it would break backward compatibility" | **KEP-2172** (0.274): "Changing defaults and making users opt-in to running as root was considered. This is a breaking..." |
Query latency 2.9-9.8ms.

**Hybrid query (vector seed -> lineage + ownership + staleness) runs in 32.6ms** and returns what the
embedding cannot: decision-ancestry depth, whether the decision cites a MISSING record, who authored
it, and whether those authors are still active.

## CORRECTION — OWNERS_ALIASES expansion (a real bug in my first ingest)
My first pass treated every entry in an `OWNERS` `approvers:` list as a person. It is not. Kubernetes
OWNERS files reference **group aliases** (`sig-api-machinery-approvers`), expanded by a separate file:
`https://raw.githubusercontent.com/kubernetes/kubernetes/master/OWNERS_ALIASES` (HTTP 200, 13,440 bytes)
= **74 aliases -> 449 memberships**.

Consequence of missing it: **71 of 866 `Person` nodes (8.2%) were groups masquerading as humans**, and
**293 approver references** were never expanded to real people, understating ownership.

## Corrected figures

(alias-expanded; these supersede the ones above)

| metric | first pass (wrong) | corrected |
|---|---|---|
| distinct people holding a current approver role | — | **157** |
| distinct people in `emeritus_approvers` | 111 | 111 (no aliases appear in emeritus — clean) |
| **departed owners with NO current approver role** | 88 of 111 (79%) | **83 of 111 (75%)** |
| `deads2k` total areas owned | 59 | **147** |
| `deads2k` overlap with lavalamp's abandoned areas | 21 | **22 of 31** |

Corrected successor ranking for lavalamp's 31 abandoned areas:
`deads2k` 22 · `liggitt` 20 · `sttts` 18 · `smarterclayton` 17 · `jpbetz` 17 · `wojtek-t` 11.

**Rule for any build on this corpus: load OWNERS_ALIASES first and expand before creating Person nodes.
Also filter bots (`kubernetes-prow[bot]` is the single top committer in the git history).**

## FINAL graph numbers (after excluding template files)

> **These drifted and were corrected on 16 Oct.** The table said 679 Kep, 959 Alternative (753
> titled) and 52 MissingRecord, against a graph that builds 681, 958 (752) and 47. The counts
> moved as the corpus and resolver changed and nothing re-checked this page, which is the same
> failure the README documents elsewhere. The numbers that matter are asserted in
> `verify_claims.py` and re-run in CI; this file is a narrative of how the corpus was understood
> and is corrected rather than maintained.
The KEP templates themselves (`NNNN-kep-template`, `0000-cloud-provider-template`) were being
ingested as decisions. They carry placeholder metadata (`kep-number: NNNN`,
`creation-date: 'yyyy-mm-dd'`) and showed up as a decision with no date and no author — which
rendered as "55y ago" because an unparsed date became epoch 0. Both now excluded.

| | count |
|---|---|
| Kep | **681** |
| Alternative | 958 (752 titled `:NamedOption`, 206 untitled prose) |
| Person | 794 (alias-expanded, bots filtered) |
| OwnersFile | 585 |
| MissingRecord | 47 |
| Sig | 23 |
| -[:APPROVES]-> | 2,584 |
| -[:EMERITUS_OF]-> | 298 |
| -[:CO_AUTHORED]-> | 5,894 (computed in Cypher, 95ms) |
| lineage resolved / broken | 300 / 70 |

Remaining date gaps: **8 of 679** KEPs have no usable `creation-date` — 3 omit the field entirely,
and 5 still carry the literal template string `'yyyy-mm-dd'`. These render as "date not recorded",
never as an age.

**Cold start from the committed snapshot: 1.07-1.18s** including the vector index and all 959
embeddings. That is the whole product bootstrapping, which is what makes a free-tier deploy viable.
