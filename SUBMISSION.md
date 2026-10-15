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

*Second track, if entering more than one:* Track 02 (Agent Memory) is arguable but not yet
earned. Answers persist as `(:Answer)` nodes that `CITED` the real records they came from, and a
later session gets `ANSWERED_FROM_MEMORY` only when those citations still resolve — so memory
invalidates itself when the graph moves underneath it. What Track 02 also asks for is agents that
**share state with each other**, and there is one agent here, not several. Entering on a half-met
brief would weaken the Track 3 entry rather than add to it. Decide deliberately; do not drift into
it.

## Description

Large engineering orgs keep re-proposing things they already rejected, because the rejection was
never a thing you could look up. The rejected option is not a document — it is a 200-word
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

And it does not only answer. It **acts**: it finds places where the project's own record
contradicts itself — someone recorded as having stepped back from several areas while one other
file still lists them as an active approver — and drafts the OWNERS patch that fixes it. The part
worth looking at is what it refuses to draft: the strongest-looking candidate in the whole corpus
is excluded because that file is vendored from another repository, and a second is refused because
the person's handle is not in the file at all — an alias expands to them, so no edit to that file
would remove them.

Every number in the README is re-checked against the live graph by a script that runs in CI, and
the graph is scored against a text baseline over the same documents: **7/8 versus 2/8**.

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
python3 -m venv .venv && . .venv/bin/activate && pip install -r requirements.txt
./run.sh          # FalkorDB up, graph seeded from the committed snapshot in ~1.1s
```

Then open <http://localhost:8099>. **No API key and no account** — the demo's buttons call the
tools directly and run the same Cypher. Verified from a clean clone in an empty directory.

## AI assistance disclosure (Rule 11)

See the AI assistance disclosure section of the README.

---

## Pre-submit checklist

- [ ] `./scripts_verify_deploy.sh` first — builds the image for linux/amd64 and runs it as a
      non-root user exactly as a Space does, then asserts the product actually answers
- [ ] `./deploy_hf.sh` and paste the Space URL above, in the README, and `gh repo edit --homepage`
- [ ] Record the narrated video (`docs/DEMO-SCRIPT.md` — 464 words, 2.6 w/s, verified speakable)
- [ ] Upload unlisted, then **open it in a private window** to confirm it plays without a sign-in
- [ ] Flip the README's Rule 10 table rows for video and deployment to done
- [ ] Register on the panel early; do not discover a required field at 23:30
- [ ] Name every track you are entering (Rule 5)
