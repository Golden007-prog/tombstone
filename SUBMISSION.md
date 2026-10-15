# Submission — ready to paste

Everything the WeMakeDevs panel asks for, written out so none of it is composed at 11pm on the
18th. Rule 10's six required items are mapped in the README; this is the copy.

**Deadline: 11:59 PM IST, Sunday 18 October 2026.** Aim to submit by 18:00 IST — panels get slow.

---

## Title

Tombstone

## One line

The decisions your org already made and forgot. Asked as a graph.

## Track

**Track 03 — Company Brain.**

*Second track, if entering more than one.* For context when deciding: at least one competing
Track 3 entry (`StarKnightt/threadline`) is entering three tracks, so multi-track entry is clearly
permitted and being used. That is a reason to decide deliberately, not a reason to follow.*

*Reasoning:* Track 02 (Agent Memory) is arguable but not yet
earned. Answers persist as `(:Answer)` nodes that `CITED` the real records they came from, and a
later session gets `ANSWERED_FROM_MEMORY` only when those citations still resolve — so memory
invalidates itself when the graph moves underneath it. What Track 02 also asks for is agents that
**share state with each other**, and there is one agent here, not several. Entering on a half-met
brief would weaken the Track 3 entry rather than add to it. Decide deliberately; do not drift into
it.

## Description

Large engineering orgs keep re-proposing things they already rejected, because the rejection was
never a thing you could look up. (I tried to measure that premise on this corpus and could not
confirm it — the measurement is in the README, along with the weaker claim that *is* demonstrated:
a rejected option is not retrievable at all today, so the question cannot be asked by anyone.)
The rejected option is not a document — it is a 200-word
subsection buried inside a 4,000-word proposal about something else. It has no identity, so you
cannot count how often an idea was refused, you cannot ask who refused it, and you cannot find out
whether anyone who knows why is still around.

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

Nothing here is asserted. **27 CI steps on every push** re-check it: 107 tests, 26 graph claims
re-queried against the live database, 17 rendered UI states checked for panels that render empty,
the drafting action's own output, the memory claims, both benchmarks re-run, and a job that runs
the quickstart on a machine that already has a `falkordb` container — the case that used to break
it. The graph is scored against a text baseline over the same documents: **7/8 versus 2/8**, and
it loses one of those eight on purpose.

Several claims did not survive that process and are **marked in the README rather than deleted**:
a benchmark that said FalkorDB computed betweenness 18x faster than networkx (on the real graph it
is roughly a tie), a multi-tenancy latency curve that did not reproduce on a second run, and the
project's own opening premise. A page that documents what it got wrong is worth more than one that
never checked.

## Against the organisers' own published principles

There are no judging criteria, but WeMakeDevs published *How to build an agent that reasons over
a graph*. The README maps every principle in it to where that piece lives here — the fixed tool
catalogue, names resolved before any query runs, the four answer shapes (named the same way),
"not in the graph" kept distinct from "nothing breaks", the path returned with the answer rather
than an explanation written afterwards, memory as nodes with a date, tenants isolated by separate
graphs, and a demo that asks the same question at two depths.

Worth saying in the submission because it was not designed to match: I found the article in the
Resources page after building this.

## Links

| | |
|---|---|
| Repository | https://github.com/aviralgarg05/tombstone |
| Live demo | *(fill in after `./deploy_hf.sh`)* |
| Demo video | *(fill in — narrated cut per `docs/DEMO-SCRIPT.md`)* |
| Fallback video | `docs/video/walkthrough-silent.mp4`, 50s, captioned, in-repo |
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
python3.13 -m venv .venv && ./.venv/bin/pip install -r requirements.txt   # Python 3.11-3.14
./run.sh          # FalkorDB up, graph seeded from the committed snapshot in ~1.1s
```

Then open <http://localhost:8099>. **No API key and no account.** The buttons call the tools
directly, and typed questions work too — routed locally by embedding similarity over the fixed
catalogue, which refuses rather than guess. Verified from a clean clone in an empty directory.

## AI assistance disclosure (Rule 11)

See the AI assistance disclosure section of the README.

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
      with it"* on 15 October, so the form has been accepting entries for two days. If it allows
      edits, a provisional submission now removes the single largest risk in this plan — a panel
      that is slow, or a required field discovered at 23:30 — and everything after it becomes an
      update rather than a race. Check whether edits are allowed the moment you are inside.

**Then, in order:**

- [ ] `git config core.hooksPath scripts` — once, so a push cannot carry a state the checks
      already know is broken (it happened twice; resolve is not a mechanism)
- [ ] `./preflight.sh` — one command, sixteen checks: every number against the live graph,
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

Aim to submit by **18:00 IST Sunday**. The deadline is 11:59 PM IST, and panels get slow.
