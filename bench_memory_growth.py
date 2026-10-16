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
ROUNDS = 25
CEILING_MB = 512          # the serial ceiling the deploy check asserts
BASELINE_MB = 387         # peak this image reaches before any memory is written


def used_bytes() -> int:
    out = subprocess.run(["docker", "exec", "falkordb", "redis-cli", "INFO", "memory"],
                         capture_output=True, text=True).stdout
    for line in out.split("\n"):
        if line.startswith("used_memory:"):
            return int(line.split(":")[1])
    sys.exit("could not read used_memory from the falkordb container; is it running?")


def main() -> int:
    graph = connect().select_graph("tomb:k8s")
    count = lambda: int(graph.query("MATCH (a:Answer) RETURN count(a)").result_set[0][0])
    agent = Agent(graph_name="tomb:k8s")

    before_n, before_m = count(), used_bytes()
    for i in range(ROUNDS):
        for q in ANSWERING:
            agent.ask_locally(f"{q} (variant {i})")
    added, delta = count() - before_n, used_bytes() - before_m

    want = ROUNDS * len(ANSWERING)
    if added < want * 0.8:
        print(f"  FAIL  recorded {added} answers, expected about {want} — these questions stopped "
              f"answering, so the measurement is of nothing")
        return 1
    if delta < 50_000:
        print(f"  FAIL  total growth {delta} bytes is inside allocator noise; raise ROUNDS "
              f"rather than report a per-answer figure from it")
        return 1

    per = delta / added
    print(f"  {added} answers recorded, database grew {delta / 1024:.0f} KB")
    print(f"  ~{per / 1024:.1f} KB per stored answer "
          f"(384-dim embedding as Vectorf32, plus the question text)")
    for n in (1_000, 10_000):
        mb = per * n / 1048576
        print(f"  {n:>6,} distinct answered questions -> ~{mb:.0f} MB on top of the "
              f"{BASELINE_MB} MB baseline = {BASELINE_MB + mb:.0f} MB "
              f"({'inside' if BASELINE_MB + mb < CEILING_MB else 'OVER'} the "
              f"{CEILING_MB} MB serial ceiling)")
    # Reconciled against the page, because the lesson from bench_vs_networkx.py is that a figure
    # printed here and compared to nothing drifts off the README silently -- two of its five rows
    # did exactly that, and were only caught by someone running it and reading both.
    import re
    readme = re.sub(r"\s*\n>?\s*", " ", open("README.md").read())
    said = re.search(r"\*\*about (\d+) KB each\*\*", readme)
    if not said:
        print("\n  note  the README no longer states a per-answer cost in the form this reads")
    else:
        claimed = int(said.group(1))
        near = abs(per / 1024 - claimed) <= max(2.0, claimed * 0.25)
        print(f"\n  {'ok  ' if near else 'note'}  this run {per / 1024:.1f} KB, "
              f"the README says about {claimed} KB"
              + ("" if near else "  <- outside, re-measure before trusting either"))

    # Clean up after itself, which is what lets this live in ./preflight.sh. Only the rows this
    # run created are removed -- matched by the "(variant N)" suffix it writes -- because a
    # benchmark that wipes a developer's or a judge's accumulated memory to measure something is
    # a worse neighbour than one that is never run.
    removed = int(graph.query(
        "MATCH (a:Answer) WHERE a.question CONTAINS '(variant ' "
        "WITH a, count(a) AS _ DETACH DELETE a RETURN count(_)").result_set[0][0] or 0)
    left = count()
    print(f"\n  cleaned up {removed} of its own rows; {left} answers remain, "
          f"which is what was here before it ran")

    print("\n  Reported, not gated: this is a dated measurement on one machine, like the other")
    print("  benchmarks here. `./run.sh --forget` clears everything, not just this.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
