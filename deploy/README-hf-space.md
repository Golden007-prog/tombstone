---
title: Tombstone
emoji: 🪦
colorFrom: gray
colorTo: red
sdk: docker
app_port: 8099
pinned: false
license: apache-2.0
---

# Tombstone

**The decisions your org already made and forgot. Asked as a graph.**

Ask *"has anyone tried this before?"* and get the rejected design option, the recorded reason, and
whether anyone who made that call still holds approval authority — over **Kubernetes' real public
governance record**, not an invented company. 681 decisions, 958 rejected alternatives, 794 people,
585 ownership files.

**It does not only answer — it acts.** It finds places where the project's own record contradicts
itself and drafts the `OWNERS` patch that fixes them. The part worth looking at is what it
*refuses* to draft: the strongest-looking candidate in the whole corpus is excluded because that
file is vendored from another repository, and a second is refused because the person's handle is
not in the file at all — an alias expands to them, so no edit to that file would remove them.

**No sign-up and no API key.** The buttons call the tools directly, and typed questions work too:
with no key configured they are routed locally by meaning against a fixed catalogue, then answered
by the same hand-written Cypher. Ask it for a poem and it declines by name rather than guess.

Try these:

- *Who owns the apiserver metrics endpoint?* — shallow returns **nothing**, with a statement of
  what was searched. Four hops explains why.
- *Draft the fix* — two patches drafted, one candidate refused with its reason.
- Type anything. It answers or it tells you it will not guess.

This Space runs FalkorDB and the app in one container and rebuilds the graph from a committed
snapshot on every boot — **about 5 seconds warm, nearer 10 from cold** — so there is nothing to go
stale and no external database to restore.

Every number above is re-checked against the live graph by scripts that run in CI on every push,
including the claims that did not survive being checked, which are marked rather than deleted.

Source, and the honest version of all of it: https://github.com/aviralgarg05/tombstone
