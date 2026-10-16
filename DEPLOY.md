# Deploying Tombstone

One image holds FalkorDB, the app, the corpus snapshot and the embedding model. It rebuilds the
graph on boot in a few seconds, so there is no external database, nothing to restore, and no state
that can go stale between the submission deadline and a judge clicking the link.

Measured locally: **9s from `docker run` to a healthy, queryable instance** (2s FalkorDB, 6.1s seed).
Image is 1.29 GB.

```bash
docker build -t tombstone .
docker run -p 8099:8099 tombstone
```

## Why not FalkorDB Cloud's free tier

Verified from their docs: free instances are **stopped after 1 day of inactivity and deleted after
7**, with no persistence, no backups and no TLS. A link submitted on Oct 18 and clicked a week later
would be dead or empty. Carrying the data in the image avoids the whole class of problem.

## Hugging Face Spaces

> **Check this before you spend time on it: a Docker Space may need a paid account.**
> Hugging Face's [Spaces overview](https://huggingface.co/docs/hub/spaces-overview), read on
> 16 Oct, says: *"Static Spaces are free for everyone. Gradio and Docker Spaces run on compute
> and require a paid plan to create: PRO for personal accounts."* This Space is `sdk: docker`,
> so on a free personal account `./deploy_hf.sh` may be refused at creation. The
> [Docker Spaces page](https://huggingface.co/docs/hub/spaces-sdks-docker) says nothing about
> plans either way, and I cannot test it without your token — so treat it as a real risk rather
> than a settled fact, and find out in the first five minutes rather than the last.
>
> **If it is refused:** `## Render (free)` and `## Fly.io` below are both configured and
> documented, and a static Space cannot host this (it needs a server and FalkorDB). Either way
> Rule 10 is already satisfied without any deployment — complete local setup plus the committed
> walkthrough — so a refused Space costs the "preferred" bonus, not the submission.

Hardware, when it does run: **16 GB RAM, 2 vCPU, 50 GB non-persistent disk** on CPU Basic. Note
what that means for the memory figures in the README — the 512 MB ceiling asserted by
`./scripts_verify_deploy.sh` is **self-imposed discipline, not a platform limit**, and the real
headroom is thirty times it. Disk is not persistent and free Spaces sleep when idle, neither of
which matters here: the app seeds its graph on boot in seconds and keeps nothing it cannot rebuild.

No card required to visit, wakes on request, and the image is kept. Sleeps after idle but restarts
on the next visit — which the fast boot makes tolerable.

1. Create a Space, SDK = **Docker**.
2. Copy `deploy/README-hf-space.md` to `README.md` **in the Space repo** (its front-matter sets
   `app_port: 8099`).
3. Push this repo to the Space. Build takes a few minutes; boot takes seconds thereafter.

## Render (free)

`deploy/render.yaml` is ready. Caveat worth knowing: free web services **spin down after 15 minutes**
of no traffic and take ~1 minute to wake, so a judge's first click can hit a blank page. Acceptable
only if the submission says so.

## Fly.io

`deploy/fly.toml` sets `min_machines_running = 1` so the app never scales to zero. New organisations
get no free allowance, so this one costs a few dollars a month — which is the most reliable option if
that is acceptable.

## Enabling free-text questions

The deployed demo works with **no key**, and that includes typed questions: without a key they are
routed locally by embedding similarity over the fixed tool catalogue, using the model already baked
into the image. Setting one of `ANTHROPIC_API_KEY`, `OPENAI_API_KEY`, `GEMINI_API_KEY` or
`GROQ_API_KEY` as a secret on the host swaps that router for a model.

Either way the contract is the same: the router picks a **tool name**, hand-written Cypher answers,
and nothing generated is concatenated into a query. A keyless instance is not a degraded one.

If you do, set a hard spend cap in the provider dashboard as well as in code. A public demo with an
uncapped key is a bill waiting to happen, and the key must never reach the browser — all model calls
go through `/api/ask` server-side.

## Verifying a deploy

```bash
curl -s https://<host>/api/health | python3 -m json.tool          # expect "falkordb": "up"
curl -s -X POST https://<host>/api/tool \
  -H 'content-type: application/json' \
  -d '{"tool":"ownership_dilution","args":{}}'                    # expect 7 rows
```

Before submitting, open the live URL **from a different network, in a private window**, and confirm
it works with no sign-in.

## Runs as a non-root UID — verified, not assumed

Hugging Face Spaces runs containers as **UID 1000** with limited write access, which is a common
way an image that works locally fails on first deploy. So it is tested both ways:

```bash
docker run --user 1000:1000 -p 8099:8099 tombstone   # how Spaces runs it
docker run                  -p 8099:8099 tombstone   # how you run it locally
```

| | result |
|---|---|
| as UID 1000 | **ready in 7s**, seeded 2.26s, queries 16–46ms |
| as root | ready in 4s |

Getting there needed three fixes, each found by actually running it rather than predicting:
every cache lives under `/app/.cache` (not `$HOME` or `/tmp`, which the platform may mount
differently); `/var/lib/falkordb/data` is **created** in the image, because redis opens its data
dir at startup even with RDB and AOF both disabled; and the startup wait now **exits 1 with the
redis error** instead of hanging for 40 seconds and then failing silently — which is how the
missing data dir was caught.

## Architecture — verified, not assumed

I develop on arm64 (Apple silicon). **Every free host runs amd64**, so an image that only works on
arm64 would fail on the first deploy — and the Python dependencies here include `onnxruntime` via
`fastembed`, which ships native wheels and is exactly the kind of thing that breaks across
architectures.

So I built and ran it:

```bash
docker buildx build --platform linux/amd64 -t tombstone:amd64 --load .
docker run --platform linux/amd64 -p 8111:8099 tombstone:amd64
```

| | result |
|---|---|
| base image `falkordb/falkordb:v4.22.1` | publishes **linux/amd64 and linux/arm64** |
| amd64 build | **succeeds**, including the baked-in embedding model |
| amd64 cold start | **12s** under emulation (faster on a real amd64 host) |
| seed | 2.25s — 679 decisions, 753 named options, 959 vectors |
| `has_this_been_tried` (exercises the embedding path) | `ANSWERED_WITH_PATH`, 62ms emulated |
| `stale_knowledge` | `ANSWERED_WITH_PATH`, 28ms emulated |

Deploy to an amd64 host with no architecture surprises.
