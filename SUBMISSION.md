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

*Nobody can see the form's fields until you are registered, and the Description below is 3556 characters. These are the same pitch at two shorter lengths so a character limit is a paste, not a rewrite at 11pm.*

**~273 characters:**

> Tombstone turns Kubernetes' own governance record into a graph and answers what no document states: one person is the entire review capacity for the apiserver's metrics endpoints. It drafts the OWNERS patch that fixes what it finds, and refuses the cases it cannot justify.

**~1085 characters:**

> Large engineering orgs re-propose things they already rejected, because a rejected option is not a document — it is a subsection buried in a proposal about something else, with no identity, no index entry and no owner. Tombstone makes it a first-class node on FalkorDB, attaches the person who killed it, and answers questions that are traversals rather than lookups: has this been tried, who really owns this, whose stepping back cost the most connective authority, what breaks if one more person leaves.
>
> It runs on Kubernetes' real governance record — 681 decisions, 958 rejected alternatives, 794 people, 585 ownership files. Nothing synthetic. The headline finding is written down nowhere: it is only true as a consequence of the structure.
>
> It acts, then stops: it drafts a real OWNERS patch and refuses the strongest-looking candidate because that file is vendored. Nothing here is asserted — 128 tests, 36 graph claims re-queried against the live database on every push. I measured the premise above and could not confirm it on this corpus, and say so rather than lead with it.

## Track

> **Track 03 — Company Brain.**

That line is the whole answer; everything below it is for your decision, not for the form.

---

*Second track, if entering more than one.* The field as of 16 Oct, from public repositories
rather than from a gallery — there is none. Fifteen-plus entries are now public, and at least
three are serious Track 3 builds:

| entry | what it is | tracks |
|---|---|---|
| `Sumit99589/orion` | forks the company graph into a "parallel universe" before a change, live on Vercel, MCP server, per-person memory graphs | all three |
| `Vaibhaav-Tiwari/lineage` | truth maintenance: when a decision reverses, the answers and beliefs built on it are struck through and actions blocked. 745 PEPs plus forum threads and commits since 2015 | two |
| `StarKnightt/threadline` | 3D replay of every traversal, a verifier agent that path-checks each citation, 60-question eval | all three |

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
tests to 128.** It is bigger and better-tested, it is honest about its own limits, and it is not
deployed either — its README says the demo and video come before submission. Do not tell anyone
this is the only entry using real data. It is not.

What is actually distinctive is narrower and survives the comparison. Kubernetes publishes
`emeritus_approvers`: an explicit, maintained record of who stepped back, which is what every
finding here is built on. lineage discloses the opposite in its own weaknesses — *"Listed owners
are known only for today"* — so it has the decisions and the people without the attrition. That is
the gap this corpus was chosen for, and it is the one claim worth making about it.

**No other entry found is using this corpus.** Three GitHub searches — for `emeritus_approvers`,
for FalkorDB entries mentioning OWNERS files, and for Kubernetes enhancements plus KEP — return
only this repository. The others each chose their own: threadline reads the FalkorDB org's GitHub
history, orion a synthetic company of people, teams, systems and customers, lineage the Python
PEPs and the forum threads behind them. That matters for one reason worth saying out loud in the
submission: **Kubernetes is the only one of those where the organisation publishes its own
attrition.** `emeritus_approvers` is a field a real project maintains about people who stepped
back, and the whole product is built on reading it. A synthetic company cannot have that, and a
repository's commit history only implies it. (Searches are evidence of absence only to the extent
GitHub's index is complete, and entries can be private until submission.)

Two more Track 3 entries have appeared since: `volfiros/axon-brain`, which stores access rules in
the graph and filters every query before anything reaches the model, and `rossycoder/dealership-brain`,
whose README separates what is real from what is stubbed and whose dataset is a fictional dealership.

Read their READMEs rather than run them, so the feature claims are what they claim, not what they
do — but the deployments I did check, by request rather than by reading.

A later sweep found the Track 3 field is wider than these five. `RISHIK92/company-brain` (2.3MB,
a temporal cited knowledge graph of people and decisions) and `cyh7789/passthru` are substantial
and **neither advertises a URL**; `Laimos-code/lore-company-brain` is 6KB, a README. So the honest
count on 16 Oct is **four deployed out of eight visible Track 3 entries** — orion, threadline,
axon-brain and dealership-brain answered HTTP 200; lineage, RISHIK92/company-brain,
lore-company-brain and passthru have no public URL.

That is a weaker claim than "everyone else is live", and it is the true one. Deploying is still
worth doing — the FAQ says a hosted demo is preferred, and half the serious field has one — but
it is an advantage to gain rather than a hole to climb out of. Nothing had pushed since 15 Oct
23:14 when this was written.

Two things follow that are worth acting on. **Multi-track entry is normal here**, so entering one
track is a choice and should be a reasoned one. And the live demo is the clearest gap in this
submission, not a nice-to-have — it is now the one thing the rest of the field has and this does
not. Note what the deployment does *not* settle: orion's demo company is explicitly synthetic,
dealership-brain's is a fictional dealership. Being deployed and being checkable are different
claims, and this entry has the second without the first.*

*Reasoning, and the new field strengthens it rather than weakening it:* Track 02 (Agent Memory)
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
worth looking at is what it refuses to draft: the strongest-looking candidate in the whole corpus
is excluded because that file is vendored from another repository, and a second is refused because
the person's handle is not in the file at all — an alias expands to them, so no edit to that file
would remove them.

Nothing here is asserted. **31 CI steps on every push** re-check it: 128 tests, 36 graph claims
re-queried against the live database, 18 rendered UI states checked for panels that render empty,
the drafting action's own output, the memory claims, two of the five benchmarks re-run — the
other three build a thousand graphs or millions of edges, so they are dated measurements with
committed scripts rather than gates, and the README says which is which — and a job that runs
the quickstart on a machine that already has a `falkordb` container — the case that used to break
it. The graph is scored against a text baseline over the same documents: **24/25 versus 9/25**, in
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
> What I changed as a result is the part I would defend: every number on the page is now
> re-derived from the live database by a script that runs on each push, the withdrawn claims are
> struck through rather than deleted, and the eval has a control category that exists so the text
> baseline can win — which it does, nine-all. A page that records what it got wrong is worth more
> than one that never looked.

## What I would do next

> Three things, in the order they would matter. **Reach the 163 rejections the search cannot
> see** — they are in the graph and the lineage queries find them, but their extracted titles came
> out as sentences so they were never embedded, which makes them invisible to the one tool whose
> job is finding rejections. **Earn the tenancy claim**: the mechanism is measured to 1,000 graphs
> but this app is single-tenant and never switches graphs, so what is demonstrated is that it
> works, not that this uses it. **Ingest something that is not a document** — the rules rightly
> forbid private tickets and chats, and a fabricated company proves nothing, so this is docs only
> until there is a public corpus with real tickets attached to real decisions.

## Links

| | |
|---|---|
| Repository | https://github.com/aviralgarg05/tombstone |
| Live demo | *(fill in after `./deploy_hf.sh`)* |
| Demo video | *(fill in — narrated cut per `docs/DEMO-SCRIPT.md`)* |
| Fallback video | `docs/video/walkthrough-silent.mp4`, 86s, captioned, in-repo |
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
the one decision inside it worth defending (752 embedded options out of 958 extracted, and why the
other 206 are not, and why only about 22 of those are actually artefacts), what each of the thirteen tools asks, which
FalkorDB feature earns its place in which tool, what the model is allowed to do, and the five
weakest things — stated first, because every one of them is already written down in the repository.

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
- [ ] `./preflight.sh` — one command, twenty-one checks: the graph counts against the live graph,
      every rendered answer state, the README's printed output, the demo script's facts and
      timing, both benchmarks, and whether the page still renders on GitHub
- [ ] `./scripts_verify_deploy.sh` — builds for linux/amd64 and runs it as a non-root user in a
      512 MB container exactly as a Space does, then checks it answers, forks, embeds in an
      iframe and survives concurrent use
- [ ] `export HF_TOKEN=hf_...` then `./deploy_hf.sh` — it sets the repo homepage, writes the live
      URL into this file, and arms the keep-awake workflow by itself
- [ ] Open the Space **in a private window** and click chip 1, to confirm it works for someone who
      is not signed in to Hugging Face. That is every judge.
- [ ] Paste the Space URL into the README's Rule 10 table (deployment row)
- [ ] Record the video — `docs/DEMO-SCRIPT.md`, **keyless**, 3:00. The script is checked in CI
      against the live app, so what it says is what the screen shows.
- [ ] Upload unlisted, then **open the link in a private window** to confirm it plays without a
      sign-in
- [ ] Publish the blog post if you want the side prize, and add its link above
- [ ] Submit, naming **every** track you are entering (Rule 5)
- [ ] `python3 submission_audit.py` one last time — it exits non-zero while anything real is
      outstanding, and it reads the repository and the live Space rather than this list

Aim to submit by **18:00 IST Sunday**. The deadline is 11:59 PM IST, and panels get slow.
