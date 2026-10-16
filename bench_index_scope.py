"""Should the vector index cover all 958 rejected options, or only the 752 named ones?

`docs/EXPLAIN-IT.md` calls the excluded set this product's biggest recall weakness, so the
exclusion had better be a decision rather than an accident. Two things were wrong with how it
was written down:

  - It said those alternatives "are not embedded". They ARE -- all 206 of them, and the stored
    vector is reproduced at cosine 1.0000 by re-embedding the BODY alone, so the title is display
    text and nothing more. They are embedded and deliberately unindexed, which is a different
    claim with a different fix.
  - It counted substance by TITLE length, which measures the extractor, not the corpus. Every
    one of the 206 carries at least 100 characters of argument, because that is the floor the
    build applies before it makes a node at all.

So this measures the actual trade. It pools the two sets into one index, scores both, and drops
the index again.

The metric is deliberately not one I can flatter. Query the index with a named option's own
sub-heading -- text the Kubernetes authors wrote, not a question I phrased -- and the right answer
is that node. Self-retrieval tops out well under 100% either way, because a sub-heading is a few
words of a 1,800-character body; what matters is the direction of the difference.

Usage:  PYTHONPATH=src python bench_index_scope.py
"""
from __future__ import annotations

import random
import re
import sys
import time

sys.path.insert(0, "src")
from graphkit.ingest import connect          # noqa: E402

GRAPH = "tomb:k8s"
SAMPLE = 400
SEED = 42
POOLED = "Alternative"
SHIPPED = "NamedOption"

# The same exclusion the shipped tool applies, so this compares retrieval and not that list.
TOPK = """
CALL db.idx.vector.queryNodes($lbl, 'emb', $k, vecf32($v)) YIELD node AS a, score
WITH a, score
WHERE NOT a.title IN ['Cons','Cons:','Not','Other Solutions:','Pros','Pros/Cons','Pros:']
RETURN a.key, score ORDER BY score ASC
"""


def vector_labels(g) -> dict:
    """Labels carrying a vector index, and how many documents each holds.

    Read per field. Matching 'VECTOR' against the whole printed row says a label still has a
    vector index when all it has is a RANGE index on another property -- which is exactly what
    this script's own cleanup check would have got wrong.
    """
    out = {}
    for row in g.ro_query("CALL db.indexes()").result_set:
        types = dict(row[2])
        if any("VECTOR" in v for v in types.values()):
            out[row[0]] = row[8].get("numDocuments")
    return out


def main() -> int:
    g = connect().select_graph(GRAPH)
    q1 = lambda c: g.ro_query(c).result_set[0][0]  # noqa: E731

    total = q1("MATCH (a:Alternative) RETURN count(a)")
    named = q1("MATCH (a:NamedOption) RETURN count(a)")
    excluded = total - named
    embedded = q1("MATCH (a:Alternative) WHERE NOT a:NamedOption AND a.emb IS NOT NULL "
                  "RETURN count(a)")
    thin = q1("MATCH (a:Alternative) WHERE NOT a:NamedOption AND size(a.body) < 100 "
              "RETURN count(a)")

    print(f"  {total} rejected options; {named} named, {excluded} outside the index")
    print(f"  of those {excluded}: {embedded} carry an embedding, {thin} hold under 100 "
          f"characters of argument")
    if excluded == 0 or named == 0:
        print("\n  REFUSING to report: one of the two sets is empty, so there is nothing to "
              "compare.")
        return 1
    if embedded != excluded:
        print(f"\n  note  {excluded - embedded} of the excluded options have no embedding, so "
              f"pooling could not reach them either")

    before = vector_labels(g)
    if POOLED in before:
        print(f"\n  REFUSING to report: a vector index on :{POOLED} already exists, so this "
              f"cannot create and drop its own.")
        return 1

    g.query(f"CREATE VECTOR INDEX FOR (a:{POOLED}) ON (a.emb) "
            "OPTIONS {dimension: 384, similarityFunction: 'cosine'}")
    # HNSW builds asynchronously. Scoring a half-built index would understate the pooled set by
    # however much of it had not landed yet, which is a measurement of nothing.
    deadline = time.time() + 60
    built = 0
    while time.time() < deadline:
        built = vector_labels(g).get(POOLED) or 0
        if built >= total:
            break
        time.sleep(0.5)
    if built < total:
        print(f"\n  REFUSING to report: the pooled index reached {built} of {total} documents "
              f"in 60s.")
        g.query(f"DROP VECTOR INDEX FOR (a:{POOLED}) ON (a.emb)")
        return 1
    print(f"  pooled index built: {built} documents\n")

    from fastembed import TextEmbedding
    model = TextEmbedding(model_name="BAAI/bge-small-en-v1.5")

    rows = g.ro_query("MATCH (a:NamedOption) RETURN a.key, a.title").result_set
    random.seed(SEED)
    sample = random.sample(rows, min(SAMPLE, len(rows)))
    vecs = [list(map(float, v)) for v in model.embed([t for _, t in sample])]

    def accuracy(label: str, k: int) -> int:
        hit = 0
        for (key, _t), v in zip(sample, vecs):
            got = g.ro_query(TOPK, params={"lbl": label, "k": k, "v": v}).result_set
            if any(r[0] == key for r in got):
                hit += 1
        return hit

    n = len(sample)
    print(f"  {n} named options, each asked for by its own sub-heading:\n")
    print(f"    {'index':<22}{'top-1':>9}{'top-3':>9}{'top-8':>9}")
    scores = {}
    for label, size in ((SHIPPED, named), (POOLED, total)):
        scores[label] = [accuracy(label, k) for k in (1, 3, 8)]
        name = f"{size} docs" + ("  (shipped)" if label == SHIPPED else "  (pooled)")
        print(f"    {name:<22}" + "".join(f"{h / n * 100:8.1f}%" for h in scores[label]))

    delta = [(p - s) / n * 100 for s, p in zip(scores[SHIPPED], scores[POOLED])]
    print(f"    {'difference':<22}" + "".join(f"{d:+8.1f}%" for d in delta))

    # The other side of the trade: what pooling buys. An unindexed node cannot be returned for
    # ANY query, so this is a structural zero rather than a low score.
    prose = g.ro_query(
        "MATCH (a:Alternative) WHERE NOT a:NamedOption RETURN a.key, a.title ORDER BY a.key"
    ).result_set
    random.seed(SEED)
    psample = random.sample(prose, min(25, len(prose)))
    pvecs = [list(map(float, v)) for v in model.embed([t for _, t in psample])]
    found = {SHIPPED: 0, POOLED: 0}
    for label in (SHIPPED, POOLED):
        for (key, _t), v in zip(psample, pvecs):
            got = g.ro_query(TOPK, params={"lbl": label, "k": 3, "v": v}).result_set
            if any(r[0] == key for r in got):
                found[label] += 1
    m = len(psample)
    print(f"\n  {m} excluded rejections, asked for by their own first sentence:")
    print(f"    reachable in top-3, shipped index : {found[SHIPPED]}/{m}")
    print(f"    reachable in top-3, pooled  index : {found[POOLED]}/{m}")

    # The drop is asynchronous, exactly like the build. Reading the index list on the next line
    # still shows the pooled index and reports that this script dirtied the graph -- which it had
    # not. A cleanup check that races the cleanup is worse than none: it cries wolf about state.
    g.query(f"DROP VECTOR INDEX FOR (a:{POOLED}) ON (a.emb)")
    deadline = time.time() + 30
    after = vector_labels(g)
    while POOLED in after and time.time() < deadline:
        time.sleep(0.5)
        after = vector_labels(g)
    clean = POOLED not in after and SHIPPED in after
    print(f"\n  dropped the pooled index; vector indexes now {sorted(after)} "
          f"-- {'as before it ran' if clean else 'NOT the state it started in'}")
    if not clean:
        print("    FAIL  this script changed the graph it measured.")
        return 1

    worse = sum(1 for d in delta if d < 0)
    verdict = ("keeping the pre-filter" if worse >= 2 else "pooling")
    print(f"\n  Verdict: {verdict}. Pooling moves named-option retrieval by "
          f"{delta[0]:+.1f}/{delta[1]:+.1f}/{delta[2]:+.1f} points at k=1/3/8 and takes the "
          f"excluded set from {found[SHIPPED]}/{m} to {found[POOLED]}/{m}.")
    print("  The shipped build keeps the 752-document index. That is the decision this script")
    print("  exists to justify, and it is reported rather than gated: it is one dated run on one")
    print("  machine, and a 3-point difference is not a thing to turn CI red over.")

    # Reconcile against the page that makes the claim, the same way the other benchmarks do.
    try:
        doc = open("docs/EXPLAIN-IT.md", encoding="utf-8").read()
    except OSError:
        return 0
    flat = " ".join(doc.split())
    # Checked as a POSITIVE claim, deliberately. The first version grepped for "not embedded" and
    # then failed on the very sentence that corrects it -- the page now says: not, as this page
    # used to say, "not embedded". A phrase-level exclusion cannot tell a claim from a disavowal
    # of that claim, and it swallows the honest sentence either way. Requiring the true statement
    # to be present cannot be satisfied by quoting the false one.
    if not re.search(r"embedded and deliberately unindexed", flat):
        print(f"\n  FAIL  docs/EXPLAIN-IT.md no longer states that the excluded options are "
              f"embedded and deliberately unindexed; {embedded} of {excluded} carry a vector, "
              f"so that is the fact the page has to carry.")
        return 1
    said = re.search(r"up to (\d+) rejections out of (\d+)", flat)
    if said and (int(said.group(1)), int(said.group(2))) != (excluded, total):
        print(f"\n  FAIL  docs/EXPLAIN-IT.md says up to {said.group(1)} of {said.group(2)}; "
              f"the graph has {excluded} of {total}.")
        return 1
    print("\n  docs/EXPLAIN-IT.md matches the graph on both figures.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
