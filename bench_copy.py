"""Re-measure `GRAPH.COPY`, and check the copy is actually a copy.

This repo quoted three different figures for the same operation: 495 ms in `counterfactual.py`,
~390 ms in the README, and a reality of about 323 ms. None had been re-measured in a long time,
and the node, edge and index counts beside them were wrong too -- the index count had been read
off a graph that had been USED, because remembering an answer adds an eighth index on
`:Answer{qid, emb}`.

Timing is hardware-dependent, so this asserts CORRECTNESS and reports the time rather than
pinning a millisecond figure that would be wrong on anyone else's machine. What it asserts is the
claim that actually matters: the copy carries the whole graph and its indexes, and the original is
untouched.
"""
from __future__ import annotations

import sys
import time

sys.path.insert(0, "src")
from graphkit.ingest import connect          # noqa: E402
from tombstone.build import build            # noqa: E402
from tombstone.snapshot import load          # noqa: E402

SOURCE = "tomb:copybench"
RUNS = 5


def shape(g) -> tuple[int, int, int]:
    nodes = g.ro_query("MATCH (n) RETURN count(n)").result_set[0][0]
    edges = g.ro_query("MATCH ()-[r]->() RETURN count(r)").result_set[0][0]
    idx = g.ro_query("CALL db.indexes() YIELD label RETURN count(label)").result_set[0][0]
    return nodes, edges, idx


db = connect()
for name in (SOURCE,):
    try:
        db.select_graph(name).delete()
    except Exception:
        pass

build(load(), graph_name=SOURCE)
src = db.select_graph(SOURCE)
before = shape(src)
print(f"  seeded source: {before[0]:,} nodes, {before[1]:,} edges, {before[2]} indexes")

fails, times = 0, []
for i in range(RUNS):
    dst = f"{SOURCE}:copy{i}"
    t0 = time.perf_counter()
    db.connection.execute_command("GRAPH.COPY", SOURCE, dst)
    times.append((time.perf_counter() - t0) * 1000)
    copied = shape(db.select_graph(dst))
    if copied != before:
        print(f"  FAIL  copy {i} is {copied}, source is {before}")
        fails += 1
    db.select_graph(dst).delete()

if shape(src) != before:
    print("  FAIL  the SOURCE graph changed while being copied")
    fails += 1

times.sort()
print(f"  {RUNS} copies: {[round(t) for t in times]} ms  "
      f"(median {round(times[len(times) // 2])} ms)")
print(f"  {'FAIL' if fails else 'PASS'}  every copy carried the full graph and its indexes, "
      f"and the original was untouched")
db.select_graph(SOURCE).delete()
sys.exit(1 if fails else 0)
