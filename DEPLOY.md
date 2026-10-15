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

## Hugging Face Spaces (recommended for a free tier)

No card required, wakes on request, and the image is kept. Sleeps after 48h idle but restarts on the
next visit — which the fast boot makes tolerable.

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

The deployed demo works with **no key**: the scripted questions call the tools directly and run the
same Cypher. To turn on free-text routing, set one of `ANTHROPIC_API_KEY`, `OPENAI_API_KEY`,
`GEMINI_API_KEY` or `GROQ_API_KEY` as a secret on the host.

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
