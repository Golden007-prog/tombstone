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

**All three hosting paths below were validated against their providers' current documentation on
16 Oct**, because configuration files rot quietly against other people's platforms and this one is
read under deadline. In short, so you can choose in thirty seconds:

| path | config | state |
|---|---|---|
| **Hugging Face Spaces** | `deploy/README-hf-space.md` | Front-matter valid against HF's field reference and gated in the push gate — but **refused on a free account: HTTP 402, tested 17 Oct.** Docker Spaces need PRO ($9/month), which buys the 16 GB CPU Basic box this image was sized for. See below for the prediction I got wrong. |
| **Render (free)** | `deploy/render.yaml` | **Live, and the one that is actually serving.** Valid against the current blueprint spec, using `runtime:` rather than the deprecated `env:`. It was killed for exceeding 512 MB on 17 Oct and now fits **under concurrency** — the running instance reports 263.7 MiB of 512 after sixteen concurrent asks, and the deploy check reproduces the envelope at 512 MB locally. Spins down after 15 min. |
| **Fly.io** | `deploy/fly.toml` | Valid, current `[[vm]]` syntax, `min_machines_running = 1` so it never cold-starts. No free allowance — a few dollars a month. |

Rule 10 is satisfied with **no deployment at all** — complete local setup plus the committed
walkthrough — so none of these is load-bearing for the submission itself.

## Why not FalkorDB Cloud's free tier

Verified from their docs: free instances are **stopped after 1 day of inactivity and deleted after
7**, with no persistence, no backups and no TLS. A link submitted on Oct 18 and clicked a week later
would be dead or empty. Carrying the data in the image avoids the whole class of problem.

## Hugging Face Spaces

> **The documentation says a Docker Space needs a paid account. The platform does not appear to
> agree, and I measured that rather than guessing.**
> Hugging Face's [Spaces overview](https://huggingface.co/docs/hub/spaces-overview), read on
> 16 Oct, says: *"Static Spaces are free for everyone. Gradio and Docker Spaces run on compute
> and require a paid plan to create: PRO for personal accounts."* This Space is `sdk: docker`,
> and that sentence would block it.
>
> **It does block it. Tested on 17 Oct: HTTP 402 Payment Required** from
> `POST /api/repos/create`, with the body *"Static Spaces are free for everyone, but hosting
> Gradio and Docker Spaces on free cpu-basic requires a PRO subscription."* The sentence in the
> docs is enforced.
>
> I had argued the other way here, and the reasoning is worth keeping because the failure in it
> is instructive. I asked the API: of the sixty most recently created Spaces on 16 Oct, three
> were `sdk: docker`, the newest about an hour old, and all three owners returned `isPro: false`
> from HF's public user endpoint — so I concluded free accounts were creating Docker Spaces and
> this would probably work. The observation was accurate; the inference was not. `isPro` on a
> public profile is not the entitlement checked at repository creation, those Spaces may have
> been created under arrangements the endpoint does not expose, and in any case reading a listing
> is not attempting the operation. I reported a measurement as though it settled a question it
> could not settle, which is the same error this project keeps catching in its own prose.
>
> `./deploy_hf.sh` failed fast and loudly at the right step, before staging or uploading, so the
> cost
> of finding out is a minute.
>
> **If it is refused:** `## Render (free)` and `## Fly.io` below are both configured and
> documented, and a static Space cannot host this (it needs a server and FalkorDB). Either way
> Rule 10 is already satisfied without any deployment — complete local setup plus the committed
> walkthrough — so a refused Space costs the "preferred" bonus, not the submission.

Hardware, when it does run: **16 GB RAM, 2 vCPU, 50 GB non-persistent disk** on CPU Basic — thirty
times the headroom of the free Render box, and the size this image was originally sized for. That
framing is what made the 512 MB number feel like discipline rather than a constraint, and it was
wrong about where the app actually runs: Render is what is serving, 512 MB is a platform limit
there, and on 17 Oct it was enforced by the kernel. Disk is not persistent and free Spaces sleep when idle, neither of
which matters here: the app seeds its graph on boot in seconds and keeps nothing it cannot rebuild.

No card required to visit, wakes on request, and the image is kept. Sleeps after idle but restarts
on the next visit — which the fast boot makes tolerable.

1. Create a Space, SDK = **Docker**.
2. Copy `deploy/README-hf-space.md` to `README.md` **in the Space repo** (its front-matter sets
   `app_port: 8099`).
3. Push this repo to the Space. Build takes a few minutes; boot takes seconds thereafter.

## Render (free)

`deploy/render.yaml` is ready, and **validated against Render's current blueprint spec on 16 Oct**:
`runtime: docker` (the field that replaced the deprecated `env`), `plan: free`, `dockerfilePath`
and `healthCheckPath` all current, nothing deprecated. The container's entrypoint binds
`${PORT:-8099}`, so it honours the port Render injects rather than hard-coding one.

**Exact steps, and the one that is easy to miss.** Render's docs say it "looks for `render.yaml`
at the repository root by default" and that you "can define your Blueprint file anywhere" by
setting the **Blueprint Path** field. This file is at `deploy/render.yaml`, *not* the root, so
leaving that field empty gives you a blueprint-not-found error rather than a deploy:

1. [dashboard.render.com](https://dashboard.render.com) → **New** → **Blueprint**
2. Connect this GitHub repository
3. Set **Blueprint Path** to `deploy/render.yaml` ← the step that is easy to miss
4. Apply. First build takes a few minutes on 0.1 CPU; `healthCheckPath` is `/api/health`,
   which only answers once FalkorDB is up and the graph is seeded, so a green health check means
   the graph really built.
5. **Set the repository homepage to the Render URL.** `./deploy_hf.sh` did this itself; nothing
   in the Render flow does, and two things read that field: the About box a judge clicks, and
   `.github/workflows/keepwarm.yml`, which every six hours proves the deployment still answers
   with real rows from the graph. Leave it empty and both are silently off.
   ```bash
   gh repo edit --homepage https://tombstone.onrender.com   # your actual URL
   ```
   Then paste the same URL into the README's **Live demo** line and SUBMISSION.md.

No token is handled anywhere in that flow — it is a browser and your own account throughout.

**What that six-hourly job can and cannot do here.** On Hugging Face a free CPU Space idles for
48 hours before sleeping, so a six-hourly ping genuinely keeps it warm. Render free spins down
after **15 minutes**, which no cron on this schedule can hold open — and pinging a free tier
every fourteen minutes to try is unreliable on GitHub's scheduler and not a reasonable thing to
do to someone else's free compute. So on Render it is a **health check**: it proves the thing
still works. The ~1 minute cold start stays a disclosed property of the free plan, which is why
the submission should say so rather than hope a judge clicks twice.

Two caveats, and they are the reason this is the fallback rather than the plan. Free web services
**spin down after 15 minutes** of no traffic and take ~1 minute to wake, so a judge's first click
can hit a blank page — acceptable only if the submission says so. And the free plan is **0.1 CPU
and 512 MB**, which on **17 Oct killed the hosted instance mid-serve**: four concurrent free-text
asks were enough, because each concurrent embed took its own ~119 MiB ONNX arena. That is fixed —
embedding is serialised process-wide in [`src/tombstone/embedding.py`](src/tombstone/embedding.py)
and the allocator is bounded in the `Dockerfile` — and the fix is checked at the hosted size
rather than argued about: `./scripts_verify_deploy.sh` now runs a second container at exactly
512 MB with no swap and floods it with concurrent free text. And then measured **on the live
instance itself**, which is what actually settles it: idle after a wake **91.6 MiB of 512**, and
after 16 distinct asks eight at a time — the shape that killed it — **263.7 MiB of 512, all 16
answered, nothing dropped**. One question at a time returns in 0.4–1.7 s; sixteen at once took
67 s for the last one out, which is a tenth of a CPU queueing rather than the lock. On a tenth of
a CPU the first boot will also be slow, which the `healthCheckPath` needs to outlast.

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

`/api/health` also carries a `memory` object — `server_rss_mb`, `container_mb` and `limit_mb`,
read from `/proc` and the cgroup **on the instance**. Every memory figure in this repository was
measured on a laptop, and the one that mattered was measured on the wrong architecture with the
wrong workload, which is how the hosted demo came to be killed. So the instance reports its own,
and the claim is checkable against the live URL instead of on this file's word:

```bash
curl -s https://<host>/api/health | python3 -c \
  'import json,sys; print(json.load(sys.stdin)["memory"])'        # on the box, not a laptop
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
