# Tombstone — build plan

**Track 3, Company Brain.** Solo. Submit by **Oct 18, 18:00 IST** (6 hours before the 23:59 deadline).

## The pitch

> Large engineering orgs keep re-proposing things they already rejected, because the rejection was
> never a thing you could look up. Tombstone makes every rejected design option a node, attaches the
> person who killed it, and tells you whether anyone who knows why is still here.

Four questions, each a traversal, none answerable by search today:
1. **Has this been tried?** — and what was the recorded reason it was rejected.
2. **Who owns this, and did they already kill this idea elsewhere?**
3. **Which areas have no living owner at all?** (a negative, with a coverage statement)
4. **Whose departure cost the most connective knowledge?** (betweenness, not a file count)

## Why this and not the alternative

A design panel of six concepts plus eighteen adversarial critics ranked a clinical-trial
eligibility matcher first. **I am not building that, and the reason is deliberate:**

- Its own stated weakness is "the graph is beautiful and the input to it is a guess" — every node
  rests on one LLM pass over oncology protocol prose. Published accuracy for that extraction task
  (Criteria2Query) is **0.514**. A tool that tells a coordinator a screen-failed patient *can enter*
  a cancer trial, built on a coin-flip extractor in three days, is both a devastating judge question
  and genuinely irresponsible. Tombstone's worst failure mode is "we missed a precedent."
- Every feasibility critic independently judged all six plans **1.5–2x over-scoped**. Tombstone is
  already built and verified; the alternative needs ClinicalTrials.gov ingest, LLM criteria
  extraction, MONDO and ATC ontologies, a verdict engine and an extractor-accuracy study, from zero.
- The one fair critique of Tombstone was that its similarity edges would be computed in numpy and
  written back, making any algorithm over them decoration. **That critique does not apply to what
  was built** — there are no similarity edges. The projection is a 2-hop co-occurrence over shared
  decisions, computed in Cypher in 83ms, and the betweenness over it is computed by FalkorDB.

Grafted from the runners-up: `:Blindspot` nodes so coverage is a traversal rather than two
integers; a deterministic auditor that structurally removes the verdict field from the model's
response schema rather than asking it to hedge; and a `query_sha` on every answer so the README's
query catalogue is verifiably the thing that ran.

## The removal test (README text, and it is true)

> Turn FalkorDB off and here is exactly what stops working. "Has this been tried?" becomes grep over
> 688 markdown files — which is what contributors already have, and why the problem exists. The
> rejected alternative has no identity, so you cannot count how many times an idea was refused, and
> you cannot return *nothing*: a vector index always hands back its k nearest rows, which is how a
> plausible wrong answer gets produced. "No living owner" is the absence of an edge, and absence is
> not a thing a similarity score can express. And the ranking of whose departure hurt most is
> betweenness centrality — a whole-graph property that no traversal, join or embedding can compute.
> There is no in-memory mirror and no cached fallback in this repo. With the database off, it fails
> loudly.

## Measured facts this build rests on (all my own, all re-runnable)

| claim | measurement |
|---|---|
| full corpus ingest | **2.12s** (1.70s parse, 0.42s load) |
| edge loading technique | 222k edges/sec by internal `id()` vs 3k/sec by indexed property — **73x** |
| PageRank, 3.3k nodes / 40k edges | **10.0ms** vs networkx 1,529ms — **153x** |
| betweenness, same graph | **19.8ms** vs networkx 351.6ms — **18x** |
| multi-tenancy, 1 → 1000 graphs | read p50 **flat** 0.42→0.38ms, p99 *improves* 2.34→0.82ms |
| tenant isolation | physical: identical Cypher returns `[]` and `db.labels()` omits the label |
| cross-graph write parallelism | 1.64–1.67x at 4–8 writers — real but **bounded**, not linear |

networkx beats FalkorDB on 2-hop pointer chasing (0.017ms vs 0.368ms) and on build time. That is
stated plainly in the README, because a judge can check it in five minutes. The argument is not
"faster at everything" — it is that PageRank at 1.5s is a batch job and at 10ms it is a tool an
agent calls inside one conversational turn.

## Hour-by-hour, with a cut list

Already done (Oct 15, 15:00–16:30): corpus parser, graph builder, six-tool catalogue, four answer
shapes, vector index over 960 alternatives, seven verified queries, benchmarks, docker-compose with
the persistence fix.

| block | work | checkpoint |
|---|---|---|
| **Oct 15, 16:30–20:00** | Agent loop: tool selection against the fixed catalogue, LLM never writes Cypher. `:Blindspot` nodes. `query_sha`. | Agent answers all four question types from the terminal |
| **Oct 15, 20:00–23:00** | Deploy hello-world to the real always-on host **tonight**, not on day 3. Seed-on-boot. | A public URL serves a real query |
| **Oct 16, 09:00–14:00** | Web UI: question box, answer card, graph panel showing only the reasoning path | Depth-1 vs depth-4 contrast visible on screen |
| **Oct 16, 14:00–18:00** | Honest-negative UX: coverage panel, UNKNOWN_ENTITY handling, the kill-switch toggle | All four shapes render correctly |
| **Oct 16, 18:00–21:00** | README: graph data model diagram + the full Cypher catalogue (both Rule-10 required) | README complete |
| **Oct 17, 09:00–13:00** | Polish, no-signup demo mode, spend cap, mobile width | A stranger can use it with no key |
| **Oct 17, 13:00–17:00** | Record the 3-minute video. Scripted voiceover recorded separately from the screen capture. | Video uploaded |
| **Oct 17, 17:00–20:00** | Blog post (uncontested side prize — zero published so far) | Published, linked |
| **Oct 18, 09:00–16:00** | Buffer. Re-verify the live URL from another network in incognito, clean-clone the quickstart. | — |
| **Oct 18, 18:00** | **Submit.** Not 23:59. | — |

**Cut list, in order:** blog post → graph visualization polish (fall back to a static path list) →
`:Blindspot` nodes → the multi-tenant demo beat (stays as a README table) → UI entirely (ship a CLI
plus video). The agent loop, the six tools, the four answer shapes, the README data model and the
Cypher catalogue are **not** cuttable — they are the submission.

## Rules compliance

- Public repo, README with data model **and** the Cypher the product depends on, 3-minute demo video,
  live URL, one named track.
- Data is Apache-2.0 public (`kubernetes/enhancements`, `kubernetes/kubernetes` OWNERS). No email
  addresses ingested even though `sigs.yaml` publishes them — Rule 6 says "personal".
- AI assistance disclosed specifically: assistant wrote scaffolding and tests; the graph model, the
  tool boundaries, every Cypher query and the benchmark methodology are mine, and where a research
  agent's number disagreed with my own parse, my parse is used and the discrepancy is recorded.
- Pinned `falkordb/falkordb:v4.22.1`, not `:latest` — the tag is untrustworthy and 6.x has
  crash and silently-wrong-result bugs.

## Risks

| risk | trigger | mitigation |
|---|---|---|
| Deploy eats a day | not serving by Oct 15 23:00 | paid always-on container provisioned tonight; FalkorDB Cloud free tier is **not** an option (stops after 1 day idle, deleted after 7) |
| Graph viz becomes a hairball | more than 3h in | render **only** the reasoning path, never the full graph; fall back to a styled path list |
| LLM cost/rate limits in a public demo | any | key stays server-side, hard provider spend cap, pre-baked answers for the demo questions while the graph query still runs live |
| Scope creep (every critic's warning) | behind at any checkpoint | the cut list above, in that order |
| `nodus` is a live Track-3 competitor | — | different problem (postmortem lesson matching vs decision archaeology + ownership attrition) and different corpus; differentiate explicitly in the README |

## Clean-room verification (Oct 15, 17:50 IST)
The README promises `git clone && pip install && ./run.sh`. That promise had never actually been
tested from a fresh checkout, so I ran it as a judge would, in an empty directory.

**Result: it works** — but only after fixing two portability bugs the test exposed.

| step | result |
|---|---|
| `git clone` | 23 commits, 46 files, committed data intact (322KB corpus + 737KB vectors) |
| `python3 -m venv .venv && pip install -r requirements.txt` | 44 packages, **14s** |
| `./run.sh` | FalkorDB up, **seeded in 1.12s**, serving |
| `/api/health` | `falkordb: up`, 679 decisions / 753 named options / 794 people |
| 3 live tool calls | all `ANSWERED_WITH_PATH`, 12.9–19.6ms |
| `/`, `/app.js`, `/style.css` | HTTP 200 |

### The two bugs it caught
1. **`run.sh` called bare `python`.** Plenty of systems only ship `python3`, and on others `python`
   resolves *outside* the venv the README just told you to create — so the dependencies you had
   just installed would appear missing. It now prefers `./.venv/bin/python`, then `$VIRTUAL_ENV`,
   then `python3`, then `python`, and says which it picked.
2. **The quickstart said `cd "graph hack"`**, which is not what a clone produces. Now
   `git clone <repo> tombstone && cd tombstone`.

`run.sh` also now fails fast with a readable message when Docker is absent or a dependency is
missing, rather than halfway through.
