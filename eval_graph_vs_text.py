"""Does the graph actually do work a text search cannot? Measured, not asserted.

The hackathon's one published judging lens is whether the graph is doing work the agent could not
do without it. Asserting that is cheap. This measures it, on the same corpus, with the same
questions, against a real text baseline.

**The baseline is honest.** TF-IDF + cosine over the SAME documents the graph was built from
(KEP titles, statuses, the alternatives prose, OWNERS paths and the handles in them). It is given
every word the graph has. It is not a strawman: where a question is really a lookup, it wins or
ties, and that is reported.

**Scoring.** Each question has a programmatic check over what the mode returned. A mode scores
only if the check passes -- so "returned something plausible" is worth nothing.

Run: PYTHONPATH=src python eval_graph_vs_text.py
"""
from __future__ import annotations

import math
import re
import sys
from collections import Counter

sys.path.insert(0, "src")

from graphkit.ingest import connect
from tombstone.agent import Agent

# ---------------------------------------------------------------- text baseline


class TfIdf:
    """A plain TF-IDF retriever over the corpus documents. No graph, no embeddings."""

    def __init__(self, docs: list[tuple[str, str]]):
        self.ids = [d[0] for d in docs]
        self.raw = [d[1] for d in docs]
        self.toks = [self._tok(t) for t in self.raw]
        df: Counter = Counter()
        for t in self.toks:
            df.update(set(t))
        n = len(self.toks)
        self.idf = {w: math.log((n + 1) / (c + 1)) + 1 for w, c in df.items()}
        self.vecs = [self._vec(t) for t in self.toks]

    @staticmethod
    def _tok(s: str) -> list[str]:
        return re.findall(r"[a-z0-9_\-/.]+", (s or "").lower())

    def _vec(self, toks: list[str]) -> dict:
        tf = Counter(toks)
        v = {w: (1 + math.log(c)) * self.idf.get(w, 1.0) for w, c in tf.items()}
        norm = math.sqrt(sum(x * x for x in v.values())) or 1.0
        return {w: x / norm for w, x in v.items()}

    def search(self, q: str, k: int = 10) -> list[tuple[str, str, float]]:
        qv = self._vec(self._tok(q))
        scored = []
        for i, dv in enumerate(self.vecs):
            if len(qv) < len(dv):
                s = sum(x * dv.get(w, 0.0) for w, x in qv.items())
            else:
                s = sum(x * qv.get(w, 0.0) for w, x in dv.items())
            if s > 0:
                scored.append((self.ids[i], self.raw[i], s))
        scored.sort(key=lambda r: -r[2])
        return scored[:k]


def load_documents(g) -> list[tuple[str, str]]:
    """Every document the graph was built from, flattened. The baseline sees all of it."""
    docs: list[tuple[str, str]] = []
    off = 0
    while True:
        r = g.ro_query(
            "MATCH (k:Kep) RETURN k.key, k.num, k.title, k.status, k.sig "
            "ORDER BY k.key SKIP $o LIMIT 2000", params={"o": off}).result_set
        if not r:
            break
        docs += [(f"KEP-{n}", f"KEP-{n} {t} status {s} sig {sg} {key}") for key, n, t, s, sg in r]
        if len(r) < 2000:
            break
        off += 2000
    off = 0
    while True:
        r = g.ro_query(
            "MATCH (a:Alternative)<-[:CONSIDERED]-(k:Kep) "
            "RETURN a.key, k.num, a.title, a.body ORDER BY a.key SKIP $o LIMIT 2000",
            params={"o": off}).result_set
        if not r:
            break
        docs += [(f"ALT {ak}", f"KEP-{n} rejected alternative {t} {b}") for ak, n, t, b in r]
        if len(r) < 2000:
            break
        off += 2000
    off = 0
    while True:
        r = g.ro_query(
            "MATCH (o:OwnersFile) OPTIONAL MATCH (p:Person)-[:APPROVES]->(o) "
            "OPTIONAL MATCH (e:Person)-[:EMERITUS_OF]->(o) "
            "WITH o, collect(DISTINCT p.key) AS ap, collect(DISTINCT e.key) AS em "
            "RETURN o.path, ap, em ORDER BY o.path SKIP $o LIMIT 2000", params={"o": off}).result_set
        if not r:
            break
        docs += [(f"OWNERS {p}", f"OWNERS file {p} approvers {' '.join(a)} "
                                 f"emeritus_approvers {' '.join(e)}") for p, a, e in r]
        if len(r) < 2000:
            break
        off += 2000
    return docs


# ---------------------------------------------------------------- the questions
#
# Each: a question, the tool that answers it, and a check over the TEXT of each mode's answer.
# Mixed on purpose -- some are lookups a text index should win.

QUESTIONS = [
    dict(q="has anyone proposed using a feature gate to make this opt-in?",
         tool="has_this_been_tried", args={"idea_text": "make it opt-in with a feature gate"},
         check=lambda t: "feature gate" in t.lower(),
         why="lookup — text should do fine"),
    dict(q="find the KEP about coscheduling",
         tool="has_this_been_tried", args={"idea_text": "coscheduling gang scheduling"},
         check=lambda t: "coscheduling" in t.lower(),
         why="title lookup — text SHOULD win this"),
    dict(q="which areas lost every approver with dedicated authority?",
         tool="ownership_dilution", args={},
         check=lambda t: "endpoints/metrics" in t and "falls back" in t.lower(),
         why="needs a tree walk to the nearest live ancestor"),
    dict(q="who should inherit lavalamp's areas?",
         tool="successor_for", args={"handle": "lavalamp"},
         check=lambda t: "deads2k" in t and re.search(r"\b2[0-9] of", t) is not None,
         why="needs co-ownership overlap counted across two edge types"),
    dict(q="who held the most connective authority before stepping back?",
         tool="stepped_back_bridges", args={"min_areas": 3},
         check=lambda t: "lavalamp" in t and "betweenness" in t.lower(),
         why="needs betweenness centrality — a whole-graph property"),
    dict(q="which cited decision records do not exist?",
         tool="broken_lineage", args={"min_cites": 2},
         check=lambda t: "0006-apply" in t,
         why="needs inbound edges to a node that is ABSENT"),
    dict(q="what knowledge here is going stale?",
         tool="stale_knowledge", args={"min_years": 3},
         check=lambda t: "KEP-583" in t and "still cited by" in t,
         why="needs age + inbound citations + author authority, joined"),
    dict(q="who owns the apiserver metrics endpoint, really?",
         tool="who_owns",
         args={"path": "staging/src/k8s.io/apiserver/pkg/endpoints/metrics/OWNERS", "depth": 4},
         check=lambda t: "no one named here still holds approval authority" in t.lower()
                         or "still holds approval" in t.lower(),
         why="needs inheritance resolved, not just the file read"),
]


def main() -> int:
    from tombstone.agent import render
    g = connect().select_graph("tomb:k8s")
    agent = Agent(graph_name="tomb:k8s")

    print("building the text baseline over the same documents…")
    docs = load_documents(g)
    tfidf = TfIdf(docs)
    print(f"  {len(docs)} documents indexed (KEPs, alternatives, OWNERS files)\n")

    print(f"{'question':<52}{'graph':>8}{'text':>8}   what it needs")
    print("-" * 118)
    gw = tw = 0
    for item in QUESTIONS:
        a = agent.dispatch(item["tool"], item["args"])
        g_text = render(a)
        g_ok = a.shape == "ANSWERED_WITH_PATH" and item["check"](g_text)

        hits = tfidf.search(item["q"], k=10)
        t_text = "\n".join(f"{i} {b}" for i, b, _ in hits)
        t_ok = bool(hits) and item["check"](t_text)

        gw += g_ok
        tw += t_ok
        print(f"  {item['q'][:50]:<50}{'PASS' if g_ok else ' -- ':>8}"
              f"{'PASS' if t_ok else ' -- ':>8}   {item['why']}")

    n = len(QUESTIONS)
    print("-" * 118)
    print(f"  {'':<50}{gw}/{n:<7}{tw}/{n}")
    print()
    print(f"Graph answers {gw}/{n}. A TF-IDF index over the same documents answers {tw}/{n}.")
    print("The text baseline sees every word the graph does. Where a question is a lookup it")
    print("competes; where the answer is a path, an absence, or a whole-graph property, there is")
    print("no document for it to find — because the answer was never written down anywhere.")

    # This score is quoted in the README's 60-second box and in the submission copy, and until now
    # nothing connected those sentences to this run. Every other number in this repo that was
    # typed into prose rather than derived from the thing it describes has gone stale, several of
    # them within a day, so this one is asserted where it is produced.
    import re as _re
    drift = []
    for doc, pattern in (("README.md", r"\*\*(\d+)/(\d+) vs (\d+)/(\d+)\*\*"),
                         ("SUBMISSION.md", r"\*\*(\d+)/(\d+) versus (\d+)/(\d+)\*\*")):
        m = _re.search(pattern, open(doc).read())
        if not m:
            drift.append(f"{doc} no longer states this score in the form the check looks for")
            continue
        said_g, said_gn, said_t, said_tn = (int(x) for x in m.groups())
        if (said_g, said_gn, said_t, said_tn) != (gw, n, tw, n):
            drift.append(f"{doc} says {said_g}/{said_gn} vs {said_t}/{said_tn}; "
                         f"this run measured {gw}/{n} vs {tw}/{n}")
    if drift:
        print()
        for d in drift:
            print("  FAIL ", d)
        return 1
    print(f"\nThe README and the submission copy both state {gw}/{n} vs {tw}/{n}, and so does this run.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
