# graph hack — Graph Hacks 2026 (WeMakeDevs x FalkorDB)

Research and de-risking phase. Concept selection in progress; see `docs/`.

## What is verified so far
- `docs/GROUND-TRUTH.md` — FalkorDB capability + performance surface, **measured locally**, not from docs.
  Includes the 73x edge-ingest finding, multi-tenancy scaling to 1000 graphs, and six silent traps.
- `docs/K8S-CORPUS-VERIFIED.md` — the Kubernetes governance corpus, parsed and counted myself, with a
  working end-to-end FalkorDB ingest (1.65s) and 7 money-shot queries.
- `docs/DATASETS.md` — live availability probe of 18 public APIs, plus one rejected candidate (FAERS).
- `docs/STRATEGY.md` — the reconstructed judging rubric and the competitive field census.

## Run FalkorDB
```bash
docker compose up -d
```
Published on **6380**, not 6379: a local Homebrew `redis-server` commonly owns 6379 and silently
shadows Docker's mapping, which surfaces as `unknown command 'GRAPH.QUERY'`.

## Spikes
`spikes/` holds the throwaway benchmarks and feasibility probes behind the numbers in `docs/`.

## AI assistance disclosure
Built with AI coding assistance. The graph model, the Cypher, the benchmark methodology and the
technical decisions are mine, and every performance number in `docs/` is from a benchmark I ran and
can re-run. Where a research agent's figure disagreed with my own parse, my parse is used and the
discrepancy is recorded.
