# Kubernetes writes down who left. Nothing reads it.

*Building a company brain on a graph, and six things FalkorDB taught me the hard way.*

---

There is a field in Kubernetes' `OWNERS` files called `emeritus_approvers`. It is the project's
record of people who used to own a piece of the codebase and have since moved on. It is plain YAML,
fully public, and it has been accumulating for years.

I parsed all 585 `OWNERS` files in `kubernetes/kubernetes`. **138 of them (23.6%) declare emeritus
approvers — 298 entries covering 111 distinct people.** Then I asked the question the field exists
to support and nobody asks: how many of those people hold no approval authority
anywhere in the repository?

**83 of 111. Seventy-five percent.**

And seven directories have lost *the approval authority of every owner they named*. `pkg/controller/podgc` is
owned, on paper, by two people who are both gone.

They are not unowned — I got that wrong first time, and it is worth saying why. Kubernetes OWNERS
files **inherit**: a directory is covered by its ancestors' approvers unless it sets
`no_parent_owners`. So `podgc` is still approvable, by the ten people who own `pkg/controller`.
What actually happened is subtler and more interesting: approval **silently widened** to a group
that never signed up for that code. Finding who inherited it means walking up the tree.

That is not a Kubernetes problem. Kubernetes is unusual because it writes its attrition down in a
machine-readable field. Every large engineering organisation has this; most just cannot see it.

So I built something to ask it questions.

---

## The thing that is not a document

I was building for a hackathon track called "Company Brain" — an agent that understands how an
organisation works. The rules forbid private company data, which turns out to be the interesting
constraint: about 95% of the entries I surveyed invented an "Acme Corp" and generated its documents
with an LLM. That makes "trace this decision back to its source" circular, because you generated the
source.

Kubernetes is a real organisation of thousands of people that publishes its decision records
(Enhancement Proposals), its ownership map (`OWNERS`), and its attrition (`emeritus_approvers`),
all under Apache-2.0.

But the thing I actually wanted was buried. Every KEP template has a section called **Alternatives**
— the options the authors considered and rejected, and why. Here is a real one, from KEP-6061:

> *"Kubelet-Managed Pull into the Localhost Profile Directory — The kubelet could pull profile
> artifacts itself and place them under its seccomp profile root…"*

That paragraph is the most valuable thing in the document and it is structurally invisible. It is
not a document, so it is not in any index. Search for "should the kubelet manage this" and you get
the *proposal*, ranked by similarity to all four thousand of its words, with the one paragraph that
says "we tried that, here is why not" diluted into noise.

So I made it a node.

**753 titled rejected options**, extracted deterministically from sub-headings — no LLM, because the
template produces them and a regex is reproducible where an extraction pass is not. Each one links
to the decision that recorded it, which links to the people who approved it, which links to whether
those people still approve anything.

The second latent node is stranger. KEPs cite each other through `replaces`, `superseded-by` and
`see-also`. I resolved all of them and **63 of 363 internal pointers (17.4%) go nowhere**. So I made
the *absent* record a node too. Now you can ask which missing documents are load-bearing:
`/keps/sig-api-machinery/0006-apply.md` does not exist, and **four separate decisions claim descent
from it.**

You cannot find that by searching. You find it by counting inbound edges to a gap.

---

## Eight things FalkorDB taught me the hard way

I measured rather than trusted, and most of what follows cost me time.

### 1. The volume path everyone will get wrong

`CONFIG GET dir` returns `/var/lib/falkordb/data`. `/data` is only a **symlink** to it. So the
conventional Redis-style mount —

```yaml
volumes:
  - falkordb-data:/data          # WRONG
```

— shadows the symlink, FalkorDB writes its snapshot to container-local storage, and **every graph
silently vanishes on `docker compose down && up`**. It survives `docker restart`, which is what makes
it so easy to miss, and so easy to ship.

```yaml
volumes:
  - falkordb-data:/var/lib/falkordb/data    # right
environment:
  REDIS_ARGS: "--appendonly yes --appendfsync everysec"
```

### 2. Creating edges by internal id is 73x faster

The obvious way to load edges is to match both endpoints on an indexed property. On 20,000 edges I
measured **3,021 edges/sec**. Resolving the business key to the internal node id once in application
memory, then matching on `id()`, gives **222,374 edges/sec**.

```cypher
-- 3k/sec
UNWIND $rows AS r MATCH (a:N {id: r.a}), (b:N {id: r.b}) CREATE (a)-[:L]->(b)

-- 222k/sec
UNWIND $rows AS r MATCH (a), (b) WHERE id(a) = r.a AND id(b) = r.b CREATE (a)-[:L]->(b)
```

`GRAPH.EXPLAIN` tells you why: `NodeByIdSeek` is a direct offset lookup, `Node By Index Scan` is a
B-tree probe per row.

And a trap inside the trap: **do not raise the batch size.** At 1,000 rows per batch I got 3,021
edges/sec; at 10,000 it collapsed to **378** — eight times *slower*. The planner builds a Cartesian
Product per row. "Optimising" by batching harder makes it worse.

### 3. Three limits are baked into the official image

`TIMEOUT 1000`, `RESULTSET_SIZE 10000`, `MAX_QUEUED_QUERIES 25`. All three bite. The second is the
nasty one, because it does not error — a query returning 20,000 rows comes back with exactly 10,000
and no warning. I lost twenty minutes to a node-id map that was silently half empty.

### 4. Vector indexes cannot filter by property

This is documented, but the consequence is worth spelling out. In a shared graph, a top-*k* vector
search returns rows from *every* tenant. Post-filtering to your own tenant means you asked for *k*
and kept *k/N*. So you choose between a measurable data leak and collapsed recall.

The fix is structural: mint a label. `(a:Alternative)` for everything, `(a:NamedOption)` for the
titled subset, and put the vector index on the narrower label. You get a genuinely pre-filtered ANN
index instead of a post-filtered one. For tenancy, the same logic says one graph per tenant — which
is FalkorDB's headline feature and, as it turns out, a correctness requirement rather than a
preference.

### 5. Betweenness is sampled, and unseeded it is not reproducible

`algo.betweenness` takes `samplingSize` (default 32) and `samplingSeed` (default 0, meaning
time-based). I published centrality numbers from unseeded runs before noticing. Pin the seed, and
say in your write-up that the result is an approximation.

### 6. Temporal support is partial

`date() + duration({days: 1})` works. `datetime() + duration({hours: 2})` does not. Neither does
`WHERE ts > datetime() - duration({days: 7})`. Store epoch milliseconds as integers and do integer
arithmetic. Also: `LIMIT` is **not** respected by `CREATE`, `SET`, `DELETE` or `MERGE` —
`UNWIND [1,2,3] AS v CREATE (:T {v: v}) RETURN 1 LIMIT 1` creates three nodes. Bound destructive
work with `WITH ... LIMIT n` *before* the clause.

### 7. Your graph is a projection, and the moment you *act* you have to go back to the source

This one cost me a wrong patch, caught before it shipped, and it is the lesson I would keep if I
could keep only one.

My agent does one thing rather than only answering: it drafts an OWNERS patch. The finding is an
inconsistency the project created itself — Kubernetes writes `emeritus_approvers` to record that
someone stepped back from an area, and three people are recorded that way across several files
while one *other* file still lists them as an active approver.

Easy enough. Find them in Cypher, remove the handle, write the diff. Three candidates, three
patches.

Two of those three patches would have been wrong, and the graph could not tell me so.

The first was the strongest signal in the entire corpus: one person recorded emeritus in **twenty**
files, still an approver in exactly one. Irresistible. That one file is
`vendor/k8s.io/utils/ptr/OWNERS` — and `vendor/` is vendored code, synced from another repository.
Patching it there would be reverted by the next sync. So the exclusion went into the query itself,
and the best-looking row in my results became a row I deliberately throw away.

The second is the real lesson. `approvers: [sig-cluster-lifecycle-leads]` is an **alias**, and my
ingest expands aliases into `APPROVES` edges — correctly, because that is who really holds
authority. So the graph says, truthfully, that this person approves `cluster-bootstrap`. But their
handle **does not appear in that file at all.** There is no edit to it that removes them. A patch
generated from the graph would have been a patch that changes nothing, submitted with total
confidence.

The graph is a *projection* of the source, flattened for traversal — and expansion is lossy in the
exact direction that matters when you stop reading and start writing. Querying wants the expanded
view. Editing wants the literal file. So the drafting layer loads the parsed corpus alongside the
graph and refuses any case where the handle is not literally named, reporting which alias put them
there instead.

If you are building an agent that acts rather than reports, that is the generalisation: **the
representation you query is not always the representation you may edit.** Find out which one your
write path is standing on before it writes anything.

The third guard is one only the graph could supply. If removing a handle empties the `approvers`
list, the file does not become unowned — it silently starts *inheriting* from an ancestor. A
one-line fix with a consequence two directories up. The draft names the ancestor that would take
over and how many approvers it has, which no amount of reading that one file could tell you.


---

### 8. `algo.WCC(NULL, NULL)` returns nothing, and does not tell you

`algo.pageRank(NULL, NULL)` is valid — the two arguments are node labels and relationship types.
So `algo.WCC(NULL, NULL)` looks valid too. It is not: on v4.22.1 it returns **zero rows and no
error**. `CALL algo.WCC()` is the working form.

I published a benchmark figure for WCC that was, it turned out, the cost of computing nothing. It
survived because a timing harness measures how long a call takes, not whether it did anything. If
you benchmark a graph algorithm, assert the *result* first — compare it against another engine, or
at minimum against a count you worked out by hand. The full story is in the networkx section below.


## "Why not just use networkx?" — I had this wrong

Someone asked me this and it is the right question. My graph is about 3,000 nodes. That fits in
memory trivially, and networkx is a very good library.

I answered it with a benchmark, published the table, and built an argument on it. Then, late in
the project, I noticed the table had **no script behind it** and described a graph of 3,300 nodes
and 39,987 edges — which is not my graph. Mine is **3,087 nodes and 15,735 edges**. So I wrote the
benchmark properly, against the real thing, and ran it three times.

| operation | networkx | FalkorDB v4.22.1 | I had claimed |
|---|---|---|---|
| build the graph *(not like-for-like)* | **8.1 ms** | 803 ms | networkx 9x |
| 2-hop neighbourhood (p50) | **0.004 ms** | 0.3 ms | networkx 22x |
| WCC | **2.1 ms** | 5.4 ms | networkx 1.6x |
| **betweenness (k=32)** — *the one a tool calls* | 25.8 ms | **16.7 ms** | **FalkorDB 18x** |
| PageRank — *no tool calls it* | 338 ms | **5.7 ms** | FalkorDB 153x |

**The betweenness row is the one that mattered, and it went from 18x to about 1.5x.** My argument
had been: 352 ms is an offline batch job, 19.8 ms is a tool an agent can call inside a
conversational turn, that is a difference in kind. On the real graph networkx does it in 26 ms.
Both are fine inside a turn. The argument is withdrawn.

The old numbers were not fabricated — they were measured on a graph 2.5x denser in edges, which is
exactly where a sparse-matrix engine's advantage lives. They were just not measurements of the
thing I was shipping, and I had stopped checking.

So here is the honest version, which costs me the punchiest paragraph I had written:

> On a graph this size, **speed is not why you need a graph database.** networkx is faster at
> everything except PageRank, which nothing in my product calls, and roughly ties on betweenness,
> which one tool does. If computing betweenness over 3,000 nodes were all this did, networkx plus
> a JSON file would be the right choice and I would be wrong.

What survives is not a speed claim at all:

- a **vector index composed with traversal in one query** — find a rejected idea by meaning, then
  walk to who rejected it and whether they still hold authority, without a round trip;
- **`GRAPH.COPY`** — mutate a whole-graph copy, re-run a recursive traversal over it, diff against
  the original and throw the copy away, inside one request;
- **memory in the same graph as the facts**, so one query starts in a remembered answer and ends
  in live nodes;
- durable persistence, physically isolated tenant graphs, concurrent access to shared live state,
  and a path object returned by the query that produced the answer.

Two things I learned writing the replacement benchmark, both of which would have quietly flattered
me:

**`CALL algo.WCC(NULL, NULL)` returns zero rows instead of erroring.** I had written it by analogy
with `algo.pageRank(NULL, NULL)`, which is valid. The WCC two-argument form is not, and it fails
silently — so my published "WCC 4.5 ms" was the cost of computing nothing at all. `CALL algo.WCC()`
is the working form. I only caught it because the new benchmark makes both engines agree on the
component count *before* it times either (lesson 8 above).

**networkx's PageRank needs scipy to be fast.** With scipy it takes a sparse path; without, it
falls back to pure Python and is far slower. My CI runner did not have scipy, and had I let that
slide, I would have published a much larger FalkorDB win on the one row where FalkorDB already
wins most — a number that would have been an artefact of my opponent's environment rather than of
either engine. The benchmark now refuses to run without scipy and says why. A comparison is only
worth publishing if the thing you are comparing against is running properly.

Which lets me ask the question I actually care about:

```cypher
CALL algo.betweenness({nodeLabels:['Person'], relationshipTypes:['CO_AUTHORED'],
                       samplingSeed: $seed}) YIELD node, score
WITH node AS p, score AS bridge
MATCH (p)-[:EMERITUS_OF]->(f:OwnersFile)
OPTIONAL MATCH (p)-[live:APPROVES]->()
WITH p, bridge, count(DISTINCT f) AS abandoned, count(live) AS live_roles
WHERE live_roles = 0 AND abandoned >= 3
RETURN p.key AS stepped_back_bridge, round(bridge*100)/100 AS betweenness, abandoned
ORDER BY bridge DESC
```

Twelve milliseconds. Not "who owned the most files" — *who was the structural bridge between groups
that otherwise did not talk*. The top result left 31 areas behind. Losing a bridge costs more than
losing a maintainer, and that distinction is a whole-graph property. No join and no embedding
produces it.

---

## The part I am least sure about

An empty traversal is not proof. It means this corpus does not record it.

I made that a product rule: every negative answer carries a statement of what was actually searched,
and the words "that is not proof it never happened." "No current approver" means no *recorded*
current approver — people own things informally all the time.

It is tempting to let a negative sound more certain than it is, because a confident "no" is a better
demo. But the whole value of asking a graph instead of a search engine is that the graph can
honestly say nothing is there, and that is only worth anything if the claim is bounded.

---

## What I would change

The co-authorship projection is derived data I write back into the graph. I compute it in Cypher
rather than in Python specifically so the database is doing the work — otherwise running an
algorithm over it would be partitioning a matrix the database never computed, which is decoration
wearing a graph costume. But it is still a materialised view I have to keep fresh, and FalkorDB has
no incremental way to do that.

I would also like **Louvain or Leiden**. FalkorDB has label propagation and that is the only
community detection available; it is non-deterministic and has no resolution parameter, which makes
"what does this organisation systematically refuse to do" harder to answer than it should be. The
6.0 release notes list both as "still in development", so this may age well.

---

*Built for Graph Hacks 2026 (WeMakeDevs × FalkorDB). Every number here comes from a benchmark in the
repo that you can re-run, and there is a `verify_claims.py` that re-checks each factual claim against
the live graph — I wrote it after catching myself quoting a stale figure.*
