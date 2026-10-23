# Be ready to explain it

Rule 12 says participants must be able to explain the graph model, the queries, the architecture
and the technical decisions. Rule 13 says a project nobody understands or verified may be rejected.

The README is long because it carries its evidence. This file is the opposite: the questions a
judge is most likely to ask, and the answer, short enough to hold in your head. Every number here
is re-derived by `./preflight.sh`, so if one has moved, that command says so.

---

## "What problem does this solve?"

Large engineering organisations re-propose things they already rejected, because the rejection was
never a thing you could look up. A rejected option is not a document — it is a 200-word subsection
inside a 4,000-word proposal about something else. It has no identity, so you cannot count how
often an idea was refused, ask who refused it, or find out whether anyone who knows why is still
around.

**Say this too:** that premise is measured in the README and it *could not be confirmed* on this
corpus. Volunteering that is stronger than being caught by it, and it is why the product's lead
finding is an ownership one rather than a repetition one.

## "Why does this need a graph?"

The headline finding — one person is the entire review capacity for the Kubernetes apiserver's
metrics endpoints — is not written down anywhere. It is only true as a consequence of structure:
who is listed where, which files inherit from which, and who has since stepped back. Getting it
needs a traversal with a variable number of hops, and two of the questions need whole-graph
properties (betweenness centrality, community detection) that no search index or embedding
produces.

The sharpest version: **`who_owns` at depth 1 returns nothing. At depth 4 it names the person.**
Same question, same data. That gap is the product.

## "Walk me through the data model."

Seeded: **3,087 nodes, 15,735 edges**. (A live instance reads slightly higher — the agent's own
memory adds `(:Answer)` nodes and `CITED` edges as it is used.)

| label | n | what it is |
|---|---|---|
| `Person` | 794 | a GitHub handle |
| `Kep` | 681 | a decision record |
| `OwnersFile` | 585 | an ownership file |
| `Alternative` | 958 | a rejected option, lifted out of the prose it was buried in |
| `NamedOption` | 752 | **a second label on the 958**, not a separate node |
| `UnnamedOption` | 206 | the complement, and the other index scope. In this engine an index scope IS a label, so the 206 the vector index cannot hold carry a full-text index on `.body` instead. Disjoint from `NamedOption` by construction, which is what lets one answer say which index found each row |
| `MissingRecord` | 47 | a record cited by name that does not exist |
| `Sig` | 22 | a special-interest group |

The edges that matter: `APPROVES` (2,584) is current authority, `EMERITUS_OF` (298) is authority
that was given up, `INHERITS_FROM` (584) is the ownership chain the depth-4 traversal walks,
`CONSIDERED` (958) joins a decision to what it rejected, and `CO_AUTHORED` (5,879) is the
collaboration graph the whole-graph algorithms run over.

**The decision to be ready to defend:** why the vector index holds 752 `NamedOption` and not all
958 `Alternative`. Say it in this order, because the page got it wrong twice before this.

The other 206 are **all real rejections**. Every one carries at least 100 characters of argument,
which is the floor the build applies before it makes a node, and every one carries a 384-dimension
vector. They are **embedded and deliberately unindexed** — not, as this page used to say, "not
embedded". Re-embedding the body reproduces the stored vector at cosine 1.0000, which is also how
we know the embedding is over the body and the title is display text only.

So the gap is structural: the vector index is minted on `:NamedOption`, and a node outside an
index scope has probability zero of being returned by it. For a day that was the whole answer, and
the honest version of it was **"up to 206 rejections out of 958 cannot be reached by the tool whose
whole job is finding them"**.

**That is no longer the answer, and the number to give is 46.** On 17 Oct the 206 got a *full-text*
index on `.body` under their own label, `:UnnamedOption` — in this engine an index scope IS a
label, which is what makes two scopes over one set of nodes possible at all. The tool consults it
only when the question contains a name the engine's own tokeniser would split: a word containing
`-` `.` `_` or `/`. So **160 of the 206 are now reachable by name, and 46 carry no splittable name
at all and are exactly as unreachable as before.** Ask about `kube-state-metrics` now and the two
bodies that name it come back, tagged `found_by: name` and appended after the similarity rows, so
`rows[0]` is still the nearest by distance. If asked for this product's biggest recall weakness,
that residual 46 is the honest answer — and the reason the answer changed is worth saying out
loud, because the measurement that made the old one feel permanent is in the next paragraph.

**And be ready for the obvious follow-up — why not just widen the index?** Because it was measured
rather than assumed. `bench_index_scope.py` pools all 958 into one index and scores both: named
options asked for by their own sub-heading drop from 48.2 / 64.8 / 72.8% to 45.8 / 61.8 / 69.8% at
k=1/3/8, while the excluded set goes from 0/25 to 19/25 reachable. Three points of precision
against structural reachability is a genuine trade; the shipped build keeps the pre-filter, and
the script that would have overturned that decision is committed next to the one that justifies
it. The real fix is a better extractor, which is a re-ingest.

## "What do the thirteen tools do?"

Four answer ownership, three answer decisions, three are whole-graph, one is a counterfactual, one
is memory, one acts.

| tool | question |
|---|---|
| `who_owns` | Same question at two depths. Depth 1 is what any database serves; depth 4 is the graph. |
| `ownership_dilution` | Which areas lost every dedicated owner, and who inherits them now? |
| `sole_approver_risk` | Which areas have exactly one approver, and who is it? |
| `stepped_back_but_still_listed` | Whose record is lopsided: stepped back from many areas, still listed in one? |
| `successor_for` | Who already co-owns the areas a departed person left behind? |
| `has_this_been_tried` | Has this idea been proposed and rejected before, and is anyone left who knows why? |
| `stale_knowledge` | What does this graph know that is going stale? |
| `broken_lineage` | Which cited decision records do not exist? Inbound edges to a missing node. |
| `stepped_back_bridges` | Who held the most *connective* authority before stepping back — not the most files? |
| `hollowing_communities` | Which contributor community is losing its people fastest? |
| `what_if_they_go` | If this cohort stops approving, which areas are stranded? Runs on a forked copy. |
| `recall` | Has this been asked before, and do the records it cited still exist? |
| `draft_owners_patch` | Turn the finding into a reviewable patch — and refuse the cases it cannot justify. |

## "Which FalkorDB features, and why each one?"

- **`algo.betweenness`** (`stepped_back_bridges`) — "most connective authority" is betweenness, not
  degree. Seeded with `samplingSeed:42` so the answer is reproducible; an unseeded sample would
  make the demo's named person change between runs.
- **`algo.labelPropagation`** (`hollowing_communities`) — communities are discovered from the
  co-authorship graph, not declared by the org chart, which is the point: the group that is
  hollowing out is not a team anyone named.
- **`GRAPH.COPY`** (`what_if_they_go`) — the counterfactual removes people's approvals and re-runs
  the traversal. On a fork, so the live graph is never mutated. This is the one place `GRAPH.COPY`
  genuinely earns its cost; be ready to say it forks the server process and needs memory headroom
  roughly equal to the graph, which is why the deploy check asserts a serial ceiling at 512MB.
- **Vector index** (`has_this_been_tried`, `recall`) — "has this been tried" is a similarity
  question over 752 embedded options; exact text match would miss every rephrasing.

**If they ask what you would do differently:** the published WCC number was removed because
`algo.WCC` called with two arguments returns zero rows and no error — the timing I had published
was the cost of computing nothing.

## "What does the model do, and what does it never do?"

The model picks **one tool name**. That is all. It never writes Cypher, never extracts an entity,
never phrases a finding. All thirteen queries are hand-written constants; the depth argument does
not template into the query, because two separate constants exist and anything other than 1 or 4
is clamped to one of them.

**On the hosted demo there is no model at all.** Free-text questions are routed locally by
embedding similarity, with an out-of-domain bucket so that "write me a poem about kubernetes"
is declined by name rather than scored into the nearest tool. That bucket exists because the
router *did* route the poem into the patch-drafting tool at 0.631, and raising the threshold would
have rejected a real question at 0.674.

## "What happens if you take FalkorDB out?"

There is a README section that answers exactly this, and the honest summary is: the four
ownership questions degrade to wrong-but-plausible, and the three whole-graph ones stop existing.
Against **two** baselines over the same documents the graph scores **24 of 25**, versus **9 of 25**
for TF-IDF and **10 of 25** for dense retrieval with this product's own embedding model, across
seven categories. The number to lead with is not that one: it is that on the *control* category —
lookups where the answer sits in one document — **all three tie, nine apiece**. That tie is what
makes the other fifteen mean anything, and the graph loses the title lookup outright. Volunteer
both before anyone finds them.

**And if they ask the obvious follow-up — "that is keyword search, what about embeddings?" — the
answer is one question.** Dense retrieval buys exactly one of the twenty-five over TF-IDF, an
inheritance question, and still scores zero on expertise, whole-graph properties, absence,
currency and the counterfactual. Not because the retriever is weak, but because for those there
is no document to retrieve: the answer was never written down. That baseline runs in CI rather
than in `./preflight.sh` — embedding 2,224 documents is minutes of CPU, which belongs on a runner.

## "Why a vector index and not FalkorDB's full-text index?"

Both exist here and both were spiked — `db.idx.fulltext.createNodeIndex` works and returns a
BM25-ish score, which is written up in `docs/GROUND-TRUTH.md`. The reason the product routes
`has_this_been_tried` through the vector index is that the question is *"has anyone proposed this
before"*, asked in the asker's words about a rejection written in someone else's. BM25 scores
shared terms; it cannot match "let the kubelet own this state" to a KEP that wrote "node-local
ownership of the resource". The eval shows the same thing from the other side: the TF-IDF
baseline is a keyword retriever over these exact documents and it answers 9 of 25.

**The honest caveat**, because it cuts the other way: a keyword index is the better tool for the
206 options the vector index excludes — they are unindexed, not unembedded. That caveat used to
end "a re-ingest rather than an afternoon", and that was wrong: it was an afternoon, and no
re-ingest. The 206 now carry a full-text index on `.body` under their own label, reaching 160 of
them by name, and the precision cost `bench_index_scope.py` measured for *pooling* them into the
ANN index is avoided because the two indexes stay disjoint rather than merging — the answer reports
which one found each row. The residual 46 have no splittable name for a keyword index to match,
so for those the real fix is a better extractor that gives them titles, not a third index.

## "Three thousand nodes is tiny. Why a graph database at all?"

The right answer is not "scale", and claiming it would be would be easy to puncture: 3,087 nodes
and 15,735 edges fit in a laptop's memory, and this repository publishes a benchmark that
**withdraws** its own networkx comparison — re-measured on the real graph, betweenness is a 1–2x
difference, not the 18x an earlier table claimed. At this size a graph library would run the
algorithms perfectly well.

What a library would not give you is one store where four different shapes of question are the
same data: a variable-hop traversal to the nearest live ancestor, an ANN search over embedded
prose, a counterfactual that forks the whole graph with `GRAPH.COPY` and drops it, and the
agent's own memory written back as nodes that `CITED` the records an answer came from. Do that
with a library and you are maintaining four stores and the joins between them, and the memory
cannot invalidate itself when the records it cited stop resolving — which is the one feature here
that depends on all of it being the same graph.

## "What is the write path, and what happens under concurrency?"

Writes are small and there are only two kinds. Every answered question becomes one
`MERGE (a:Answer {qid})` plus a `MERGE` per citation, so re-asking is idempotent by construction
rather than by checking first. The corpus itself is never written at runtime: `build()` drops and
reseeds the graph from a committed snapshot, which is why a restart needs no restore and nothing
can be half-migrated. **~1.1s** against a FalkorDB that is already up, which is the local case and
the figure the comparison table in the README uses; **6.1s** cold inside the container, where the
server is starting at the same time; **2.26s** in the container running as UID 1000. This answer
used to say "about six seconds" flat, which quoted the container figure at someone asking about a
restart and disagreed with the README by five and a half times.

Concurrency was measured rather than reasoned about — and then the hosted instance was killed by
it anyway, on **17 Oct**, because the measurement was pointed at the wrong thing. The suspect was
`GRAPH.COPY`, which forks and needs headroom roughly equal to the graph; six at once were fired at
every deploy and came back **five answered, one degraded honestly, no hard failures**. All true,
and not the problem. The multiplier was the **embedder**: ONNX Runtime takes its own ~119 MiB
arena per concurrent run, so four people typing at once exceeded a 512 MB box while six
counterfactuals fitted in 319 MiB. Embedding is now serialised process-wide, the allocator is
bounded, and the check runs at the hosted size: **288 MiB under eight concurrent asks on
linux/amd64**, where the same flood was previously OOM-killed on the first round. The **live
instance reports its own figures** through `/api/health` — 91.6 MiB idle, 263.7 MiB after sixteen
concurrent asks, 248 MiB of headroom — so that claim is checkable against the URL rather than on
my word, which is the whole reason the field exists. The degraded
counterfactual is still the behaviour to point at: it returns `DEGRADED` with a reason rather than
a wrong answer or a timeout.

## "How do you know any of this is true?"

One command: `./preflight.sh` — twenty-four checks. The graph counts are re-derived against the
live database; the benchmark ratios are reported with their conditions rather than gated.
37 CI steps on every push, 39 runs because two repeat across Python 3.11 and 3.14. 190 tests. Each answer in the UI carries its Cypher, that query's hash, the arguments it was answered with,
a coverage statement, and a line saying no model wrote the prose.

## "What is weakest?"

Say these before you are asked:

1. **The premise did not confirm.** Measured, written up, lead finding changed as a result.
2. **Tenant isolation is "Partly".** The mechanism is measured to 1,000 graphs, but this app is
   single-tenant and never switches graphs, so it does not itself isolate anything.
3. **Docs only — no tickets, no chats.** The rules forbid private data and a fabricated Acme Corp
   proves nothing. Kubernetes publishes its decisions, its ownership map *and* its attrition.
4. **A withdrawn benchmark.** The networkx comparison claimed an 18x betweenness win on a graph
   that was not this product's. Re-measured on the real one it is 1–2x, and the claim is struck
   through rather than deleted. PageRank held up, at 30–145x across machines — the low end
   is a loaded laptop, and the range is reported rather than gated because gating a ratio
   turned CI red for a claim that was never false.
5. **Four of fourteen questions draw a reasoning path**, not all of them — there is no path to
   draw for "which areas have exactly one approver", and inventing a picture for a list would be
   decoration.

The reason to lead with these: every one of them is already written down in the repository, so a
judge who finds them finds them *already disclosed*. That is a much better position than having
them discovered.
