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
whether anyone who made that call still works here — over **Kubernetes' real public governance
record**, not an invented company.

Graph Hacks 2026 (WeMakeDevs x FalkorDB), Track 3 — Company Brain.
Source: https://github.com/aviralgarg05/tombstone

This Space runs FalkorDB and the app in one container and rebuilds the graph from a committed
snapshot on every boot (~6s), so there is nothing to go stale and no external database to restore.
No sign-up and no API key are needed to use it.
