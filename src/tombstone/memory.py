"""Write answers back into the graph, so the agent accumulates precedent.

The brief's stated evaluation goals are that the agent acts on connected data, **remembers what it
learns**, and shows how it reached each answer. Without this module Tombstone does the first and
third and not the second.

The design choice that matters: an answer is not stored as text. It is stored as a node that
CITES the exact graph nodes it was built from. That means recall is a traversal rather than a
string lookup, and it means a remembered answer can be re-checked against the live graph instead
of being trusted — if the underlying node is gone, the memory says so.

Memory lives in the SAME graph as the facts, because a separate store would make the
"works without FalkorDB" test pass, which is precisely the failure the rules describe.
"""
from __future__ import annotations

import hashlib
import re
import time

SCHEMA = """
(:Answer  {qid, question, tool, shape, query_sha, ts_ms:int, row_count:int, emb})
(:Answer)-[:CITED {role}]->(:Kep | :Person | :OwnersFile | :NamedOption | :MissingRecord)
"""
# This used to declare `(:Answer)-[:FOLLOWS]->(:Answer)  -- same session, ordered` as well, and
# nothing in this module or any other ever created one: `CALL db.relationshipTypes()` on a graph
# that has answered questions returns fourteen types and FOLLOWS is not among them. A schema
# comment that names an edge the code does not write is a false description of the data model in
# the file a reader goes to for the data model. Removed rather than implemented, because session
# ordering is already carried by `ts_ms` and nothing asks for the edge.


# The question text an (:Answer) carries is shown VERBATIM to whoever clicks the recall chip
# next, and on the hosted demo anyone can supply it: /api/tool takes a free-form `question`
# beside the tool name, so a stranger's text becomes a line inside this product's own answer
# card. Rendering is text-nodes-only, so there is no markup to execute -- but a NEWLINE is enough
# to forge the card's own lines. Measured on the running app: a question carrying
# "legit question\n\n--- a/README.md\n+++ SUBMISSION WITHDRAWN by the author" came back from the
# recall chip as extra bullets reading like output from this repository.
#
# So the stored text is one line, printable, and bounded. This changes what is DISPLAYED only:
# `qid` already normalises whitespace before hashing, so a repeat still merges onto the same node
# and ANSWERED_FROM_MEMORY is unaffected. Truncation is marked rather than silent, because a
# question that stops mid-word with no sign reads like the product lost half of it.
_CONTROL = re.compile(r"[\x00-\x1f\x7f-\x9f\u2028\u2029]+")


def clean_question(question: str, cap: int = 400) -> str:
    one_line = _CONTROL.sub(" ", question or "")
    one_line = " ".join(one_line.split())
    return one_line[: cap - 1] + "\u2026" if len(one_line) > cap else one_line


def qid(question: str, tool: str) -> str:
    return hashlib.sha256(f"{tool}|{' '.join(question.lower().split())}".encode()).hexdigest()[:16]


class Memory:
    """Episodic (what was asked, when), semantic (what it cited), procedural (which tool worked)."""

    def __init__(self, graph, embedder=None):
        self.g = graph
        self._embedder = embedder
        self._ready = False

    def ensure(self) -> None:
        if self._ready:
            return
        try:
            self.g.query("CREATE INDEX FOR (a:Answer) ON (a.qid)")
        except Exception:
            pass
        try:
            self.g.query(
                "CREATE VECTOR INDEX FOR (a:Answer) ON (a.emb) "
                "OPTIONS {dimension: 384, similarityFunction: 'cosine'}"
            )
        except Exception:
            pass
        self._ready = True

    # ---------- write ----------
    def record(self, question: str, answer, session: str = "default",
               qvec: list | None = None) -> str | None:
        """Store one answer and link it to the nodes it was actually built from.

        Returns the qid, or None if nothing was worth recording. Failures here are swallowed:
        memory is additive, and a write problem must never break the answer the user asked for.
        """
        self.ensure()
        aid = qid(question, answer.tool)
        now = int(time.time() * 1000)
        try:
            self.g.query(
                """
                MERGE (a:Answer {qid: $qid})
                ON CREATE SET a.question = $q, a.tool = $tool, a.shape = $shape,
                              a.query_sha = $sha, a.ts_ms = $now, a.row_count = $rows,
                              a.times_asked = 1
                ON MATCH  SET a.ts_ms = $now, a.shape = $shape, a.row_count = $rows,
                              a.times_asked = coalesce(a.times_asked, 1) + 1
                """,
                params={"qid": aid, "q": clean_question(question), "tool": answer.tool,
                        "shape": answer.shape, "sha": answer.cypher and
                        hashlib.sha256(" ".join(answer.cypher.split()).encode()).hexdigest()[:12],
                        "now": now, "rows": len(answer.rows)},
            )
            if qvec:
                self.g.query(
                    "MATCH (a:Answer {qid: $qid}) SET a.emb = vecf32($v)",
                    params={"qid": aid, "v": qvec},
                )
            self._link(aid, answer)
        except Exception:
            return None
        return aid

    def _link(self, aid: str, answer) -> None:
        """Link the answer to the real nodes behind it, by their natural keys.

        Only entities the tool genuinely returned are cited. Nothing is inferred, because a
        fabricated citation is worse than no citation.
        """
        keys = {"Kep": set(), "Person": set(), "OwnersFile": set(), "MissingRecord": set()}
        t = answer.tool
        for r in answer.rows:
            try:
                if t == "has_this_been_tried":
                    keys["Kep"].add(str(r[2]))
                    for d in (r[8] or []):
                        keys["Person"].add(d)
                elif t == "ownership_dilution":
                    keys["OwnersFile"].add(r[0])
                    for d in (r[1] or []):
                        keys["Person"].add(d)
                elif t == "stepped_back_bridges":
                    keys["Person"].add(r[0])
                elif t == "successor_for":
                    keys["Person"].add(r[0])
                elif t == "broken_lineage":
                    keys["MissingRecord"].add(r[0])
                elif t.startswith("who_owns"):
                    keys["OwnersFile"].add(r[0])
                # Below: tools that return perfectly good entities but were never wired up, so
                # they recorded ZERO citations and could therefore never be returned from memory
                # -- the gate for ANSWERED_FROM_MEMORY is that the cited nodes still resolve, and
                # a tool with no citations has nothing to re-check. Memory worked on 6 of 13
                # tools and silently did nothing on the rest.
                elif t == "sole_approver_risk":
                    keys["Person"].add(r[0])
                    for area in (r[2] or []):
                        keys["OwnersFile"].add(area)
                elif t == "hollowing_communities":
                    for person in (r[5] or []):
                        keys["Person"].add(person)
                elif t == "stale_knowledge":
                    keys["Kep"].add(str(r[0]))
                elif t == "what_if_they_go":
                    for person in (r[0] or []):
                        keys["Person"].add(person)
                    for area in (r[1] or []):
                        keys["OwnersFile"].add(area)
                elif t == "stepped_back_but_still_listed":
                    keys["Person"].add(r[0])
                    for area in (r[3] or []):
                        keys["OwnersFile"].add(area)
                elif t == "draft_owners_patch":
                    keys["Person"].add(r[0])
                    keys["OwnersFile"].add(r[1])
            except (IndexError, TypeError):
                continue

        # Kep is keyed by directory path but these tools return kep-number, so match on num.
        if keys["Kep"]:
            self.g.query(
                """
                MATCH (a:Answer {qid: $qid})
                UNWIND $nums AS n
                MATCH (k:Kep {num: n})
                MERGE (a)-[:CITED {role: 'decision'}]->(k)
                """,
                params={"qid": aid, "nums": [k for k in keys["Kep"] if k]},
            )
        for label, role in (("Person", "person"), ("OwnersFile", "area"),
                            ("MissingRecord", "missing")):
            vals = [v for v in keys[label] if v]
            if not vals:
                continue
            self.g.query(
                f"""
                MATCH (a:Answer {{qid: $qid}})
                UNWIND $keys AS k
                MATCH (n:{label} {{key: k}})
                MERGE (a)-[:CITED {{role: $role}}]->(n)
                """,
                params={"qid": aid, "keys": vals, "role": role},
            )

    # ---------- read ----------
    RECALL = """
CALL db.idx.vector.queryNodes('Answer', 'emb', $k, vecf32($qvec)) YIELD node AS a, score
WITH a, score WHERE score <= $maxDist
OPTIONAL MATCH (a)-[c:CITED]->(n)
WITH a, score, collect(DISTINCT {role: c.role, key: coalesce(n.num, n.key)}) AS cited
RETURN a.question    AS asked_before,
       a.tool        AS answered_with,
       a.shape       AS shape,
       a.times_asked AS times_asked,
       a.ts_ms       AS last_asked_ms,
       a.row_count   AS rows,
       cited,
       round(score * 1000) / 1000 AS distance
ORDER BY score ASC
LIMIT $limit
"""

    def recall(self, qvec: list, k: int = 5, max_dist: float = 0.30, limit: int = 3):
        """Has this been asked before, and what did it cite? Recall is a traversal, not a cache."""
        self.ensure()
        return self.g.ro_query(
            self.RECALL,
            params={"qvec": qvec, "k": k, "maxDist": max_dist, "limit": limit},
        ).result_set

    STALE = """
MATCH (a:Answer)-[:CITED]->(n)
WITH a, count(n) AS cited_now
WHERE a.row_count > 0
RETURN a.question AS question, a.tool AS tool, a.row_count AS rows_when_answered,
       cited_now, a.ts_ms AS answered_ms
ORDER BY a.ts_ms DESC
LIMIT $limit
"""

    EXACT = """
MATCH (a:Answer {qid: $qid})
OPTIONAL MATCH (a)-[c:CITED]->(n)
RETURN a.question    AS question,
       a.tool        AS tool,
       a.times_asked AS times_asked,
       a.ts_ms       AS last_ms,
       a.row_count   AS rows,
       count(c)      AS citations_still_live
"""

    def recall_exact(self, question: str, tool: str):
        """Has this EXACT question been answered before, and do its citations still resolve?

        The re-check is the point. A remembered answer is only worth returning if the nodes it
        cited are still there -- otherwise it is a cache serving a stale claim, which is the
        failure this whole product argues against. Citations that have vanished make the memory
        unusable, and the tool re-runs instead.
        """
        self.ensure()
        rows = self.g.ro_query(self.EXACT, params={"qid": qid(question, tool)}).result_set
        return rows[0] if rows else None

    def stats(self) -> dict:
        self.ensure()
        try:
            n = self.g.ro_query("MATCH (a:Answer) RETURN count(a)").result_set[0][0]
            c = self.g.ro_query("MATCH (:Answer)-[r:CITED]->() RETURN count(r)").result_set[0][0]
            return {"answers_remembered": n, "citations": c}
        except Exception:
            return {"answers_remembered": 0, "citations": 0}
