---
title: Tombstone
emoji: 🪦
colorFrom: gray
colorTo: red
sdk: docker
app_port: 8099
pinned: false
license: apache-2.0
short_description: The decisions your org already made and forgot. A Company Brain on FalkorDB over Kubernetes' real governance record.
---

# Tombstone

**The decisions your org already made and forgot. Asked as a graph.**

Ask *"has anyone tried this before?"* and get the rejected design option, the recorded reason, and
whether anyone who made that call still holds approval authority — over **Kubernetes' real public
governance record**, not an invented company. 681 decisions, 958 rejected alternatives, 794 people,
585 ownership files.

**It does not only answer — it acts.** It finds places where the project's own record contradicts
itself and drafts the `OWNERS` patch that fixes them. The part worth looking at is what it
does not draft: the strongest-looking candidate never becomes a candidate at all, because that file is
vendored from another repository and the exclusion lives in the Cypher; the one it does
refuse is refused because the person's handle is not in the file at all — an alias expands
to them, so no edit to that file would remove them.

**No sign-up and no API key.** The buttons call the tools directly, and typed questions work too:
with no key configured they are routed locally by meaning against a fixed catalogue, then answered
by the same hand-written Cypher. Ask it for a poem and it declines by name rather than guess.

**What happens to what you type.** An answered question is written into the graph as a node
carrying the question text — that is the memory feature working, not a side effect — and the
"Has this graph been asked this before?" button will show it to whoever visits next. Nothing is
sent anywhere else, and there is no account to attach it to.

Try these:

- *Who owns the apiserver metrics endpoint?* — shallow returns **nothing**, with a statement of
  what was searched. Four hops explains why.
- *Draft the fix* — two patches drafted, one candidate refused with its reason.
- Type anything. It answers or it tells you it will not guess.

This Space runs FalkorDB and the app in one container and rebuilds the graph from a committed
snapshot on every boot, so there is nothing to go stale and no external database to restore.
Measured on the image this Space is built from: **3.7 s** from container start to the health
endpoint reporting FalkorDB up, and **1.5 s** more for the first real answer. That was an
M-series laptop; a Space's shared CPU will be slower, and a Space that has gone to sleep pays its
own wake-up before any of this starts. The whole thing boots at **144 MiB** and holds **288 MiB
under eight concurrent free-text asks**, measured on the real linux/amd64 image inside a 512 MB
container with no swap. That is the figure to trust: the earlier one, ~450 MiB "in serial use",
was measured serially and the hosted Render instance was killed on 17 Oct by concurrency it never
covered.

The graph counts above — 681, 958, 794, 585 — are re-queried against the live database by
scripts that run in CI on every push, along with 36 graph claims and 190 tests. The boot and
memory figures are not: they need Docker and a built image, so they are measured by
`scripts_verify_deploy.sh` on a developer machine and are dated readings rather than gates. This
sentence used to say "every number above", which covered both and was true of only one.

Any claim that did not survive being checked is marked rather than deleted.

Source, and the honest version of all of it: https://github.com/aviralgarg05/tombstone
