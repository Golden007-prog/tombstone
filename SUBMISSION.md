# Submission — ready to paste

**How to use this file.** Everything down to the pre-submit checklist is copy for the form, and
each section is the answer to one field. Two places carry reasoning *for you* rather than text to
paste, and both say so where they start: the second-track decision under **Track**, and the
checklist at the end. If you are filling the form at speed, the rule is simple — paste what is in
a section, skip what is in italics under one.

Everything the WeMakeDevs panel asks for, written out so none of it is composed at 11pm on the
18th. Rule 10's six required items are mapped in the README; this is the copy.

**Deadline: 11:59 PM IST, Sunday 18 October 2026.** Aim to submit by 18:00 IST — panels get slow.

---

## Title

Tombstone

## One line

The decisions your org already made and forgot. Asked as a graph.

## If the form caps the description

*Nobody can see the form's fields until you are registered, and the Description below is 3872 characters. These are the same pitch at two shorter lengths so a character limit is a paste, not a rewrite at 11pm.*

**~273 characters:**

> Tombstone turns Kubernetes' own governance record into a graph and answers what no document states: one person is the entire review capacity for the apiserver's metrics endpoints. It drafts two real OWNERS patches for what it finds, and refuses the one it cannot justify.

**~1085 characters:**

> Large engineering orgs re-propose things they already rejected, because a rejected option is not a document — it is a subsection buried in a proposal about something else, with no identity, no index entry and no owner. Tombstone makes it a first-class node on FalkorDB, attaches the person who killed it, and answers questions that are traversals rather than lookups: has this been tried, who really owns this, whose stepping back cost the most connective authority, what breaks if one more person leaves.
>
> It runs on Kubernetes' real governance record — 681 decisions, 958 rejected alternatives, 794 people, 585 ownership files. Nothing synthetic. The headline finding is written down nowhere: it is only true as a consequence of the structure.
>
> It acts, then stops: it drafts two real OWNERS patches and refuses the third, because that approval arrives through an alias. Nothing here is asserted — 190 tests, 36 graph claims re-queried against the live database on every push. I measured the premise above and could not confirm it on this corpus, and say so rather than lead with it.

## Track

> **Track 03 — Company Brain.**

That line is the whole answer; everything below it is for your decision, not for the form.

---

*Second track, if entering more than one.* The field as of 16 Oct, from public repositories
rather than from a gallery — there is none. **253 repositories created since 14 Oct mention
FalkorDB and 134 are Track 3 entries**, counted by `scripts_survey_field.py` rather than by hand
and re-run on 17 Oct;
the three below were read closely, and the census of the twenty largest is further down:

| entry | what it is | tracks |
|---|---|---|
| `Sumit99589/orion` | forks the company graph into a "parallel universe" before a change, live on Vercel, MCP server, per-person memory graphs | all three |
| `Vaibhaav-Tiwari/lineage` | truth maintenance: when a decision reverses, the answers and beliefs built on it are struck through and actions blocked. 745 PEPs plus forum threads and commits since 2015 | two |
| `StarKnightt/threadline` | 3D replay of every traversal, a verifier agent that path-checks each citation, 60-question eval | all three |
| `kh-bikash/cairn` | **the closest competitor.** Live, no sign-up. Two workspaces on two FalkorDB graphs: 13 real FalkorDB-org repositories, and a fictional 24-person company in real Slack/Jira/ADR export formats. Betweenness and label propagation, drift detection, rejected alternatives with verbatim quotes, MCP, and a **four-system eval** — graph agent, graph-with-no-AI, dense vector RAG, keyword RAG — graded twice, automatically and by a second model | two |
| `Prashant-thakur77/Faultline` **(now 404 — read 16 Oct while live, unverifiable since)** | "no path, no claim": the model suggests, a read-only query decides. Live demo, hosted MCP with a public read-only key, a GitHub Pages replay that needs no backend, a v1.0.0 release, **a narrated 4:24 video already published**, and a real pull request merged after two-step approval | T1 primary, T3 secondary |
| `srinjoy356/keystone` | public codebase history as a graph; every answer shows its subgraph and exact Cypher, and each quoted decision is checked against its source text by code. FalkorDB Cloud + Vercel, and a real issue opened after human approval | all three |

**Three of the four serious Track 3 builds use invented data; one does not, and it is the one to
take seriously.** orion's demo company, Corvane, is explicitly synthetic; dealership-brain's is a
fictional dealership; `RISHIK92/company-brain` generates its world from its own `world.build`
module and calls itself a practice build. That third one volunteers the cost in its own README:
because its synthetic text is not paraphrased, it *"flatters the pattern extractor and lexical
baselines alike"* — which is the trap exactly, since writing both the documents and the questions
means part of any graph-versus-text gap is a gap you authored.

`Vaibhaav-Tiwari/lineage` made the same choice this did, on Python instead of Kubernetes: 745
PEPs, 310 discuss.python.org threads and 5,708 posts, the devguide Experts Index, cpython history
since 2015. **27,959 nodes and 67,601 relationships to this graph's 3,087 and 15,735, and 185
tests to 190.** It is bigger and better-tested, it is honest about its own limits, and it is not
deployed either — its README says the demo and video come before submission. Do not tell anyone
this is the only entry using real data. It is not — and there is now a number for that rather
than a caution: **4 of the 20 largest Track 3 entries name a specific real public corpus** in
their README (`cairn`, `lineage`, this one, `decision-brain`), and three of those four are also on
Kubernetes. Real data is the rarer choice, which is worth saying plainly, but it is not
this entry's private territory, and claiming otherwise to a judge who has read `cairn` would be
the expensive kind of wrong.

That figure is what a README *claims*, not what its code does, and the first instrument that
produced it was wrong in both directions: it matched `apache`, which is the licence on half the
field, and `acme`, which usually appears inside a sentence *refusing* to invent an Acme Corp —
including this repository's own README, which the first run therefore filed as synthetic. A
pattern keyed on a word instead of a meaning, for the third time in two days.

Why this corpus was the right choice is narrower than "nobody else has it", and the two are worth
separating. Kubernetes publishes `emeritus_approvers`: an explicit, maintained record of who
stepped back, which is what every finding here is built on. lineage discloses the opposite in its
own weaknesses — *"Listed owners are known only for today"* — so it has the decisions and the
people without the attrition. That is the gap this corpus was chosen for, and that part still
holds.

**An earlier version of this page said "no other entry found is using this corpus." That is no
longer true, and the entry that falsifies it is the closest competitor in the field.**
`BalajiReddy1/understudy`, pushed the morning of 16 Oct, describes itself as modelling
"Kubernetes as a company in FalkorDB" and checking "who could actually step in if someone left" —
this project's thesis in one sentence. It is not a surface resemblance. Its tree carries
`ingest/owners.py`, `ingest/keps.py` and `derive/departures.py`, and that last file's own
docstring reads *"Departures: approvers who left, read from OWNERS history… a handle newly appears
in `emeritus_approvers` in an OWNERS file."* Same field, same files. On one axis it goes further
than this does: it diffs OWNERS across git history to date each departure and record the person's
last activity before it, so it knows *when* the project lost someone. This reads current state and
does not. It also carries nineteen test modules, an MCP server, an agent loop with memory and
trace, a fixes engine and a networkx cross-check.

So, honestly, what is left: the corpus is shared, the attrition signal is shared, and what differs
is what gets done with them. **An earlier version of this paragraph said understudy had "no web
surface, no rendered figures and no reachable demo". That was true of the tree I read on the
morning of 16 Oct and false by that afternoon** — they pushed a forty-file React frontend at
16:37 (`frontend/src/App.tsx`, five components, `api.ts`, its own unit tests). Writing a
competitor's absence into a submission is a claim with a shelf life measured in hours, and this
one expired in six. It is corrected here rather than quietly deleted, because the correction is
the more useful fact: **two entries now do this on the same corpus, and the gap is narrower than
one morning's reading suggested.**

What this still has that I could not find in theirs: an answer surface where every reply carries
its Cypher, that query's hash and the arguments it was answered with; a drawn path a judge can
read without running anything; a graph-versus-text evaluation over the same documents, honest
about handing the graph arm its tool (24/25
against 9/25 for TF-IDF and 10/25 for dense retrieval); 36 claims re-derived against the live
database on every push; and the engine-level work in Honest limits, where the directedness of
`algo.betweenness` is derived from the vendor's own worked example because they do not document
it. **What understudy has that this does not: a pre-registered backtest that asks whether its own
central number predicts anything, and reports a null.** That is a better scientific instinct than
any feature on this page, and the honest thing to say about it is that I did not do it.

"Only entry on this corpus" is not a claim to defend any more — and finding that out from a
stranger's repository two days before the deadline is a great deal cheaper than having a judge
find it.

The others each chose their own: threadline reads the FalkorDB org's GitHub history, orion a
synthetic company of people, teams, systems and customers, lineage the Python PEPs and the forum
threads behind them. `cairn` and `bibek198/decision-brain` also name Kubernetes in their READMEs.
(Searches are evidence of absence only to the extent GitHub's index is complete, and entries can
be private until they are submitted — which is precisely how this claim came to be wrong.)

Two more Track 3 entries have appeared since: `volfiros/axon-brain`, which stores access rules in
the graph and filters every query before anything reaches the model, and `rossycoder/dealership-brain`,
whose README separates what is real from what is stubbed and whose dataset is a fictional dealership.

Read their READMEs rather than run them, so the feature claims are what they claim, not what they
do — but the deployments I did check, by request rather than by reading.

**That hand-made list of eight was wrong by an order of magnitude, and it is worth saying how.**
Re-counted with [`scripts_survey_field.py`](scripts_survey_field.py), re-run on 16 Oct as this
was being written, and again on the evening of 17 Oct: **253 repositories created since 14 Oct
mention FalkorDB, and 134 of them are Track 3 / company-brain entries.** Successive runs of the
same script gave 123/85, then 141/99, then 175/113, then this — the field grew by twenty-one
Track 3 entries between two runs a day apart, and by twenty-eight in the day before that. That is the best argument there is for
re-running the script rather than quoting it, and the reason every figure here carries its date. Not eight. `RISHIK92/company-brain`, which the earlier sweep called substantial, now
returns 404 — gone or made private — so one of the eight cannot even be checked any more.

Of the **20 largest, 11 serve a reachable demo**, and **this is one of them** — re-run on the
evening of 17 Oct, after deploying. This repository is **9th of 134 by size**. Both figures moved
between two runs on the same day, which is the argument for the script over the quote. An
earlier version of this line said it was *not* one of them, which was true when written and
stopped being true the moment the Render deploy went up. An earlier version of this line listed `Faultline` among them — it was read when
it was live, but `Prashant-thakur77/Faultline` now returns 404, and it never came out of the
script's own three queries, so a hand-read entry was being presented as scripted output. Both
faults are the same fault: a list the page invites you to reproduce has to be the list the script
actually prints.

The count has two deliberate cautions, because getting it wrong once was enough. It looks for a
demo in the README as well as the `homepage` field — three of the fifteen largest link one only
in their README, so counting `homepage` alone undercounts and reporting that as the deployment
rate would be exactly the sort of flattering error this page keeps catching. And it reports a
census of the twenty largest rather than a rate over all 134, because a rate over repositories you
have actually opened is honest and one extrapolated from a sample is not. Two of those also
time out under Python's default headers and answer 200 to `curl`; reporting a live competitor as
dead would have been the convenient mistake.

**A sharper reading of the same census.** Across all 134 the deployment rate is low, but that
average flattens the part that matters. The three entries read closely here — `cairn`, `Faultline` (since 404),
`keystone` — are **all three deployed**, all three enter more than one track, and one of them has
its narrated video already published and a v1.0.0 release tagged. At the top of this field a live
link is not a differentiator, it is the entry fee; the differentiator is further in. So the
instruction that follows from the census is not "relax, most of them have no demo" — it is "the
ones you will actually be compared against all have one."

**One conclusion from the old passage was backwards and is withdrawn.** It said a live demo "is
now the one thing the rest of the field has and this does not". Nine of the twenty largest
entries have no reachable demo either. Deploying is still clearly worth doing — the FAQ prefers a
hosted demo, and at the serious end of the field roughly a third have one — but it moves this
into a minority rather than up to par with everyone. The reason to do it is that judges click
links, not that the field is ahead.

Two things follow that are worth acting on. **Multi-track entry is normal here**, so entering one
track is a choice and should be a reasoned one. And the live demo *was* the clearest gap in this
submission — not because the field is ahead, which the census above shows it is not, but because a
judge with 134 entries to get through clicks links, and eleven of the twenty largest give them one.
**That gap closed on 17 Oct**: <https://tombstone-vvn9.onrender.com>, and this document says so
sixty lines above. It is left in rather than deleted because the reasoning is what decided the
work, and because what a deployment does *not* settle still holds: orion's demo company is
explicitly synthetic, dealership-brain's is a fictional dealership. Being deployed and being
checkable are different claims, and this entry now has both rather than only the second.*

*Reasoning.* **There are three tracks and this analysis only ever examined one of them**, which
is a gap worth naming before the conclusions: Track 01 is *Agents That Act on Connected Data*,
Track 02 is *Agent Memory and Coordination*, Track 03 is *Company Brain*. The paragraph below
weighed 02 carefully and declined it, and never enumerated 01 at all — rigorous-looking and
incomplete, which is the same shape as the competitor count that was off by an order of
magnitude. Both are declined, and here is each on its own evidence.

**Track 01 (Agents That Act) is the closer fit of the two, and still declined.** The action here
is real and committed: a finding becomes two reviewable OWNERS patches, one candidate is refused
with its reason (that person's handle is not in the file at all and only reaches it through an
alias), the strongest-looking case never becomes a candidate because it is vendored and excluded
in the Cypher, and both drafts sit in `docs/patches/` so a judge
can read them without running anything. The README leads on it. But the entries leading that
track *execute*: `Faultline` merged a real pull request on its own demo-infra repository after a
two-step approval and verified it APPLIED — that repository has since gone 404, so take it as read
while live and no longer checkable; `keystone` opened a real issue on a sandbox repo, and that one
still stands. This
drafts a patch and deliberately stops, which is the right product decision and the weaker
submission on an "acts" axis. Entering 01 would invite exactly the comparison the paragraph below
refuses for 02, against an entry that also already has its narrated video released.

*Track 02 (Agent Memory)
is arguable but not yet earned. Answers persist as `(:Answer)` nodes that `CITED` the real records they came from, and a
later session gets `ANSWERED_FROM_MEMORY` only when those citations still resolve — so memory
invalidates itself when the graph moves underneath it. What Track 02 also asks for is agents that
**share state with each other**, and there is one agent here, not several. Orion runs a shared
task board with atomic claims and heartbeat release; Lineage runs a Historian and a Steward that
act on each other's output. Against entries that meet that brief fully, entering on a half-met one
is worse than not entering: it invites the comparison on the axis where this is weakest, and costs
attention on the axis where it is strongest. Decide deliberately; do not drift into it.

## Description

Large engineering orgs keep re-proposing things they already rejected, because the rejection was
never a thing you could look up. The rejected option is not a document — it is a 200-word
subsection buried inside a 4,000-word proposal about something else. It has no identity, so you
cannot count how often an idea was refused, you cannot ask who refused it, and you cannot find out
whether anyone who knows why is still around.

I tried to measure that premise on this corpus and **could not confirm it**. The measurement is in
the README, next to the weaker claim that *is* demonstrated: a rejected option is not retrievable
at all today, so the question cannot be asked by anyone. Leading with a premise I could not prove
would have been the easier pitch, and this project is about not doing that.

Tombstone makes the rejected alternative a first-class node, attaches the person who killed it,
and answers questions that are each a traversal rather than a lookup: has this been tried, who
owns this really, whose stepping back cost the most connective authority, which group is hollowing
out, and what breaks if one more person steps back.

It runs on **Kubernetes' own governance record** — a real organisation of thousands of people that
publishes its decision history, its ownership map and its own attrition. 681 decisions, 958
rejected alternatives, 794 people, 585 ownership files. Nothing synthetic.

And it does not only answer. It **acts** — and then stops. Nothing is applied, nothing is sent
anywhere, and every draft is addressed to a human with both readings of the evidence on its face;
there is a test that walks the AST and fails if the drafting path imports a network module. It
finds places where the project's own record contradicts itself — someone recorded as having stepped back from several areas while one other
file still lists them as an active approver — and drafts the OWNERS patch that fixes it. The part
worth looking at is what it does not draft: the strongest-looking candidate never becomes a candidate at all, because that file is
vendored from another repository and the exclusion lives in the Cypher; the one it does
refuse is refused because the person's handle is not in the file at all — an alias expands
to them, so no edit to that file would remove them.

Nothing here is asserted. **37 CI steps on every push** re-check it: 190 tests, 36 graph claims
re-queried against the live database, 18 rendered UI states checked for panels that render empty,
the drafting action's own output, the memory claims, two of the seven benchmarks re-run — the
other five build a thousand graphs, millions of edges, a memory curve or a second vector index, so they are dated measurements with
committed scripts rather than gates, and the README says which is which — and a job that runs
the quickstart on a machine that already has a `falkordb` container — the case that used to break
it. The graph is scored against two baselines over the same documents, with the graph arm given
the tool and its arguments while the baselines get only the question, so it is answering power
with routing factored out — **24/25, against 9/25 for
TF-IDF and 10/25 for dense retrieval with the product's own embedding model** — in
seven categories — and on the control category, lookups where the answer sits in one document, the
text index *ties it nine to nine*, across ten of the twenty-five questions. That tie is why the other fifteen mean anything.

Several claims did not survive that process and are **marked in the README rather than deleted**:
a benchmark that said FalkorDB computed betweenness 18x faster than networkx (on the real graph it
is roughly a tie), a multi-tenancy latency curve that did not reproduce on a second run, and the
project's own opening premise. A page that documents what it got wrong is worth more than one that
never checked.

## Against the organisers' own published principles

No *scored* criteria are published. Two things come close, and the README maps this build against
both. The first is the track's own five "Key focus" bullets — four are answered with exact numbers
(681 of 681 decision records carry their source URL; 83 people are emeritus somewhere while holding
no current approval anywhere), and the fifth asks for "docs, tickets, and chats" where this has
docs only, which the README says plainly along with why a fabricated Acme Corp would be worse. The
second is an article WeMakeDevs published, *How to build an agent that reasons over a graph*, whose
principles the README maps one by one to where each piece lives here — the fixed tool
catalogue, names resolved before any query runs, the four answer shapes (named the same way),
"not in the graph" kept distinct from "nothing breaks", the path returned with the answer rather
than an explanation written afterwards, memory as nodes with a date, a demo that asks the same question at two depths — and, where the article
asks for tenant isolation, an honest **partly**: the app is single-tenant, so what is shown is that the mechanism works rather than that this uses it.

Worth saying in the submission because it was not designed to match: I found the article in the
Resources page after building this.

## Team

> Solo.

## Built with

> FalkorDB v4.22.1 (pinned — not `:latest`), Python, FastAPI, fastembed with BAAI/bge-small-en-v1.5
> running locally at ~5ms a query with no API key and no cost, Docker, and hand-written SVG for the
> reasoning path — no graph-drawing library. Graph features used: variable-length traversal over
> the OWNERS inheritance tree, `algo.betweenness` (seeded), `algo.labelPropagation`, `GRAPH.COPY`
> for counterfactuals, and a vector index composed with traversal in a single query.

## Hardest problem / what went wrong

*A form usually asks this. The honest answer is the strongest thing here, so it is written out
rather than improvised.*

> The hardest part was not building it, it was finding out which of my own claims were false.
>
> Four did not survive being checked. I claimed FalkorDB computed betweenness 18x faster than
> networkx; re-measured on this product's actual graph rather than the larger synthetic one the
> old table described, it is roughly a tie, and the argument built on it is withdrawn. I claimed
> 88 of 111 departed owners held no current role; expanding `OWNERS_ALIASES` properly made it 83,
> because group aliases had been counted as people. I claimed the agent remembered what it
> learned, which was true on the path a model routes and silently false on the keyless path that
> the hosted demo actually uses — a method that does not exist, called inside a bare `except
> Exception: pass`, so every question recorded nothing. And the premise in my own first sentence,
> that organisations re-propose what they already rejected, I could not demonstrate on this
> corpus at all.
>
> Later the same discipline found a different class of defect, and this one was in the demo. An
> answer's prose and the diagram beside it are built by two different queries, and they filtered
> rejected options differently — so on the very file the demo script opens with, the sentence
> named two rejections and the picture drew neither, one of them the alternative the narration
> reads aloud. That beat's whole claim is that the picture *is* the path the answer came from.
> The same shape turned up twice more: the honest negative reported "958 rejected alternatives
> indexed" to someone whose question had been compared against 752 of them, overstating its own
> haystack by 27% in the one sentence whose entire job is to say what was searched; and the same
> question asked two ways returned 5 rows and 15 while showing one identical query and one
> identical hash, because a chip narrows a threshold and free text does not.
>
> None of the three was findable by reading either path. All three came from one method — take
> two code paths that answer the same question and make them disagree out loud — and the two
> remaining pairs I pointed it at came back clean, which is the result I would have been least
> able to guess.
>
> What I changed as a result is the part I would defend: every number on the page is now
> re-derived from the live database by a script that runs on each push, the withdrawn claims are
> struck through rather than deleted, and the eval has a control category that exists so the text
> baseline can win — which it does, nine-all. A page that records what it got wrong is worth more
> than one that never looked.

## What I would do next

> Three things, in the order they would matter. **Reach the last 46 rejections that no index
> can find by name.** On 17 Oct the 206 that the vector index excludes got a full-text index on `.body` under
> their own label, which reaches **160 of them by name** — a word containing `-` `.` `_` or `/`,
> the engine's own tokeniser rule rather than a list of interesting words. `bench_index_scope.py`
> measures why *widening the vector index* was the wrong move instead: pooling them in costs about
> three points of named-option retrieval at every k, and keeping the two scopes disjoint avoids
> that while letting each answer say which index found each row. The residual 46 carry no
> splittable name for a keyword index to match, so the fix for those is a better extractor that
> gives them titles, not a third index. **Earn the tenancy claim**: the mechanism is measured to 1,000 graphs
> but this app is single-tenant and never switches graphs, so what is demonstrated is that it
> works, not that this uses it. **Ingest something that is not a document** — the rules rightly
> forbid private tickets and chats, and a fabricated company proves nothing, so this is docs only
> until there is a public corpus with real tickets attached to real decisions.

## Links

| | |
|---|---|
| Repository | https://github.com/aviralgarg05/tombstone |
| Live demo | <https://tombstone-vvn9.onrender.com> — Render free: sleeps after 15 min idle, first click ~1 min. Hugging Face refused a Docker Space on a free account (HTTP 402; they require PRO). |
| Demo video | *(fill in — narrated cut per `docs/DEMO-SCRIPT.md`)* |
| Fallback video | [docs/video/walkthrough-silent.mp4](docs/video/walkthrough-silent.mp4) — 86s, captioned, in-repo, 771 KB. It **downloads**; GitHub does not play repo-committed video in the browser. For a judge who runs nothing and clicks nothing, the depth-contrast GIF in the README renders inline and carries the core finding |
| Blog post | *(fill in if published — side prize is for the best post)* |

## How FalkorDB is used (Rule: it must support a central part of the product)

- Every answer is a hand-written parameterised Cypher query. The model picks a tool name and fills
  arguments; **no model output is ever concatenated into Cypher.**
- Ownership resolution is a variable-length traversal over an `INHERITS_FROM` tree — Kubernetes
  OWNERS files inherit, so "who owns this" means walking up until live approvers appear.
- `algo.betweenness` (seeded, so it reproduces) ranks whose stepping back cost the most connective
  authority. A whole-graph property no join or embedding can produce.
- `algo.labelPropagation` discovers contributor communities from co-authorship that are declared
  nowhere, then ranks them by attrition.
- `GRAPH.COPY` evaluates counterfactuals: copy the graph, delete a cohort's approvals in the copy,
  re-run the recursive traversal, diff, drop the copy. The live graph is never touched.
- A vector index seeds "has this been tried?" by meaning, and the graph supplies what no embedding
  holds: which decision recorded it, who decided, and whether they still hold authority.
- Memory lives in the same graph, so one query can start in memory and end in facts.

Turn the database off and the product stops, loudly. There is no in-memory mirror and no cached
fallback anywhere in the repo, and a test asserts it.

## Setup (for the "complete local setup instructions" requirement)

```bash
git clone https://github.com/aviralgarg05/tombstone tombstone && cd tombstone
./run.sh          # builds .venv if needed, starts FalkorDB, seeds, serves
```

Then open <http://localhost:8099>. **No API key and no account.** The buttons call the tools
directly, and typed questions work too — routed locally by embedding similarity over the fixed
catalogue, which refuses rather than guess. Verified from a clean clone in an empty directory.

## AI assistance disclosure (Rule 11)

See the AI assistance disclosure section of the README.

## Being able to explain it (Rules 12 and 13)

`docs/EXPLAIN-IT.md` — read this before any judging call. It is the questions most likely to be
asked, with the answer short enough to hold in your head: why a graph at all, the data model and
the one decision inside it worth defending (752 options in the vector index out of 958 extracted,
why the other 206 are not, and how a second index over exactly those 206 now reaches 160 of
them), what each of the thirteen tools asks, which
FalkorDB feature earns its place in which tool, what the model is allowed to do, and the five
weakest things — stated first, because every one of them is already written down in the repository.

It also answers the three a FalkorDB engineer is likeliest to ask, which were missing until I went
looking for them specifically: **why the vector index rather than their full-text index** (both
were spiked, and **both now ship**: the ANN index over the 752 named options, a full-text index
over exactly the 206 it excludes, and each answer reports which one found each row), **why a graph database for 3,087 nodes at all** — where the wrong answer is scale, and
this page's own withdrawn networkx benchmark is the evidence against it — and **what the write
path does under concurrency**, which is the one hard edge here and is measured rather than
argued: six simultaneous `GRAPH.COPY` requests give five answered and one degraded honestly.

---

## Pre-submit checklist

**Do this one first, today, before anything else:**

- [ ] **Register on wemakedevs.org now.** Not on Sunday. The FAQ says *"Your team and your
      submission are managed from the same panel"* — so **the submission form is behind
      registration**, and neither the event page nor the rules publishes its fields. Nobody can
      tell you what it will ask for. Registering now turns that from a deadline-night surprise
      into something you can see, screenshot, and fill in at leisure. It also surfaces anything
      that needs an account, a profile, or a verification step while there is time to fix it.
      No late-submission policy is stated anywhere, so assume the 11:59 PM IST cutoff is hard.
- [ ] Once inside the panel, **check what it asks for** against this document. If it wants
      something not written here — a tagline, a category, a screenshot, a specific video host —
      add it here while it is cheap.

- [ ] **Submit something early.** The schedule page says the event opened and *"submissions open
      with it"* on 15 October, so the form has been accepting entries since then. If it allows
      edits, a provisional submission now removes the single largest risk in this plan — a panel
      that is slow, or a required field discovered at 23:30 — and everything after it becomes an
      update rather than a race. Check whether edits are allowed the moment you are inside.

      **Submitting early costs nothing, because this is already a valid entry.** Run
      `python3 submission_audit.py`: all six of Rule 10's required items are satisfied right now.
      The repository is public and Apache-2.0, the README carries the setup and the data model,
      the Cypher has its own section, **a demo video is committed** (the captioned walkthrough —
      every frame a real screenshot of the running app), the setup instructions are complete and
      CI-runs them from a clean clone, and the track is named at the top of the page. A live
      Space and a narrated cut are both *improvements* the FAQ prefers, not missing requirements.
      Do not hold the submission waiting for them.

**Then, in order:**

- [x] `git config core.hooksPath scripts` — done; `submission_audit.py` confirms it. The push
      gate now also refuses any commit carrying a credential-shaped string, which matters on the
      next line of this list.
- [ ] `./preflight.sh` — one command, twenty-four checks: the graph counts against the live graph,
      every rendered answer state, the README's printed output, the demo script's facts and
      timing, both benchmarks, and whether the page still renders on GitHub
- [ ] `./scripts_verify_deploy.sh` — builds for linux/amd64 and runs it as a non-root user in a
      container; checks it answers, forks, embeds in an iframe and survives concurrent use, then
      **imposes the hosted envelope rather than asserting it**: a second container at exactly
      512 MB with no swap, flooded with concurrent free text, failing if the kernel kills it. That
      stage exists because the hosted demo *was* killed, on 17 Oct, by the one size the check
      never ran at
- [x] **Deployed — to Render, not Hugging Face.** `./deploy_hf.sh` got HTTP 402: Docker Spaces
      need PRO. `deploy/render.yaml` via the dashboard instead (Blueprint Path
      `deploy/render.yaml`), and the repository homepage set by hand, which `deploy_hf.sh` would
      have done itself
- [x] Confirmed it works for someone signed in to nothing: every check above was an
      unauthenticated request from outside the account — health, all thirteen tools, keyless free
      text, the drawn path, every static route. Worth one look in a real browser before you
      record, since curl does not run JavaScript
- [x] Paste the live URL into the README's Rule 10 table (deployment row)
- [ ] Record the video — `docs/DEMO-SCRIPT.md`, **keyless**, 3:00. The script is checked in CI
      against the live app, so what it says is what the screen shows.
- [ ] Upload unlisted, then **open the link in a private window** to confirm it plays without a
      sign-in
- [ ] Publish the blog post if you want the side prize, and add its link above
- [ ] Submit, naming **every** track you are entering (Rule 5)
- [ ] `python3 submission_audit.py` one last time — it exits non-zero while anything real is
      outstanding, and it reads the repository and the live Space rather than this list

Aim to submit by **18:00 IST Sunday**. The deadline is 11:59 PM IST, and panels get slow.
