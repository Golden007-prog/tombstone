"""How much does the agent's memory cost to keep? Measured, because the README states a number.

The deploy check reports peak memory with an EMPTY memory graph, so its figure is the floor
rather than the shape of a Space that has been used. This records a batch of answers and watches
the database grow, which is the only honest way to put a number on "memory grows with use".

Two things learned writing it, both preserved here as guards:

  - A first attempt asked unanswerable questions and recorded almost nothing, because only the
    answering shapes are written back. The questions below are ones that actually answer, and the
    script asserts it recorded what it meant to.
  - A first instrument reported NEGATIVE growth -- allocator noise swamping a small signal. A
    result saying memory fell when you added data is a broken instrument, so this refuses to
    report a per-answer cost unless the total delta clears a floor.

Usage:  ./run.sh    (in another shell)
        PYTHONPATH=src python bench_memory_growth.py
"""
from __future__ import annotations

import subprocess
import sys

sys.path.insert(0, "src")
from graphkit.ingest import connect          # noqa: E402
from tombstone.agent import Agent            # noqa: E402

ANSWERING = [
    "which areas have exactly one approver", "who should inherit lavalamp areas",
    "which areas lost every dedicated owner", "what knowledge here is going stale",
    "which cited decisions no longer exist", "which contributor group is hollowing out",
    "whose stepping back cost the most connective authority",
    "whose ownership record contradicts itself",
]
BLOCKS = 2                # two blocks, because the point is the
BLOCK = 200               # DIFFERENCE between the first and the last
CEILING_MB = 512          # the serial ceiling the deploy check asserts
# The container's floor, as ./scripts_verify_deploy.sh measures it on the actual linux/amd64
# image: 288 MiB under eight concurrent asks at the hosted size. It has now read 387 here,
# "about 400 MB" in the Space README, 450 MiB from the serial measurement, and this -- four
# figures for one quantity, each left behind by the change that moved it. 450 survived here
# longest because this file is a benchmark nobody re-reads, and a stale constant in a script that
# PRINTS a projection is worse than one in prose: it manufactures new wrong numbers on every run.
# The live instance's own figure is lower still, 263.7 MiB after sixteen concurrent asks, read off
# /api/health rather than a laptop; the larger local number is used here so the projection errs
# toward the ceiling rather than away from it.
#
# Note what is being added to what: the per-answer cost below is FalkorDB's own used_memory,
# while this ceiling is whole-container RSS (the app, uvicorn, the embedding model and the
# database). The projection assumes database growth shows up one-for-one in container RSS, which
# is roughly true because the database is in the container, and is the reason these totals are
# "about".
BASELINE_MB = 288


def used_bytes() -> int:
    out = subprocess.run(["docker", "exec", "falkordb", "redis-cli", "INFO", "memory"],
                         capture_output=True, text=True).stdout
    for line in out.split("\n"):
        if line.startswith("used_memory:"):
            return int(line.split(":")[1])
    sys.exit("could not read used_memory from the falkordb container; is it running?")


def sweep(graph) -> int:
    """Remove only the rows this benchmark writes, matched by their "(variant N)" suffix."""
    return int(graph.query(
        "MATCH (a:Answer) WHERE a.question CONTAINS '(variant ' "
        "WITH a, count(a) AS _ DETACH DELETE a RETURN count(_)").result_set[0][0] or 0)


def main() -> int:
    """Measure, then clean up WHATEVER happened -- see _measure for why that is the shape."""
    graph = connect().select_graph("tomb:k8s")
    # Sweep first. A run that exits on one of the guards below used to leave its 200 rows in the
    # graph, and then the next run asked those same questions, got ANSWERED_FROM_MEMORY for every
    # one, recorded nothing new, and reported "these questions stopped answering" -- a true
    # statement about a graph the previous failure had poisoned. Wiring this into ./preflight.sh
    # is what surfaced it: one noisy run made every later run fail, with a message pointing at
    # the wrong thing.
    stale = sweep(graph)
    if stale:
        print(f"  swept {stale} rows an earlier run left behind before measuring")
    try:
        return _measure(graph)
    finally:
        removed = sweep(graph)
        left = int(graph.query("MATCH (a:Answer) RETURN count(a)").result_set[0][0])
        print(f"\n  cleaned up {removed} of its own rows; {left} answers remain, "
              f"which is what was here before it ran")


def _measure(graph) -> int:
    count = lambda: int(graph.query("MATCH (a:Answer) RETURN count(a)").result_set[0][0])
    agent = Agent(graph_name="tomb:k8s")

    n0 = count()
    print(f"  starting from {n0} stored answers"
          + (" -- an empty memory, so the first block measures the one-time cost too"
             if n0 == 0 else ""))
    blocks, n, m = [], n0, used_bytes()
    for b in range(BLOCKS):
        for i in range(b * BLOCK, (b + 1) * BLOCK):
            agent.ask_locally(f"{ANSWERING[i % len(ANSWERING)]} (variant {i})")
        n2, m2 = count(), used_bytes()
        blocks.append((n2 - n, m2 - m))
        n, m = n2, m2

    added = sum(a for a, _ in blocks)
    want = BLOCKS * BLOCK
    if added < want * 0.8:
        print(f"  FAIL  recorded {added} answers, expected about {want} -- these questions "
              f"stopped answering, so the measurement is of nothing")
        return 1

    print(f"\n    {'block':<9}{'answers':>9}{'growth':>12}{'KB/answer':>12}")
    for i, (a, d) in enumerate(blocks, 1):
        print(f"    {i:<9}{a:>9}{d / 1024:>10.0f} KB{d / 1024 / max(1, a):>12.2f}")

    first, last = blocks[0], blocks[-1]
    marginal = last[1] / 1024 / max(1, last[0])

    # Whether the instrument can be trusted AT ALL in this instance, asked before anything is
    # reported from it. `used_memory` is instance-wide, so once rows have been deleted the
    # allocator hands their arena space back to the next insert and the delta understates by
    # whatever it reuses. Run this twice in a row and the second run measures a first block at
    # -0.1 KB an answer: memory apparently fell while 200 rows were added.
    #
    # That is not evidence against the published figure, so it must not be reported as a failure.
    # A check that goes red for a reason unrelated to its claim teaches you to ignore it, which
    # costs more than the check was ever worth. It says what it needs instead.
    if first[1] <= 0 or marginal <= 0.5:
        print(f"\n  note  this database cannot be measured: the first block grew "
              f"{first[1] / 1024:.0f} KB for {first[0]} answers. used_memory is instance-wide, so "
              f"a database that has had answers deleted reuses their space and the delta "
              f"understates.")
        print("        For a figure worth publishing, restart FalkorDB and seed it fresh:")
        print("          docker restart falkordb && ./run.sh")
        print("        Nothing here contradicts the README; the instrument is simply blind in "
              "this instance.")
        return 0
    if last[1] < 50_000:
        print(f"  FAIL  the last block grew {last[1]} bytes, which is inside allocator noise; "
              f"raise BLOCK rather than report a per-answer figure from it")
        return 1

    # The distinction this benchmark exists to make. The published figure used to be the FIRST
    # block's average -- about 12 KB -- multiplied by ten thousand. From an empty memory that
    # block pays roughly 1.4 MB of one-time structure for the vector index, so its average is a
    # first-batch cost masquerading as a marginal rate, and the projection it fed was ~3x high.
    one_off = (first[1] - last[1] * first[0] / max(1, last[0])) / 1048576
    print(f"\n  ~{marginal:.1f} KB per stored answer, marginal, from the last block")
    print(f"  the first block averaged {first[1] / 1024 / max(1, first[0]):.1f} KB/answer"
          + (f", about {one_off:.1f} MB of which is one-time structure"
             if one_off > 0.2 else ""))
    print("  Most of each answer is the 384-dimension embedding, a native Vectorf32 at 1,536 B.")

    for n_q in (1_000, 10_000):
        mb = marginal * n_q / 1024 + max(0.0, one_off)
        print(f"  {n_q:>6,} distinct answered questions -> ~{mb:.0f} MB on top of the "
              f"{BASELINE_MB} MB baseline = {BASELINE_MB + mb:.0f} MB "
              f"({'inside' if BASELINE_MB + mb < CEILING_MB else 'OVER'} the "
              f"{CEILING_MB} MB serial ceiling)")

    # Reconciled against the page, because the lesson from bench_vs_networkx.py is that a figure
    # printed here and compared to nothing drifts off the README silently.
    import re
    try:
        readme = open("README.md", encoding="utf-8").read()
    except OSError:
        return 0
    said = re.search(r"\*\*about ([\d.]+) KB each, marginal\*\*", " ".join(readme.split()))
    if not said:
        print("\n  FAIL  README.md no longer states a marginal per-answer figure to check "
              "against; it must say '**about N KB each, marginal**'")
        return 1
    claimed = float(said.group(1))
    # A FACTOR of two, not a percentage. Trustworthy runs of this gave 2.7, 3.0 and 3.6 KB, so a
    # tolerance tight enough to separate those would eventually go red over a figure that was
    # never wrong -- and the projection it feeds has 30-plus MB of headroom either way. What this
    # is for is catching the drift that matters: the published number was 12 KB, a first-batch
    # average mistaken for a marginal rate, and a factor-of-two bound catches that while leaving
    # the run-to-run spread alone.
    near = 0.5 * claimed <= marginal <= 2.0 * claimed
    print(f"\n  {'ok  ' if near else 'FAIL'}  this run {marginal:.1f} KB marginal, the README "
          f"says about {claimed} KB"
          + ("" if near else "  <- outside, re-measure before trusting either"))
    if not near:
        return 1

    # Cleanup lives in main()'s finally. Only the rows this run created are removed -- matched by
    # the "(variant N)" suffix it writes -- because a benchmark that wipes a developer's or a
    # judge's accumulated memory to measure something is a worse neighbour than one that is
    # never run.
    print("\n  Reported, not gated: this is a dated measurement on one machine, like the other")
    print("  benchmarks here. `./run.sh --forget` clears everything, not just this.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
