# Kubernetes writes down who left. Nothing reads it.

*Building a company brain on a graph, and nine things FalkorDB taught me the hard way.*

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

**752 titled rejected options**, extracted deterministically from sub-headings — no LLM, because the
template produces them and a regex is reproducible where an extraction pass is not. Each one links
to the decision that recorded it, which links to the people who approved it, which links to whether
those people still approve anything.

The second latent node is stranger. KEPs cite each other through `replaces`, `superseded-by` and
`see-also`. I resolved all of them and **55 of 358 internal pointers (15.4%) go nowhere**. So I made
the *absent* record a node too.

(My first number here was **63 of 363, 17.4%**, and it was inflated. Two of those references point
at legacy flat-layout `.md` records that do exist, and one used `/kep/` where it meant `/keps/` —
a typo whose target is unambiguous. Resolving those honestly costs me eight broken pointers and
two percentage points. I am including the worse-for-me number because a statistic about decay that
is itself partly a parsing bug is exactly the kind of claim this post is about.) Now you can ask which missing documents are load-bearing:
`/keps/sig-api-machinery/0006-apply.md` does not exist, and **four separate decisions claim descent
from it.**

You cannot find that by searching. You find it by counting inbound edges to a gap.

---

## Ten things FalkorDB taught me the hard way

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

**What that choice costs, measured, because I only argued it at first.** Minting the narrow label
leaves 206 of my 958 nodes outside the index, and an unindexed node has probability zero of being
returned for *any* query — a structural hole, not a scoring miss. It is worth knowing the size of
the trade before defending it, so I built both and scored them: pooling all 958 into one index
moves retrieval on the named subset from **48.2 / 64.8 / 72.8%** to **45.8 / 61.8 / 69.8%** at
k=1/3/8, while taking the excluded 206 from **0/25 to 19/25** reachable. Three points of precision
against structural reachability. I kept the pre-filter, and the script that would have overturned
that decision is committed next to the one that justifies it.

Two things I had wrong on the way there. I described those 206 as "not embedded" — they are all
embedded, and re-embedding one reproduces its stored vector at cosine 1.0000, which also told me
the embedding is over the body and the title is display text only. And I had been counting their
substance by *title* length, which measures the extractor, not the corpus.

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


### 9. `EXISTS { ... }` is not a subquery here, and the error will not tell you that

I wanted "ownership files where nobody outside this cohort still approves", which in recent
openCypher is one clause:

```cypher
WHERE NOT EXISTS { MATCH (x:Person)-[:APPROVES]->(o) WHERE NOT x.key IN $hs }
```

On v4.22.1 that fails with:

```
Invalid input '(': expected ':', ',' or '}'
```

Read that error twice. It is not saying the subquery is unsupported — it is saying that **after
`{` it expected a map key**. The parser has no concept of an existential subquery, so it reads the
brace as a map literal and then trips on the first `(` of the pattern inside. You go looking for a
typo in a pattern that is perfectly well formed.

The working version is an `OPTIONAL MATCH` and a count:

```cypher
OPTIONAL MATCH (x:Person)-[:APPROVES]->(o) WHERE NOT x.key IN $hs
WITH o, leaving, count(DISTINCT x) AS others
WHERE others = 0
```

The general lesson is about error messages rather than about this one clause: when a graph
database's parser does not know a construct, it very often reports the failure in terms of the
construct it *did* think you were writing. "Expected a map key" meant "I have never heard of
`EXISTS {`". Checking the version's own documentation for the clause is faster than believing the
error.

### 10. Creating *and dropping* a vector index are both asynchronous

`CREATE VECTOR INDEX` returns before the index exists. HNSW builds in the background, and
`CALL db.indexes()` reports a `numDocuments` that climbs toward the real count — so a benchmark
that creates an index and immediately queries it is scoring whatever happened to land. Poll until
`numDocuments` reaches what you expect, and refuse to report if it never does.

`DROP VECTOR INDEX` has the same property and it is easier to get bitten by, because the failure
looks like the opposite of what it is. I had a script that created a temporary index, measured,
dropped it, then re-read the index list to prove it had cleaned up after itself — and it reported
that it had *dirtied* the graph it measured. It had not; the drop had simply not landed yet one
line later. A cleanup check that races the cleanup cries wolf about state, which is worse than no
check: the first thing I did was go looking for a leak that did not exist.

One more trap in reading that index list. I filtered it by matching `"VECTOR"` against the whole
printed row, which reports a label as still having a vector index when all it has is a `RANGE`
index on some other property. Read the per-field types, not the row.

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

Twelve milliseconds, median of five runs. Not "who owned the most files" — *who was the structural
bridge between groups that otherwise did not talk*, among people who now hold no approval authority
anywhere. Top result on this corpus: `logicalhan`, betweenness 156.5, five areas left behind.

Losing a bridge costs more than losing a maintainer, and that distinction is a whole-graph
property — not a traversal, not a join, not anything an embedding expresses. A graph *library* can
compute it; I measured that above and it is no slower. What a library cannot do is **compose the
score with the ownership traversal in the same query**, which is the whole of what that Cypher
does: rank by centrality, then walk from each person to the areas they left, against live data,
in one statement.

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

## The checks lied to me more often than the code did

I ended up writing a lot of verification — a script that re-queries the README's thirty-six graph
claims against the live database, another that drives every rendered answer state through a
headless browser, another that reads the demo script's narration and asserts the app actually
returns what it claims.
Thirty-three CI steps. The thing nobody warns you about is that **the checks fail in their own
ways**, and a check that fails for the wrong reason costs more than the bug it was meant to catch.

The sharpest example came from measuring memory. `INFO memory`'s `used_memory` is *instance-wide*,
so once you have deleted rows the allocator hands their space to the next insert and a growth
delta understates by whatever it reuses. Run the same benchmark twice and the second run reports
the first block at **-0.1 KB per answer** — memory apparently falling while two hundred rows are
added. That is not evidence against the figure; it is an instrument that has gone blind in that
instance, and reporting it as a failure would be a lie about which thing is broken. The benchmark
says so now, and names what to restart.

The same measurement taught me something duller and more expensive. I had published **about 12 KB
per stored answer**, reproducing at 11.9, 11.6 and 12.2 across three runs — real runs, and all
three started from an *empty* memory, where the first two hundred answers also pay around 1.7 MB
of one-time vector-index structure. Block by block it is 12.2 then 3.6. A first-batch average
multiplied by ten thousand is not a projection, and mine overstated the ceiling by about 3x. The
number was reproducible and wrong, which is the combination to watch for.

Four that cost me the most:

**A probe with a fixed question, against a store that persists.** A test asked a question, recorded
the answer, then asserted the next ask came back remembered. It passed, and failed on the second
run ever — because the first ask was already remembered from the previous run. The feature working,
reported as a failure. Anything that writes to a durable store needs a unique key per run. I fixed
this in one file and hit it again two files later, which is its own lesson.

**An assertion that was correct until I fixed a bug.** A concurrency check counted only
`ANSWERED_WITH_PATH` as success. The moment I fixed memory to record button clicks as well as typed
questions, repeats started coming back `ANSWERED_FROM_MEMORY`, and the check reported "0 answered"
out of six requests that had all succeeded. That is indistinguishable from a concurrency collapse,
and it took an hour to tell apart. Fixing a bug can invalidate a test without touching it.

**A timing harness that never looked at its result.** I published `WCC 4.5ms` in a benchmark.
`CALL algo.WCC(NULL, NULL)` returns zero rows and no error on v4.22.1 — I had written it by analogy
with `algo.pageRank(NULL, NULL)`, which is valid. The figure was the cost of computing nothing. I
only caught it because the replacement benchmark makes two engines agree on the answer *before* it
times either. If you benchmark a graph algorithm, assert the result first; comparing against a
second implementation is the cheapest way to do it.

There are six more in the repo's `GROUND-TRUTH.md`, including ffmpeg silently dropping any caption
line containing a `%`, and headless Chrome instances sharing a profile directory and handing back
screenshots of a page that never ran. None of them are about graphs.

---

**A parser that lost any element containing another element.** The check that drives every
rendered answer state through a headless browser tracks a handful of element ids and counts
nesting depth to know when each one closes. It incremented the depth of only the innermost open
element — so whenever one tracked element contained another, the outer one was left permanently
one level deep and never recorded at all. Two of them did: the panel holding the reasoning path,
and the one holding the headline number.

The function asking "is this visible?" received nothing and answered *no*. So a feature that was
rendering perfectly was reported as broken, and I spent an hour reading application code that had
nothing wrong with it before opening the page in a real browser and seeing the panel sitting
there.

That is the worst shape a bad check can take. A check that fails loudly costs you minutes. A check
that fails *as though it were a finding about your product* sends you to the wrong file with
confidence. Two rules came out of it, and they are cheap: an element the parser could not find is
reported as **a parse failure in the checker**, never as "not visible" — and anything that counts
nesting must exclude void elements, because no closing tag is coming for them.


**One sentence, wrong three times, each time in my own favour.** The summary box at the top of my
README said "every benchmark re-run on each push". Two of them run in CI; the multi-tenancy one
builds a thousand graphs and does not — and I had written that fact down an hour earlier while
leaving the summary claiming otherwise. I corrected it to "two of the three", and the check I
wrote in the same commit caught *that* as wrong too: there were five benchmark scripts then, counting
the ingest-rate ones whose numbers appear in this post. Then the check failed on a pair of numbers
that agreed, because its word map stopped at four.

The claim, the fix, and the check on the fix. Two of the three were wrong in the direction that
sounds more rigorous, and none of them was a lie — each was a sentence I believed when I wrote it.
That is the failure mode worth designing against, because sincerity is not a defence and
re-reading your own work does not catch it. Only making the thing fail does.


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

*Built for Graph Hacks 2026 (WeMakeDevs × FalkorDB). Every figure in this post has something
behind it in the repository, and they are not all the same thing: the graph counts are re-queried
against the live database on every push, this post's own numbers are re-checked by `verify_blog.py`,
and the ingest and benchmark timings come from committed scripts you can re-run — reported with
their conditions rather than gated, because the same code gives betweenness 2x on a laptop and 6x
on a CI runner.*

*This footer used to say "every number here comes from a benchmark" and that a script "re-checks
each factual claim". Neither was quite true — the corpus counts come from the graph, not a
benchmark, and the script checks thirty-six claims rather than all of them. I found it by grepping
my own writing for sentences that assert verification, which is a thing I recommend, and which is
how the sentence two paragraphs above this one got fixed as well.*
