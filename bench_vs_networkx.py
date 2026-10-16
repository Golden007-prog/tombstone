"""Compare FalkorDB against networkx ON THIS PRODUCT'S OWN GRAPH.

The README has carried a networkx comparison for most of this project's life with **no committed
script behind it**, and quoting a graph of "3,300 nodes / 39,987 edges" -- which is not this
product's graph. The real seeded graph is 3,087 nodes and 15,735 edges. For a project whose whole
claim is that its numbers are checkable, that was the weakest paragraph on the page.

So this measures the real thing. The graph is seeded from the committed snapshot, exported to
networkx edge-for-edge, and the same four operations are run on both. networkx is a DEV-only
dependency: it is deliberately not in requirements.txt, because the product does not use it, and
this script says so rather than failing confusingly if it is absent.

The comparison is kept honest in both directions. Betweenness is sampled identically (k=32, fixed
seed) or it is not the same operation. The 2-hop figure is a median over many sources, because a
single source is noise. And the operations networkx wins are reported first.
"""
from __future__ import annotations

import statistics
import sys
import time

sys.path.insert(0, "src")

try:
    import networkx as nx
except ImportError:
    sys.exit("networkx is not installed. It is a dev-only comparison dependency:\n"
             "  pip install networkx scipy\n"
             "The product itself does not use it, which is why it is not in requirements.txt.")

try:
    import scipy  # noqa: F401
except ImportError:
    # Not optional, and not a packaging detail. networkx's PageRank uses a scipy sparse path when
    # scipy is present and a far slower pure-Python one when it is not. Benchmarking against the
    # fallback would be measuring the competitor with a hand tied -- and would flatter FalkorDB by
    # a wide margin on the single row where it already wins by the most. The comparison is only
    # worth publishing if networkx is running at its best.
    sys.exit("scipy is not installed, so networkx would fall back to its slow pure-Python\n"
             "PageRank and this comparison would flatter FalkorDB. Install it:\n"
             "  pip install networkx scipy")

from graphkit.ingest import connect          # noqa: E402
from tombstone.build import build            # noqa: E402
from tombstone.snapshot import load          # noqa: E402

GRAPH = "tomb:nxbench"
SAMPLES = 32
SEED = 42


def ms(fn):
    t0 = time.perf_counter()
    out = fn()
    return (time.perf_counter() - t0) * 1000, out


db = connect()
try:
    db.select_graph(GRAPH).delete()
except Exception:
    pass
build(load(), graph_name=GRAPH)
g = db.select_graph(GRAPH)

nodes = g.ro_query("MATCH (n) RETURN count(n)").result_set[0][0]
edges = g.ro_query("MATCH ()-[r]->() RETURN count(r)").result_set[0][0]
print(f"  the product's own graph: {nodes:,} nodes, {edges:,} edges\n")

pairs = g.ro_query("MATCH (a)-[r]->(b) RETURN id(a), id(b)").result_set

t_build_nx, G = ms(lambda: nx.DiGraph(pairs))
t_build_fdb, _ = ms(lambda: build(load(), graph_name=f"{GRAPH}:rebuild"))
db.select_graph(f"{GRAPH}:rebuild").delete()

t_pr_nx, _ = ms(lambda: nx.pagerank(G))
t_pr_fdb, _ = ms(lambda: g.ro_query("CALL algo.pageRank(NULL, NULL) YIELD node RETURN count(node)"))

t_wcc_nx, nx_components = ms(lambda: list(nx.weakly_connected_components(G)))
# `algo.WCC(NULL, NULL)` -- the two-argument form, by analogy with algo.pageRank(NULL, NULL) --
# silently returns ZERO ROWS on v4.22.1 rather than erroring. A previous benchmark in
# docs/GROUND-TRUTH.md timed that call and published "WCC 4.5ms", which was the cost of computing
# nothing. The no-argument form is the one that works, and the cross-check below is what caught it.
t_wcc_fdb, fdb_wcc = ms(lambda: g.ro_query(
    "CALL algo.WCC() YIELD componentId RETURN count(DISTINCT componentId)"))

# Cross-check that the two are computing the same thing before comparing how fast they do it.
# A benchmark where one engine is quietly solving a different problem is worse than no benchmark.
fdb_components = fdb_wcc.result_set[0][0]
if len(nx_components) != fdb_components:
    print(f"  FAIL  networkx finds {len(nx_components)} weakly-connected components, "
          f"FalkorDB finds {fdb_components} -- they are not computing the same thing")
    sys.exit(1)
print(f"  cross-check: both engines agree on {fdb_components} weakly-connected components\n")


def readme_range(label: str) -> tuple[float, float] | None:
    """The ratio range the README prints for a row, e.g. "FalkorDB 54-145x" -> (54, 145).

    The absolute milliseconds in that table are deliberately NOT asserted: they are a measurement
    on one machine at one moment, and a check that fails because CI runs on slower hardware is a
    check people learn to skip. The RATIO is the claim, and a ratio survives a change of machine
    well enough to be worth holding to.
    """
    import re
    row = re.search(rf"^\|[^|]*{re.escape(label)}[^|]*\|[^|]*\|[^|]*\|([^|]*)\|",
                    open("README.md").read(), re.M)
    if not row:
        return None
    nums = re.findall(r"(\d+(?:\.\d+)?)", row.group(1))
    if not nums:
        return None
    lo = float(nums[0])
    hi = float(nums[1]) if len(nums) > 1 else lo
    return (lo, hi)


t_bc_nx, _ = ms(lambda: nx.betweenness_centrality(G, k=SAMPLES, seed=SEED))
t_bc_fdb, _ = ms(lambda: g.ro_query(
    "CALL algo.betweenness({samplingSize: $k, samplingSeed: $s}) "
    "YIELD node RETURN count(node)", params={"k": SAMPLES, "s": SEED}))

sources = [r[0] for r in g.ro_query("MATCH (n) RETURN id(n) LIMIT 200").result_set]
nx_hops, fdb_hops = [], []
for sid in sources:
    if sid in G:
        t, _ = ms(lambda: set(nx.single_source_shortest_path_length(G, sid, cutoff=2)))
        nx_hops.append(t)
    t, _ = ms(lambda: g.ro_query(
        "MATCH (a)-[*1..2]->(b) WHERE id(a) = $i RETURN count(DISTINCT b)", params={"i": sid}))
    fdb_hops.append(t)

rows = [
    ("build graph", t_build_nx, t_build_fdb),
    ("2-hop neighbourhood (p50)", statistics.median(nx_hops), statistics.median(fdb_hops)),
    ("WCC", t_wcc_nx, t_wcc_fdb),
    (f"betweenness (k={SAMPLES}, seed={SEED})", t_bc_nx, t_bc_fdb),
    ("PageRank", t_pr_nx, t_pr_fdb),
]
print(f"  {'operation':<34}{'networkx':>12}{'FalkorDB':>12}   winner")
print("  " + "-" * 74)
for name, a, b in rows:
    if a < b:
        verdict = f"networkx {b / a:,.0f}x"
    else:
        verdict = f"FalkorDB {a / b:,.0f}x"
    print(f"  {name:<34}{a:>10.1f}ms{b:>10.1f}ms   {verdict}")

db.select_graph(GRAPH).delete()
print("\n  networkx wins in-process pointer chasing; FalkorDB wins the global algorithms.")

# The ratios this run measured, against the ranges the README prints. Absolute milliseconds are
# NOT checked -- they are one machine at one moment. The ratio is the claim, and the ranges are
# wide because re-running widened them: a loaded machine gave PageRank 30x where the page had
# said 54-145x, and that is the page's problem, not the machine's.
_drift = []

def _check_ratio(label: str, measured: float) -> None:
    rng = readme_range(label)
    if rng is None:
        _drift.append(f"the README has no ratio for {label!r}")
        return
    lo, hi = rng
    if not (lo * 0.9 <= measured <= hi * 1.1):
        _drift.append(f"{label}: this run measured {measured:.0f}x, the README prints "
                      f"{lo:g}-{hi:g}x")


_check_ratio("betweenness", max(t_bc_nx, t_bc_fdb) / max(min(t_bc_nx, t_bc_fdb), 1e-9))
_check_ratio("PageRank", max(t_pr_nx, t_pr_fdb) / max(min(t_pr_nx, t_pr_fdb), 1e-9))
_check_ratio("WCC", max(t_wcc_nx, t_wcc_fdb) / max(min(t_wcc_nx, t_wcc_fdb), 1e-9))
if _drift:
    print()
    for _d in _drift:
        print(f"  FAIL  {_d}")
    sys.exit(1)
print("\n  every ratio this run measured falls inside the range the README prints.")
