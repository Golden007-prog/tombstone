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


# The dense baseline's last measured score, so the documents can state it while the cheap
# default run still validates every figure they carry. Without this, a README quoting the dense
# result would read as drift to every run that did not compute it -- and making the default
# compute it anyway would defeat the point of making it opt-in.
#
# It is a published constant, which in this repository means the expensive run re-derives it and
# fails if it has moved. CI runs --dense on every push, so this cannot quietly go stale.
DENSE_LAST_MEASURED = 10


class Dense:
    """The same documents, retrieved by embedding similarity instead of keyword overlap.

    This exists because TF-IDF alone leaves the obvious objection open. "Keyword search loses"
    invites "so use embeddings", and the strongest entries in this field score a dense retriever
    explicitly. The unanswered question was the hole in this measurement, not in the result.

    Same model the product routes with, same documents the TF-IDF index gets, same k, same grader.

    OPT-IN, for a reason worth recording. I first timed `docs[:300]`, got 80 documents a second
    and wrote "about 28 seconds" for all 2,224 -- but those first 300 are KEP title lines
    averaging 127 characters while the corpus averages 434, so the sample was 3.4x cheaper per
    document than the thing it stood for. The real run passed five minutes on a loaded machine.
    Timing an unrepresentative prefix and multiplying is the same error as sampling three tools
    and calling the catalogue checked.

    So ./preflight.sh keeps the cheap comparison and this runs on request (`--dense`, or
    `EVAL_DENSE=1`), which is how CI runs it -- on a GitHub runner rather than on anyone's laptop.
    Embeddings cache under the gitignored `data/raw/`, keyed by the documents themselves so a
    corpus change invalidates them rather than silently scoring last week's text.
    """

    CACHE = "data/raw/eval-dense-vectors.npz"

    def __init__(self, docs: list[tuple[str, str]]):
        import hashlib
        import os

        import numpy as np
        from fastembed import TextEmbedding

        self.ids = [d[0] for d in docs]
        self.raw = [d[1] for d in docs]
        self._model = TextEmbedding(model_name="BAAI/bge-small-en-v1.5")
        self._np = np

        key = hashlib.sha256("\x00".join(self.raw).encode()).hexdigest()[:16]
        mat = None
        if os.path.exists(self.CACHE):
            try:
                z = np.load(self.CACHE)
                if str(z["key"]) == key:
                    mat = z["mat"]
            except Exception:
                mat = None
        if mat is None:
            print(f"    embedding {len(self.raw)} documents — minutes, not seconds; cached after "
                  f"this…", flush=True)
            mat = np.asarray(list(self._model.embed(self.raw)), dtype="float32")
            os.makedirs(os.path.dirname(self.CACHE), exist_ok=True)
            np.savez_compressed(self.CACHE, mat=mat, key=np.array(key))
        else:
            print(f"    reusing cached embeddings for {len(self.raw)} documents", flush=True)
        self._mat = mat / (np.linalg.norm(mat, axis=1, keepdims=True) + 1e-9)

    def search(self, q: str, k: int = 10) -> list[tuple[str, str, float]]:
        np = self._np
        qv = np.asarray(list(self._model.embed([q]))[0], dtype="float32")
        qv = qv / (np.linalg.norm(qv) + 1e-9)
        sims = self._mat @ qv
        return [(self.ids[i], self.raw[i], float(sims[i])) for i in np.argsort(-sims)[:k]]


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
         check=lambda t: "feature gate" in t.lower(), cat="lookup (control)",
         why="lookup — text should do fine"),
    dict(q="find the KEP about coscheduling",
         tool="has_this_been_tried", args={"idea_text": "coscheduling gang scheduling"},
         check=lambda t: "coscheduling" in t.lower(), cat="lookup (control)",
         why="title lookup — text SHOULD win this"),
    dict(q="which areas lost every approver with dedicated authority?",
         tool="ownership_dilution", args={},
         check=lambda t: "endpoints/metrics" in t and "falls back" in t.lower(), cat="inheritance",
         why="needs a tree walk to the nearest live ancestor"),
    dict(q="who should inherit lavalamp's areas?",
         tool="successor_for", args={"handle": "lavalamp"},
         check=lambda t: "deads2k" in t and re.search(r"\b2[0-9] of", t) is not None, cat="expertise",
         why="needs co-ownership overlap counted across two edge types"),
    dict(q="who held the most connective authority before stepping back?",
         tool="stepped_back_bridges", args={"min_areas": 3},
         check=lambda t: "lavalamp" in t and "betweenness" in t.lower(), cat="whole-graph",
         why="needs betweenness centrality — a whole-graph property"),
    dict(q="which cited decision records do not exist?",
         tool="broken_lineage", args={"min_cites": 2},
         check=lambda t: "0006-apply" in t, cat="absence",
         why="needs inbound edges to a node that is ABSENT"),
    dict(q="what knowledge here is going stale?",
         tool="stale_knowledge", args={"min_years": 3},
         check=lambda t: "KEP-583" in t and "still cited by" in t, cat="currency",
         why="needs age + inbound citations + author authority, joined"),
    dict(q="who owns the apiserver metrics endpoint, really?",
         tool="who_owns",
         args={"path": "staging/src/k8s.io/apiserver/pkg/endpoints/metrics/OWNERS", "depth": 4},
         check=lambda t: "no one named here still holds approval authority" in t.lower()
                         or "still holds approval" in t.lower(), cat="inheritance",
         why="needs inheritance resolved, not just the file read"),
    # --- added after reading a competing entry whose eval ran 60 questions against this one's
    # eight. Eight is enough to show a direction and too few to be evidence. These are written the
    # same way as the originals: a real question, a programmatic check over what the mode actually
    # returned, and a category so the result can be read per kind rather than as one average. The
    # control category is deliberately GROWN too -- a baseline that is only asked questions it
    # must lose is a strawman, and its score rising is the point of including them.
    dict(q="which KEP discusses self-assembling inventories?",
         tool="has_this_been_tried", args={"idea_text": "self-assembling inventories"},
         check=lambda t: "4322" in t or "self-assembling" in t.lower(), cat="lookup (control)",
         why="title lookup — text should find this"),
    dict(q="was a generic annotation considered for the class name?",
         tool="has_this_been_tried", args={"idea_text": "use an annotation instead of a field"},
         check=lambda t: "annotation" in t.lower(), cat="lookup (control)",
         why="phrase lookup — text should find this"),
    dict(q="has storing cluster state in a relational database been proposed?",
         tool="has_this_been_tried",
         args={"idea_text": "store cluster state in a relational database"},
         check=lambda t: "rejected in kep" in t.lower(), cat="lookup (control)",
         why="idea lookup, loosely worded — text has the words"),
    dict(q="who really owns pkg/scheduler?",
         tool="who_owns", args={"path": "pkg/scheduler/OWNERS", "depth": 4},
         check=lambda t: "sanposhiho" in t and "actively owned" in t.lower(), cat="inheritance",
         why="an area that IS owned — the control for the inheritance category"),
    dict(q="does anyone named on the apiserver metrics file still approve there?",
         tool="who_owns",
         args={"path": "staging/src/k8s.io/apiserver/pkg/endpoints/metrics/OWNERS", "depth": 4},
         check=lambda t: "logicalhan" in t, cat="inheritance",
         why="needs the departed owner named, not just the file's contents"),
    dict(q="who already co-owns the areas spiffxp abandoned?",
         tool="successor_for", args={"handle": "spiffxp"},
         check=lambda t: "bentheelder" in t and re.search(r"\b8 of their 9\b", t) is not None,
         cat="expertise",
         why="needs overlap counted between two people across areas"),
    dict(q="which areas are held by exactly one approver?",
         tool="sole_approver_risk", args={},
         check=lambda t: "apelisse" in t and "only approver" in t.lower(), cat="absence",
         why="counting approvers per area — no document states this"),
    dict(q="whose ownership record contradicts itself?",
         tool="stepped_back_but_still_listed", args={"min_stepped_back": 3},
         check=lambda t: "spiffxp" in t and "hack/jenkins" in t, cat="absence",
         why="needs two edge types compared for the same person"),
    dict(q="which contributor community is losing its people fastest?",
         tool="hollowing_communities", args={},
         check=lambda t: "community" in t.lower() and "stepped back" in t.lower(),
         cat="whole-graph",
         why="needs community detection — the groups are declared nowhere"),
    dict(q="which decision has been provisional the longest while still being cited?",
         tool="stale_knowledge", args={"min_years": 3},
         check=lambda t: "provisional for" in t.lower() and "still cited by" in t.lower(),
         cat="currency",
         why="needs status, age and inbound citations joined"),
    dict(q="what would be left with no owner if the apiserver reviewers all stepped back?",
         tool="what_if_they_go",
         args={"handles": ["deads2k", "liggitt", "jpbetz", "smarterclayton", "enj", "serathius"]},
         check=lambda t: "kms" in t.lower(), cat="counterfactual",
         why="needs the graph re-evaluated after a deletion that never happened"),
    dict(q="how many areas are stranded today, before anyone else leaves?",
         tool="what_if_they_go",
         args={"handles": ["deads2k", "liggitt", "jpbetz", "smarterclayton", "enj", "serathius"]},
         check=lambda t: "baseline before the change: 0 areas" in t.lower(), cat="counterfactual",
         why="needs a baseline the corpus never states"),
    # --- Added after comparing this eval's SIZE against the field's: 20 questions where rival
    # entries publish 29 and 60. Growing it is only worth anything if the new questions can go
    # against me, so all five are control lookups whose answer IS written in a document and
    # which the text baseline duly won -- all five, taking it from 4/20 to 9/25.
    #
    # Three more were written and then deleted: sole_approver_risk, hollowing_communities and
    # stepped_back_but_still_listed were already covered above, and I added them without
    # checking. Three questions the graph wins, re-asked in different words, would have moved
    # the ratio without telling anyone anything -- which is the exact padding this comment
    # opened by disclaiming.
    dict(q="is there a proposal about sidecar containers?",
         tool="has_this_been_tried",
         args={"idea_text": "run a sidecar container alongside the main one"},
         check=lambda t: "sidecar" in t.lower(), cat="lookup (control)",
         why="a KEP title — text should find this"),
    dict(q="has node system swap support been proposed?",
         tool="has_this_been_tried", args={"idea_text": "let nodes use swap memory"},
         check=lambda t: "swap" in t.lower(), cat="lookup (control)",
         why="a KEP title — text should find this"),
    dict(q="is there anything about seccomp by default?",
         tool="has_this_been_tried", args={"idea_text": "enable seccomp profiles by default"},
         check=lambda t: "seccomp" in t.lower(), cat="lookup (control)",
         why="a KEP title — text should find this"),
    dict(q="has in-place resize of pod resources been proposed?",
         tool="has_this_been_tried", args={"idea_text": "resize pod resources without restarting"},
         check=lambda t: "in-place" in t.lower() or "resize" in t.lower(),
         cat="lookup (control)", why="a KEP title — text should find this"),
    dict(q="is there a proposal about writable cgroups?",
         tool="has_this_been_tried",
         args={"idea_text": "make cgroups writable from inside the container"},
         check=lambda t: "cgroup" in t.lower(), cat="lookup (control)",
         why="a KEP title — text should find this"),

]


def main() -> int:
    from tombstone.agent import render
    g = connect().select_graph("tomb:k8s")
    agent = Agent(graph_name="tomb:k8s")

    import os as _os0
    want_dense = "--dense" in sys.argv or _os0.environ.get("EVAL_DENSE") == "1"

    print("building the text baseline over the same documents…")
    docs = load_documents(g)
    tfidf = TfIdf(docs)
    dense = Dense(docs) if want_dense else None
    print(f"  {len(docs)} documents indexed (KEPs, alternatives, OWNERS files)"
          + ("; and again by embedding\n" if dense else
             ". Dense retrieval off; add --dense to score it too.\n"))

    _dh = f"{'dense':>8}" if dense else ""
    print(f"{'question':<52}{'graph':>8}{'text':>8}{_dh}   what it needs")
    print("-" * 118)
    gw = tw = dw = 0
    by_cat: dict[int, tuple[int, int, int]] = {}
    for item in QUESTIONS:
        a = agent.dispatch(item["tool"], item["args"])
        g_text = render(a)
        g_ok = a.shape == "ANSWERED_WITH_PATH" and item["check"](g_text)

        hits = tfidf.search(item["q"], k=10)
        t_text = "\n".join(f"{i} {b}" for i, b, _ in hits)
        t_ok = bool(hits) and item["check"](t_text)

        d_ok = False
        if dense is not None:
            dhits = dense.search(item["q"], k=10)
            d_ok = bool(dhits) and item["check"]("\n".join(f"{i} {b}" for i, b, _ in dhits))

        gw += g_ok
        tw += t_ok
        dw += d_ok
        by_cat[id(item)] = (int(g_ok), int(t_ok), int(d_ok))
        _dc = (f"{'PASS' if d_ok else ' -- ':>8}") if dense is not None else ""
        print(f"  {item['q'][:50]:<50}{'PASS' if g_ok else ' -- ':>8}"
              f"{'PASS' if t_ok else ' -- ':>8}{_dc}   {item['why']}")

    n = len(QUESTIONS)
    print("-" * 118)
    print(f"  {'':<50}{gw}/{n:<7}{tw}/{n}"
          + (f"{'':<3}{dw}/{n}" if dense is not None else ""))

    # Per category, because one average hides the only thing this eval is for. The control row
    # existing -- and the baseline scoring on it -- is what makes the other rows mean anything.
    print()
    print(f"  {'category':<28}{'n':>3}{'graph':>8}{'text':>7}"
          + (f"{'dense':>7}" if dense is not None else ""))
    for cat in dict.fromkeys(i.get("cat", "uncategorised") for i in QUESTIONS):
        rows = [i for i in QUESTIONS if i.get("cat", "uncategorised") == cat]
        g_c = sum(by_cat[id(i)][0] for i in rows)
        t_c = sum(by_cat[id(i)][1] for i in rows)
        print(f"  {cat:<28}{len(rows):>3}{g_c:>8}{t_c:>7}"
              + (f"{sum(by_cat[id(i)][2] for i in rows):>7}" if dense is not None else ""))
    print()
    print(f"Graph answers {gw}/{n}. A TF-IDF index over the same documents answers {tw}/{n}.")
    print("The text baseline sees every word the graph does. Where a question is a lookup it")
    print("competes; where the answer is a path, an absence, or a whole-graph property, there is")
    print("no document for it to find — because the answer was never written down anywhere.")

    # This score is quoted in the README's 60-second box and in the submission copy, and until now
    # nothing connected those sentences to this run. Every other number in this repo that was
    # typed into prose rather than derived from the thing it describes has gone stale, several of
    # them within a day, so this one is asserted where it is produced.
    import os as _os
    import re as _re
    import subprocess as _subp
    drift = []

    # This was a hand-kept list of three filenames, and the comment on the third one said it had
    # been "found by grep, not by a check, which is the whole problem" -- EXPLAIN-IT.md was still
    # saying 7/8 after the eval grew to twenty questions. Adding one more name to the list did not
    # fix the problem, it postponed it: FINISH.md was ALSO still saying 7/8, and FINISH.md is the
    # file read last, under deadline, with the answers to a judge's hard questions in it. So the
    # list is gone. Every tracked document that mentions the baseline is scanned, in any phrasing.
    #
    # The rule is denominator-first, which is what makes it phrasing-agnostic: this benchmark's
    # denominator is the question count, so a pair in one of these paragraphs whose denominator is
    # not n is stale by construction -- that is exactly the shape 7/8 and 2/8 have.
    _docs = [d for d in _subp.run(["git", "ls-files", "*.md"], capture_output=True,
                                  text=True).stdout.split() if _os.path.exists(d)]
    _stated = 0
    for doc in _docs:
        for para in _re.split(r"\n\s*\n", open(doc).read()):
            if not _re.search(r"TF-IDF|text baseline|text index", para, _re.I):
                continue
            for a, b in _re.findall(r"(\d+)\s*(?:/|\s+of\s+)\s*(\d+)", para):
                a, b = int(a), int(b)
                _stated += 1
                if b != n:
                    drift.append(f"{doc} scores this benchmark out of {b}; it has {n} questions "
                                 f"(says {a}/{b}, so it predates the eval growing)")
                elif a not in ((gw, tw, dw) if dense is not None
                               else (gw, tw, DENSE_LAST_MEASURED)):
                    drift.append(f"{doc} says {a}/{b}; this run measured {gw}/{n} for the graph "
                                 f"and {tw}/{n} for the text baseline")
    if not _stated:
        drift.append("no tracked document states this score any more; at least one should")
    # The one direction that matters: when the dense baseline HAS run, it owns the constant the
    # cheap run trusts. A figure the documents may quote must be re-derived by something.
    if dense is not None and dw != DENSE_LAST_MEASURED:
        drift.append(f"the dense baseline scored {dw}/{n}; DENSE_LAST_MEASURED says "
                     f"{DENSE_LAST_MEASURED}. Update the constant and every document quoting it.")

    # The README's 60-second block states the same two facts in WORDS -- "loses one of those
    # twenty-five" and "ties the baseline nine-all" -- and the scan above only matches digits, so
    # growing the eval from 20 to 25 left "one of those twenty" sitting in the first thing a judge
    # reads. Spelled numbers drift exactly as readily as digits and are harder to grep for.
    _SPELL = {1: "one", 2: "two", 3: "three", 4: "four", 5: "five", 6: "six", 7: "seven",
              8: "eight", 9: "nine", 10: "ten", 11: "eleven", 12: "twelve", 13: "thirteen",
              14: "fourteen", 15: "fifteen", 16: "sixteen", 17: "seventeen", 18: "eighteen",
              19: "nineteen", 20: "twenty", 21: "twenty-one", 22: "twenty-two",
              23: "twenty-three", 24: "twenty-four", 25: "twenty-five", 26: "twenty-six",
              27: "twenty-seven", 28: "twenty-eight", 29: "twenty-nine", 30: "thirty"}
    # Flattened: these patterns span several words, so a reflow that moved a line break
    # between them would stop the match. The floors below would then fail loudly, which
    # is the right failure for a deleted claim and the wrong one for a reformatted
    # paragraph -- a check that cries wolf at `fmt` is one people learn to skip.
    _readme_txt = _re.sub(r"\s*\n>?\s*", " ", open("README.md").read())
    _m = _re.search(r"loses (?:one|\w+) of those ([\w-]+) on purpose", _readme_txt)
    if not _m:
        drift.append("README no longer says how many questions the graph loses one of")
    elif _m.group(1) != _SPELL.get(n):
        drift.append(f"README says 'one of those {_m.group(1)}'; the eval has {n} questions "
                     f"({_SPELL.get(n)})")
    _ctrl = [i for i in QUESTIONS if i.get("cat") == "lookup (control)"]
    _ctrl_t = sum(by_cat[id(i)][1] for i in _ctrl)
    _m2 = _re.search(r"ties the baseline ([\w-]+)-all", _readme_txt)
    if not _m2:
        drift.append("README no longer states the control-category tie in words")
    elif _m2.group(1) != _SPELL.get(_ctrl_t):
        drift.append(f"README says the baseline ties {_m2.group(1)}-all on the control category; "
                     f"this run measured {_ctrl_t}")
    # ...and the per-category table the README prints, row by row. Writing that table by hand is
    # how the totals got stale in the first place.
    readme = open("README.md").read()
    for cat in dict.fromkeys(i.get("cat", "uncategorised") for i in QUESTIONS):
        rows = [i for i in QUESTIONS if i.get("cat", "uncategorised") == cat]
        g_c = sum(by_cat[id(i)][0] for i in rows)
        t_c = sum(by_cat[id(i)][1] for i in rows)
        m = _re.search(rf"^{_re.escape(cat)}\s+(\d+)\s+(\d+)\s+(\d+)", readme, _re.M)
        if not m:
            drift.append(f"README has no category row for {cat!r}")
        elif (int(m.group(1)), int(m.group(2)), int(m.group(3))) != (len(rows), g_c, t_c):
            drift.append(f"README's {cat!r} row says {m.groups()}; "
                         f"this run measured ({len(rows)}, {g_c}, {t_c})")

    # The totals line under that table, which this check did not read until it was found wrong by
    # eye: the category rows all said 25/24/9 while the row beneath them still said 20/19/4 from
    # before the eval grew. The comment above has claimed since it was written that hand-written
    # totals are how this goes stale, and the totals were the one line it was not looking at.
    _tot = _re.search(rf"^\s+{n}\s+(\d+)\s+(\d+)\s*$", readme, _re.M)
    if not _tot:
        drift.append(f"README's eval table has no totals row reading {n} questions")
    elif (int(_tot.group(1)), int(_tot.group(2))) != (gw, tw):
        drift.append(f"README's totals row says {_tot.groups()} for {n} questions; "
                     f"this run measured ({gw}, {tw})")

    if drift:
        print()
        for d in drift:
            print("  FAIL ", d)
        return 1
    print(f"\nThe README and the submission copy both state {gw}/{n} vs {tw}/{n}, and so does this run.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
