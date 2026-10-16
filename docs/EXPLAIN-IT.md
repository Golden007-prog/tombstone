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
| `MissingRecord` | 47 | a record cited by name that does not exist |
| `Sig` | 22 | a special-interest group |

The edges that matter: `APPROVES` (2,584) is current authority, `EMERITUS_OF` (298) is authority
that was given up, `INHERITS_FROM` (584) is the ownership chain the depth-4 traversal walks,
`CONSIDERED` (958) joins a decision to what it rejected, and `CO_AUTHORED` (5,879) is the
collaboration graph the whole-graph algorithms run over.

**The decision to be ready to defend:** why 752 `NamedOption` out of 958 `Alternative`. Only 752 of
the extracted options are genuinely a *nameable* alternative — but be careful how you say what
the other 206 are, because I got it wrong on the page first. Only about 22 are artefacts: 19 list
markers, a few fragments. **163 are 60+ characters of real text describing a rejection that
happened**, whose extracted title came out as a sentence because the KEP wrote it as a paragraph
rather than a sub-heading. They are nodes in the graph and the lineage queries see them; they are
not embedded, so `has_this_been_tried` cannot reach them. If asked what this product's biggest
recall weakness is, that is the honest answer: up to 163 rejections out of 958 are not findable by
the tool whose whole job is finding them.

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
Against a text baseline over the same documents the graph scores **24 of 25 versus 9 of 25**,
across seven categories. The number to lead with is not that one: it is that on the *control*
category — lookups where the answer sits in one document — the text index **ties it, 9 to 9**.
That tie is what makes the other fifteen mean anything, and the graph loses the title lookup
outright. Volunteer both before anyone finds them.

## "How do you know any of this is true?"

One command: `./preflight.sh` — twenty-one checks. The graph counts are re-derived against the
live database; the benchmark ratios are reported with their conditions rather than gated.
31 CI steps on every push. 124 tests. Each answer in the UI carries its Cypher, that query's hash,
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
   through rather than deleted. PageRank held up at 54–145x.
5. **Three of fourteen questions draw a reasoning path**, not all of them — there is no path to
   draw for "which areas have exactly one approver", and inventing a picture for a list would be
   decoration.

The reason to lead with these: every one of them is already written down in the repository, so a
judge who finds them finds them *already disclosed*. That is a much better position than having
them discovered.
