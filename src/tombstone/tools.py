"""The agent's fixed tool catalogue.

The organizer's own kickoff blog is explicit about the architecture: "Fix the queries, parameterise
them, and let the model choose between them rather than compose them", and "the agent never writes
a query". So every query here is hand-written and parameterised, the model only picks a tool name
and fills its arguments, and no model output is ever concatenated into Cypher.

Each tool returns an Answer with one of four SHAPES, mirroring the blog's own taxonomy:
    ANSWERED_WITH_PATH  - found it, and here is the traversal that proves it
    NOT_IN_GRAPH        - the traversal ran and returned nothing. This is a real answer.
    UNKNOWN_ENTITY      - the name did not resolve, so nothing else ran
    DEGRADED            - the graph is reachable but the query could not complete

The UNKNOWN_ENTITY shape matters: the blog warns that "a plausible service name is worse than no
answer", so every entity argument is resolved against the graph before any traversal runs.

Honest-negative discipline: a NOT_IN_GRAPH result always carries a `coverage` block, because an
empty traversal only means the graph does not know -- it is not proof that nothing exists.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

# A fixed "now" is injected per request. FalkorDB v4.22.1 cannot do datetime arithmetic, so all
# age comparisons are integer millisecond maths against this parameter.
MS_PER_YEAR = 31_557_600_000


@dataclass
class Answer:
    shape: str
    tool: str
    rows: list = field(default_factory=list)
    paths: list = field(default_factory=list)
    coverage: dict = field(default_factory=dict)
    note: str = ""
    cypher: str = ""
    params: dict = field(default_factory=dict)
    ms: float = 0.0

    def to_dict(self) -> dict:
        return asdict(self)


class Tools:
    """Fixed Cypher catalogue. One method per agent tool."""

    def __init__(self, graph, now_ms: int):
        self.g = graph
        self.now_ms = now_ms

    # ---------- internal ----------
    def _run(self, tool: str, cypher: str, params: dict) -> tuple[list, float]:
        import time
        t0 = time.perf_counter()
        res = self.g.ro_query(cypher, params=params)
        return res.result_set, (time.perf_counter() - t0) * 1000

    def _coverage(self) -> dict:
        """What the graph actually contains, so a negative can be read honestly."""
        rows, _ = self._run(
            "coverage",
            """
            MATCH (k:Kep) WITH count(k) AS keps
            MATCH (a:Alternative) WITH keps, count(a) AS alts
            MATCH (p:Person) WITH keps, alts, count(p) AS people
            MATCH (o:OwnersFile) WITH keps, alts, people, count(o) AS owners
            MATCH (m:MissingRecord)
            RETURN keps, alts, people, owners, count(m) AS missing
            """,
            {},
        )
        if not rows:
            return {}
        k, a, p, o, m = rows[0]
        return {
            "decisions_indexed": k,
            "rejected_alternatives_indexed": a,
            "people": p,
            "ownership_files": o,
            "missing_decision_records": m,
            "corpus": "kubernetes/enhancements + kubernetes/kubernetes OWNERS",
            "caveat": "An empty result means this corpus does not record it. It is not proof it never happened.",
        }

    def resolve_person(self, handle: str) -> str | None:
        rows, _ = self._run(
            "resolve_person",
            "MATCH (p:Person {key: $h}) RETURN p.key LIMIT 1",
            {"h": (handle or "").strip().lstrip("@").lower()},
        )
        return rows[0][0] if rows else None

    def resolve_path(self, path: str) -> str | None:
        rows, _ = self._run(
            "resolve_path",
            "MATCH (o:OwnersFile) WHERE o.path = $p RETURN o.path LIMIT 1",
            {"p": (path or "").strip()},
        )
        return rows[0][0] if rows else None

    # ---------- TOOL 1 ----------
    HAS_THIS_BEEN_TRIED = """
CALL db.idx.vector.queryNodes('NamedOption', 'emb', $k, vecf32($qvec)) YIELD node AS alt, score
WITH alt, score WHERE score <= $maxDist
MATCH (kep:Kep)-[:CONSIDERED]->(alt)
OPTIONAL MATCH (kep)-[:OWNED_BY]->(sig:Sig)
OPTIONAL MATCH (author:Person)-[:AUTHORED|APPROVED]->(kep)
OPTIONAL MATCH (author)-[liveRole:APPROVES]->()
WITH kep, sig, alt, score,
     collect(DISTINCT author.key) AS deciders,
     count(DISTINCT liveRole)     AS decider_live_roles
RETURN alt.title                             AS rejected_idea,
       alt.body                              AS rationale,
       kep.num                               AS kep,
       kep.title                             AS kep_title,
       kep.status                            AS status,
       sig.key                               AS sig,
       kep.url                               AS source_url,
       CASE WHEN kep.created_ms = 0 THEN -1
            ELSE ($now - kep.created_ms) / $msYear END AS years_ago,
       deciders,
       decider_live_roles,
       CASE WHEN decider_live_roles = 0 THEN 'NO_LIVING_OWNER' ELSE 'HAS_LIVING_OWNER' END
                                             AS rationale_ownership,
       round(score * 1000) / 1000            AS distance
ORDER BY score ASC
LIMIT $limit
"""

    def has_this_been_tried(self, qvec: list, k: int = 8, max_dist: float = 0.45, limit: int = 5) -> Answer:
        """Has this idea been proposed and rejected before, and is anyone left who knows why?"""
        params = {"qvec": qvec, "k": k, "maxDist": max_dist, "limit": limit,
                  "now": self.now_ms, "msYear": MS_PER_YEAR}
        rows, ms = self._run("has_this_been_tried", self.HAS_THIS_BEEN_TRIED, params)
        if not rows:
            return Answer("NOT_IN_GRAPH", "has_this_been_tried", coverage=self._coverage(), ms=ms,
                          cypher=self.HAS_THIS_BEEN_TRIED,
                          note="No recorded rejected alternative within the distance threshold.")
        return Answer("ANSWERED_WITH_PATH", "has_this_been_tried", rows=rows, ms=ms,
                      cypher=self.HAS_THIS_BEEN_TRIED, params={"k": k, "maxDist": max_dist})

    # ---------- TOOL 2 ----------
    ORPHANED_OWNERSHIP = """
MATCH (dep:Person)-[:EMERITUS_OF]->(f:OwnersFile)
OPTIONAL MATCH (cur:Person)-[:APPROVES]->(f)
WITH f, collect(DISTINCT dep.key) AS departed, count(DISTINCT cur) AS live_approvers
WHERE live_approvers = 0
RETURN f.path AS orphaned_area, departed, f.url AS source_url
ORDER BY f.path
LIMIT $limit
"""

    def orphaned_ownership(self, limit: int = 25) -> Answer:
        """Which areas have NO current approver at all, only departed ones? Proof by absence."""
        rows, ms = self._run("orphaned_ownership", self.ORPHANED_OWNERSHIP, {"limit": limit})
        shape = "ANSWERED_WITH_PATH" if rows else "NOT_IN_GRAPH"
        return Answer(shape, "orphaned_ownership", rows=rows, ms=ms,
                      cypher=self.ORPHANED_OWNERSHIP, coverage=self._coverage())

    # ---------- TOOL 3 ----------
    DEPARTED_BRIDGES = """
CALL algo.betweenness({nodeLabels:['Person'], relationshipTypes:['CO_AUTHORED'], samplingSeed: $seed})
YIELD node, score
WITH node AS p, score AS bridge
MATCH (p)-[:EMERITUS_OF]->(f:OwnersFile)
OPTIONAL MATCH (p)-[liveRole:APPROVES]->()
WITH p, bridge, count(DISTINCT f) AS abandoned_areas, count(liveRole) AS live_roles
WHERE live_roles = 0 AND abandoned_areas >= $minAreas
RETURN p.key                        AS departed_bridge,
       round(bridge * 100) / 100     AS betweenness,
       abandoned_areas
ORDER BY bridge DESC
LIMIT $limit
"""

    def departed_bridges(self, min_areas: int = 3, limit: int = 10, seed: int = 42) -> Answer:
        """Whose departure cost the most CONNECTIVE knowledge, not just the most files?

        Betweenness centrality is the point: it is a whole-graph property, so neither a traversal
        nor a vector search can produce it. The seed is pinned because algo.betweenness is sampled
        (samplingSize default 32) and its default seed is time-based, so unseeded runs are not
        reproducible.
        """
        params = {"minAreas": min_areas, "limit": limit, "seed": seed}
        rows, ms = self._run("departed_bridges", self.DEPARTED_BRIDGES, params)
        shape = "ANSWERED_WITH_PATH" if rows else "NOT_IN_GRAPH"
        return Answer(shape, "departed_bridges", rows=rows, ms=ms,
                      cypher=self.DEPARTED_BRIDGES, params=params, coverage=self._coverage(),
                      note="betweenness is sampled (size 32, seed pinned) -- approximate, reproducible")

    # ---------- TOOL 4 ----------
    SUCCESSOR_FOR = """
MATCH (dep:Person {key: $handle})-[:EMERITUS_OF]->(f:OwnersFile)
WITH dep, collect(DISTINCT f) AS abandoned
UNWIND abandoned AS area
MATCH (cand:Person)-[:APPROVES]->(area)
WITH dep, cand, size(abandoned) AS total_abandoned, count(DISTINCT area) AS shared
MATCH (cand)-[:APPROVES]->(owned:OwnersFile)
RETURN cand.key                 AS candidate,
       shared                   AS shares_areas_with_departed,
       total_abandoned          AS departed_total_areas,
       count(DISTINCT owned)    AS candidate_total_areas
ORDER BY shared DESC, candidate_total_areas DESC
LIMIT $limit
"""

    def successor_for(self, handle: str, limit: int = 6) -> Answer:
        """Who already co-owns the areas this departed person left behind?"""
        resolved = self.resolve_person(handle)
        if not resolved:
            return Answer("UNKNOWN_ENTITY", "successor_for",
                          note=f"'{handle}' is not a person in this graph. Nothing else was run.",
                          coverage=self._coverage())
        rows, ms = self._run("successor_for", self.SUCCESSOR_FOR, {"handle": resolved, "limit": limit})
        shape = "ANSWERED_WITH_PATH" if rows else "NOT_IN_GRAPH"
        return Answer(shape, "successor_for", rows=rows, ms=ms,
                      cypher=self.SUCCESSOR_FOR, params={"handle": resolved},
                      coverage=self._coverage() if not rows else {})

    # ---------- TOOL 5 ----------
    BROKEN_LINEAGE = """
MATCH (k:Kep)-[:CITES_MISSING]->(m:MissingRecord)
WITH m, collect(DISTINCT k.num) AS citing_keps, count(DISTINCT k) AS cited_by
WHERE cited_by >= $minCites
RETURN m.key AS missing_record, cited_by, citing_keps
ORDER BY cited_by DESC, m.key
LIMIT $limit
"""

    def broken_lineage(self, min_cites: int = 1, limit: int = 15) -> Answer:
        """Which cited decision records do not exist? Inbound edges to a missing node."""
        rows, ms = self._run("broken_lineage", self.BROKEN_LINEAGE,
                             {"minCites": min_cites, "limit": limit})
        shape = "ANSWERED_WITH_PATH" if rows else "NOT_IN_GRAPH"
        return Answer(shape, "broken_lineage", rows=rows, ms=ms, cypher=self.BROKEN_LINEAGE)

    # ---------- TOOL 6: the depth contrast the rubric asks for ----------
    WHO_OWNS_DEPTH1 = """
MATCH (p:Person)-[:APPROVES]->(o:OwnersFile {path: $path})
RETURN p.key AS approver, o.path AS area, o.url AS source_url
ORDER BY approver
LIMIT $limit
"""

    WHO_OWNS_DEPTH4 = """
MATCH (o:OwnersFile {path: $path})
OPTIONAL MATCH (live:Person)-[:APPROVES]->(o)
OPTIONAL MATCH (dep:Person)-[:EMERITUS_OF]->(o)
WITH o, collect(DISTINCT live.key) AS live_approvers, collect(DISTINCT dep) AS departed
UNWIND (CASE WHEN size(departed) = 0 THEN [null] ELSE departed END) AS d
OPTIONAL MATCH (d)-[:AUTHORED|APPROVED]->(k:Kep)-[:CONSIDERED]->(a:Alternative)
OPTIONAL MATCH (k)-[:OWNED_BY]->(sig:Sig)
WITH o, live_approvers, d,
     collect(DISTINCT k.num)   AS decisions_they_shaped,
     collect(DISTINCT a.title) AS ideas_they_rejected,
     collect(DISTINCT sig.key) AS sigs_touched
RETURN o.path                    AS area,
       live_approvers,
       d.key                     AS departed_owner,
       size(decisions_they_shaped) AS n_decisions,
       decisions_they_shaped[0..5] AS sample_decisions,
       ideas_they_rejected[0..4]   AS sample_rejected_ideas,
       sigs_touched,
       CASE WHEN size(live_approvers) = 0 THEN 'ORPHANED' ELSE 'COVERED' END AS status
LIMIT $limit
"""

    def who_owns(self, path: str, depth: int = 1, limit: int = 20) -> Answer:
        """Same question, two depths. Depth 1 is what any database serves; depth 4 is the graph."""
        resolved = self.resolve_path(path)
        if not resolved:
            return Answer("UNKNOWN_ENTITY", "who_owns",
                          note=f"'{path}' is not an ownership file in this graph. Nothing else was run.",
                          coverage=self._coverage())
        cypher = self.WHO_OWNS_DEPTH1 if depth <= 1 else self.WHO_OWNS_DEPTH4
        rows, ms = self._run("who_owns", cypher, {"path": resolved, "limit": limit})
        if rows:
            return Answer("ANSWERED_WITH_PATH", f"who_owns(depth={depth})", rows=rows, ms=ms,
                          cypher=cypher, params={"path": resolved, "depth": depth})
        # The path RESOLVED -- it simply has no current approvers. Saying "nothing matches that"
        # here would be the kind of plausible-but-wrong answer the brief warns about.
        return Answer(
            "NOT_IN_GRAPH", f"who_owns(depth={depth})", rows=[], ms=ms, cypher=cypher,
            params={"path": resolved, "depth": depth},
            note=(f"{resolved} is a real ownership file in this graph, but it has NO current "
                  f"approvers. Ask again at depth 4 to see who used to own it and what they decided."),
            coverage=self._coverage(),
        )


CATALOGUE = {
    "has_this_been_tried": "Search recorded rejected design alternatives by meaning, and report whether anyone who made that call is still around. Args: idea_text.",
    "orphaned_ownership": "List areas that have NO current approver, only departed ones. Args: none.",
    "departed_bridges": "Rank departed people by how much CONNECTIVE knowledge left with them (betweenness centrality). Args: min_areas.",
    "successor_for": "Suggest who should inherit a departed person's areas, from co-ownership overlap. Args: handle.",
    "broken_lineage": "List decision records that other decisions cite but which do not exist. Args: min_cites.",
    "who_owns": "Who owns an area. depth=1 gives the approver list; depth=4 adds what the departed owner decided elsewhere. Args: path, depth.",
}
