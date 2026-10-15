"""Test this product's own premise, and report the answer even when it is unwelcome.

The README opens by saying large orgs keep re-proposing things they already rejected. That is the
motivation for the whole product, and I had never measured it. So: can a previously-rejected
alternative be shown to have been independently re-proposed and re-rejected somewhere else in
Kubernetes' record?

Method. Every named rejected alternative carries a local embedding. Compare all of them pairwise,
keep pairs that belong to DIFFERENT decisions, and ask whether the record already links those two
decisions through `REPLACES`, `SUPERSEDED_BY` or `SEE_ALSO`. A linked pair is not a re-proposal:
it is a successor KEP carrying its predecessor's Alternatives section forward, which is exactly
what should happen and which the record already captures.

The answer this returns on the current corpus is NO -- every near-identical cross-decision pair is
already linked. The band below near-identical holds topical neighbours ("add pod index as a label"
beside "generic managed-by"), which are different ideas in similar vocabulary, and counting those
would be the same overclaim this product exists to avoid.

That result is in the README. A premise that cannot be demonstrated should be labelled, not
quietly left standing.
"""
from __future__ import annotations

import sys

import numpy as np

sys.path.insert(0, "src")
from graphkit.ingest import connect          # noqa: E402
from tombstone.snapshot import load_vectors  # noqa: E402

IDENTICAL = 0.95     # at or above this, the text is effectively the same alternative
ADJACENT = 0.86      # between the two, ideas are merely topically near each other
GRAPH = "tomb:k8s"


def main() -> int:
    a, b = load_vectors()
    keys, vecs = (a, b) if isinstance(a[0], str) else (b, a)
    g = connect().select_graph(GRAPH)
    owner = {r[0]: (r[1], r[2]) for r in g.ro_query(
        "MATCH (k:Kep)-[:CONSIDERED]->(a:NamedOption) RETURN a.key, k.key, a.title").result_set}

    keep = [i for i, k in enumerate(keys) if k in owner]
    V = np.asarray(vecs, dtype=np.float32)[keep]
    K = [keys[i] for i in keep]
    V /= np.linalg.norm(V, axis=1, keepdims=True) + 1e-9
    S = V @ V.T
    np.fill_diagonal(S, -1.0)

    linked = {frozenset(r) for r in g.ro_query(
        "MATCH (x:Kep)-[:REPLACES|SUPERSEDED_BY|SEE_ALSO]-(y:Kep) RETURN x.key, y.key").result_set}

    pairs, adjacent = {}, 0
    for i in range(len(K)):
        for j in range(i + 1, len(K)):
            ka, kb = owner[K[i]][0], owner[K[j]][0]
            if ka == kb:
                continue
            s = float(S[i, j])
            if s >= IDENTICAL:
                pairs.setdefault(frozenset((ka, kb)), []).append(owner[K[i]][1])
            elif s >= ADJACENT:
                adjacent += 1

    print(f"named rejected alternatives compared : {len(K)}")
    print(f"decisions with a recorded relationship: {len(linked)}")
    print(f"\ncross-decision pairs sharing a near-identical alternative (cos >= {IDENTICAL}): "
          f"{len(pairs)}")

    unexplained = 0
    for pair, alts in sorted(pairs.items(), key=lambda kv: -len(kv[1])):
        ka, kb = sorted(pair)
        known = pair in linked
        unexplained += not known
        print(f"  [{'already linked' if known else 'NOT LINKED'}] {len(alts)} shared")
        print(f"      {ka}")
        print(f"      {kb}")

    print(f"\ntopically adjacent pairs ({ADJACENT} <= cos < {IDENTICAL}): {adjacent}, "
          f"NOT counted — different ideas in similar vocabulary")
    print(f"\nre-proposals this corpus can demonstrate: {unexplained}")

    # The README states these numbers, so they are checked rather than trusted, the same way
    # verify_claims.py checks the graph counts. If a real re-proposal ever appears, this fails
    # loudly and the README gets a better story than the one it has now.
    expected = {"near_identical_pairs": 3, "unexplained": 0, "adjacent": 31}
    got = {"near_identical_pairs": len(pairs), "unexplained": unexplained, "adjacent": adjacent}
    if got != expected:
        print(f"\nREADME says {expected}, measurement says {got}", file=sys.stderr)
        return 1
    if unexplained == 0:
        print("\nThe premise is not demonstrated here. Every near-identical pair is a successor\n"
              "carrying its predecessor's alternatives forward, and the record already links them.\n"
              "What the product does is make a rejected alternative RETRIEVABLE, so the question\n"
              "can be asked at all. That it finds no silent repeats is a result, not a failure.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
