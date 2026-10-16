"""A small, honest retrieval eval for `has_this_been_tried`.

Not a benchmark. Twelve paraphrases a Kubernetes contributor might plausibly type, each written
WITHOUT looking at the corpus first, scored on whether the top hit is a real titled rejected option
with a substantive recorded rationale at a usable distance.

Run: PYTHONPATH=src python eval_retrieval.py
"""
import sys

sys.path.insert(0, "src")
from tombstone.agent import Agent

# Written as a contributor would phrase them, not reverse-engineered from the data.
QUERIES = [
    "let the kubelet manage this state itself instead of the API server",
    "just use a CRD instead of adding a built-in API type",
    "make it opt-in with a feature gate rather than changing the default",
    "store this in etcd directly",
    "add a new field to the Pod spec",
    "use an annotation instead of a first-class field",
    "handle this in the scheduler rather than the kubelet",
    "expose it as a new CRI method",
    "use a webhook for validation",
    "put the logic in a separate controller",
    "reuse the existing taints and tolerations mechanism",
    "make it a separate out-of-tree component",
]

# A control: things this corpus genuinely should not know about. A retrieval layer that never
# returns nothing is not telling you anything.
CONTROLS = [
    "rewrite the control plane in COBOL on a mainframe",
    "replace the scheduler with a reinforcement learning agent trained on chess",
    "migrate all state to a blockchain",
]

MAX_DIST = 0.33
MIN_RATIONALE = 120


def main() -> int:
    a = Agent(graph_name="tomb:k8s", now_ms=1_760_000_000_000)
    print(f"{'query':<54}{'dist':>7}   top rejected option")
    print("-" * 132)
    hits = 0
    for q in QUERIES:
        ans = a.dispatch("has_this_been_tried", {"idea_text": q})
        if ans.shape != "ANSWERED_WITH_PATH" or not ans.rows:
            print(f"  {q[:52]:<52}{'--':>7}   (nothing returned)")
            continue
        idea, rationale, kep, *_rest = ans.rows[0]
        dist = ans.rows[0][-1]
        ok = dist < MAX_DIST and len(str(rationale)) > MIN_RATIONALE
        hits += ok
        print(f"{'  ' if ok else '?!'}{q[:52]:<52}{dist:>7}   KEP-{kep:<6}{str(idea)[:52]}")

    print("-" * 132)
    print(f"useful top hits: {hits}/{len(QUERIES)}")

    print(f"\ncontrols (should return NOTHING at max_dist=0.15):")
    clean = 0
    for q in CONTROLS:
        ans = a.dispatch("has_this_been_tried", {"idea_text": q, "max_dist": 0.15})
        ok = ans.shape == "NOT_IN_GRAPH"
        clean += ok
        print(f"  {'PASS' if ok else 'FAIL'}  {q[:70]:<72} -> {ans.shape}")
    print(f"\ncontrols correctly empty: {clean}/{len(CONTROLS)}")

    # The README prints both of these scores. Until now nothing connected those sentences to this
    # run, which is how every other number in this repository has gone stale -- and this one had a
    # live reason to move today: has_this_been_tried started excluding seven section headings from
    # the haystack, so both scores were worth re-reading rather than assuming.
    import re as _re
    readme = open("README.md").read()
    drift = []
    m = _re.search(r"\*\*(\d+)/(\d+) return a real titled rejected option", readme)
    if not m:
        drift.append("the README no longer states the paraphrase score where this can read it")
    elif (int(m.group(1)), int(m.group(2))) != (hits, len(QUERIES)):
        drift.append(f"the README says {m.group(1)}/{m.group(2)} useful top hits; "
                     f"this run measured {hits}/{len(QUERIES)}")
    m2 = _re.search(r"(\d+) negative controls?", readme)
    if m2 and int(m2.group(1)) != len(CONTROLS):
        drift.append(f"the README says {m2.group(1)} negative controls; this file has "
                     f"{len(CONTROLS)}")
    for d in drift:
        print(f"  FAIL  {d}")

    return 0 if (hits == len(QUERIES) and clean == len(CONTROLS) and not drift) else 1


if __name__ == "__main__":
    sys.exit(main())
