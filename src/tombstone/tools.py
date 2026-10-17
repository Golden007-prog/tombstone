"""The agent's fixed tool catalogue.

The organizer's own kickoff blog is explicit about the architecture: "Fix the queries, parameterise
them, and let the model choose between them rather than compose them", and "the agent never writes
a query". So every query here is hand-written and parameterised, the model only picks a tool name
and fills its arguments, and no model output is ever concatenated into Cypher.

Each tool returns an Answer with one of these SHAPES, mirroring the kickoff blog's own taxonomy:
    ANSWERED_WITH_PATH   - found it, and here is the traversal that proves it
    ANSWERED_FROM_MEMORY - this exact question was answered before; the prior answer's citations
                           were re-checked against the live graph and still hold
    NOT_IN_GRAPH         - the traversal ran and returned nothing. This is a real answer.
    UNKNOWN_ENTITY       - the name did not resolve, so nothing else ran
    DEGRADED             - the graph is reachable but the query could not complete

The UNKNOWN_ENTITY shape matters: the blog warns that "a plausible service name is worse than no
answer", so every entity argument is resolved against the graph before any traversal runs.

Honest-negative discipline: a NOT_IN_GRAPH result always carries a `coverage` block, because an
empty traversal only means the graph does not know -- it is not proof that nothing exists.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
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
    # Whole-graph counts for a tool whose `rows` are a top-N page. The UI headline used to be
    # computed by summing `rows`, which silently reported the page as the population: the
    # sole-approver chip said "31 areas held alone by 12 people" when the graph has 45 across 23,
    # and this file's own docstring said 45 two hundred lines away. A LIMIT is a display decision
    # and must not become a claim, so the number in the headline comes from here, not from rows.
    totals: dict = field(default_factory=dict)


# ---------------------------------------------------------------------------
# The name path: finding a rejection by a symbol nobody can embed.
#
# README's Honest limits has carried this failure since it was measured: ask about
# `kube-state-metrics` and the rejection that names it does not come back, because the ANN index
# is minted on :NamedOption and the two copies of that rejection are among the 206 that are not.
# Re-checked against the deployed instance on 17 Oct: ANSWERED_WITH_PATH, five rows, closest
# cosine distance 0.194, not one of them the answer.
#
# It is not a scoring miss a better model would fix. A 384-dimension vector of a sentence cannot
# preserve `kube-state-metrics` as a distinct symbol, and this file's own renderer already ships
# the sentence saying the distance is not discriminative on this corpus -- 0.313 for a typed
# kubelet question against 0.297 for one about carrier pigeons.
#
# WHAT THIS IS NOT. Not a fallback for an empty similarity result: `rows` is almost never empty,
# because an ANN top-k always returns k and the 0.45 bound is loose. A fallback keyed on
# emptiness would never fire. These hits are APPENDED instead, so rows[0] stays the
# nearest-by-distance row and nothing that reads rows[0] moves.
#
# Nor is the question's text passed to the index. `-` is NOT in RediSearch's query language, so
# `kube-state-metrics` passed through raw is a NEGATION of the words being searched for -- and it
# would fail as an empty result, which is this product's honest negative, the worst available
# failure mode. The query is REBUILT from alphanumeric subterms, so no user byte reaches the
# query language and no escaping is needed.
_NAME_SPLIT = re.compile(r"[-._/]")
_NAME_TOKEN = re.compile(r"[a-z0-9]+")

# RediSearch's documented default English stop words. Listed rather than inferred because a term
# the index silently dropped must not count toward the two-term floor below, or the floor
# measures something the engine did not do.
_NAME_STOP = frozenset((
    "a", "is", "the", "an", "and", "are", "as", "at", "be", "but", "by", "for", "if", "in",
    "into", "it", "no", "not", "of", "on", "or", "such", "that", "their", "then", "there",
    "these", "they", "this", "to", "was", "will", "with",
))

# The column order HAS_THIS_BEEN_TRIED returns, named rather than counted. This tuple exists
# because eval_retrieval.py read the distance as `rows[0][-1]`, which is right for twelve columns
# and silently wrong for thirteen -- and it gates preflight AND CI.
HAS_THIS_BEEN_TRIED_COLUMNS = (
    "rejected_idea", "rationale", "kep", "kep_title", "status", "sig", "source_url",
    "years_ago", "deciders", "decider_live_roles", "rationale_ownership", "distance",
    "found_by",
)
DIST_COL = HAS_THIS_BEEN_TRIED_COLUMNS.index("distance")

# How many bodies a name may match before this path refuses to report it. This is the name path's
# `max_dist`, and it is the whole reason the path is safe: a two-term conjunction over an
# 1,800-character argument is not a name match, it is two words that both occur somewhere.
# Measured document frequencies over the 206: (kube state metrics) 2, (cgroup v1) 2,
# (client go) 3, (out tree) 4, (kube proxy) 5, (control plane) 5, (pod level) 10.
# The sixth line is the one that matters: `rewrite the control-plane in COBOL on a mainframe` is
# eval_retrieval.py's first negative control with one hyphen added, and without this bound it
# returns unrelated rejections -- turning the claim that this product says NOTHING when it knows
# nothing into a false positive. The count is taken by the ENGINE: the query asks for
# NAME_HIT_BOUND + 1 rows and the lot is discarded if it comes back full.
NAME_HIT_BOUND = 3


def searchable_names(text: str) -> list[list[str]]:
    """The names in `text` that this engine's tokeniser would split, as term lists.

    The rule is lexical and has one justification, from docs.falkordb.com's full-text page:
    indexed text "is split on whitespace and punctuation". So a whitespace-delimited word
    containing `-` `.` `_` or `/` is exactly a word the index stores as several terms and a
    sentence embedding cannot keep whole. There is no list of interesting words anywhere here.

    ALL-CAPS and camelCase are deliberately NOT in the rule -- not as tuning, but because the
    tokeniser does not split them, so they are out by the same sentence. That exclusion is
    load-bearing: `API` alone appears in 65 of the 206 bodies.

    Subterms shorter than two characters are dropped, which is also the tokeniser's doing: `e.g.`
    splits to `e` and `g`, which co-occur in 19 of the 206. `v1.28` survives as (v1 28) and finds
    nothing, which is the right outcome rather than a special case.
    """
    out: list[list[str]] = []
    seen: set[tuple[str, ...]] = set()
    for word in (text or "").split():
        if not _NAME_SPLIT.search(word):
            continue
        parts = [p for p in _NAME_TOKEN.findall(word.lower())
                 if len(p) >= 2 and p not in _NAME_STOP]
        if len(parts) < 2:
            continue
        key = tuple(parts)
        if key not in seen:
            seen.add(key)
            out.append(parts)
    return out


def fulltext_query(names: list[list[str]]) -> str:
    """Term lists -> one RediSearch query string, built from alphanumerics only.

    `(kube state metrics)|(cgroup v1)`: a space is AND, `|` is OR, parentheses disambiguate.
    Nothing from the user's text survives into this string except [a-z0-9] tokens, which is why
    there is no escaping: the dialect-dependent meaning of `-` cannot arise from characters that
    cannot get here.
    """
    return "|".join("(" + " ".join(p) + ")" for p in names)


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

    def _coverage(self, similarity: bool = False, by_name: bool = False) -> dict:
        """What the graph actually contains, so a negative can be read honestly.

        `similarity` is set by the one tool that answers through the vector index. It matters
        because the honest negative used to say "958 rejected alternatives indexed" to someone
        whose question had been compared against 752 of them -- the index is minted on
        :NamedOption, and "indexed" was precisely the word that was false for the other 206.
        Overstating the haystack by 27% in the sentence whose entire job is to say what was
        searched is a worse failure than any wrong answer, because it is the sentence a judge is
        told to trust when the product comes back empty.
        """
        rows, _ = self._run(
            "coverage",
            """
            MATCH (k:Kep) WITH count(k) AS keps
            MATCH (a:Alternative) WITH keps, count(a) AS alts
            MATCH (n:NamedOption) WITH keps, alts, count(n) AS searchable
            MATCH (p:Person) WITH keps, alts, searchable, count(p) AS people
            MATCH (o:OwnersFile) WITH keps, alts, searchable, people, count(o) AS owners
            MATCH (m:MissingRecord)
            RETURN keps, alts, searchable, people, owners, count(m) AS missing
            """,
            {},
        )
        if not rows:
            return {}
        k, a, sch, p, o, m = rows[0]
        out = {"decisions_indexed": k}
        if similarity:
            # What this tool actually compared the question against, and then the whole set, so
            # the gap is visible rather than averaged into one flattering number.
            out["rejected alternatives searched by similarity"] = sch
            if by_name:
                # The 206 now carry a full-text index, but it is only consulted when the question
                # contains a name the tokeniser would split. Claiming they were searched on a
                # question that named nothing would be the identical overclaim one index to the
                # right -- the wording changes, the number does not.
                out["more searched by name in the text index"] = a - sch
            else:
                out["more rejected alternatives in the graph, searchable only by a name this "
                    "question did not contain"] = a - sch
        else:
            out["rejected_alternatives_in_graph"] = a
        out.update({
            "people": p,
            "ownership_files": o,
            "missing_decision_records": m,
            "corpus": "kubernetes/enhancements + kubernetes/kubernetes OWNERS",
            "caveat": "An empty result means this corpus does not record it. It is not proof it never happened.",
        })
        return out

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
// Seven titles in this corpus are section headings the extractor lifted as if they were options
// -- 'Pros', 'Cons', 'Pros/Cons' and friends, twelve nodes in all. They are embedded, so a vague
// question reaches them: "what are the tradeoffs here" answered with 'Pros/Cons', a heading
// dressed as a rejected idea. Excluded by name rather than by pattern, because ACL, API and VPA
// are three letters long and are real options. Re-extracting the corpus is the proper fix and is
// not a thing to start two days from a deadline.
WITH alt, score
WHERE NOT alt.title IN ['Cons', 'Cons:', 'Not', 'Other Solutions:', 'Pros', 'Pros/Cons', 'Pros:']
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
       round(score * 1000) / 1000            AS distance,
       'similarity'                          AS found_by
ORDER BY score ASC
LIMIT $limit
"""

    # ---------- TOOL 1, second query ----------
    # The same twelve columns as HAS_THIS_BEEN_TRIED plus `found_by`, so one answer can carry rows
    # from both retrievers and every consumer reading a column by position keeps working:
    # memory.py's _link reads r[2] and r[8], the age test reads r[7], headline() reads r[11].
    #
    # `distance` is NULL on these rows, and that is not laziness. The vector index returns a
    # cosine DISTANCE where lower is better; this index returns a TF-IDF score where HIGHER is
    # better. Putting two numbers that point in opposite directions in one column would let any
    # ORDER BY, any min(), and any renderer printing "closest" produce a confident wrong answer.
    #
    # LIMIT is $cap, not $limit, and the caller passes NAME_HIT_BOUND + 1. Asking for one more
    # row than may be reported is what lets the ENGINE do the counting: if the query comes back
    # full, the name matched too much of the corpus to be a name, and the result is dropped.
    HAS_THIS_BEEN_TRIED_BY_NAME = """
CALL db.idx.fulltext.queryNodes('UnnamedOption', $q) YIELD node AS alt, score
WITH alt, score
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
       null                                  AS distance,
       'name'                                AS found_by
ORDER BY score DESC
LIMIT $cap
"""

    def has_this_been_tried(self, qvec: list, k: int = 8, max_dist: float = 0.45,
                            limit: int = 5, names: list | None = None) -> Answer:
        """Has this idea been proposed and rejected before, and is anyone left who knows why?

        Two retrievers over two disjoint sets of options, and the answer says which found each row.

        `names` is appended to this signature rather than inserted into it, on purpose: three
        callers pass `qvec` positionally, and inserting a parameter ahead of `k` would silently
        rebind it for anyone who ever passes k positionally.
        """
        params = {"qvec": qvec, "k": k, "maxDist": max_dist, "limit": limit,
                  "now": self.now_ms, "msYear": MS_PER_YEAR}
        rows, ms = self._run("has_this_been_tried", self.HAS_THIS_BEEN_TRIED, params)
        cypher = self.HAS_THIS_BEEN_TRIED
        shown = {"k": k, "max_dist": max_dist, "limit": limit}

        # The name path runs second and its rows go underneath, so rows[0] is still the
        # nearest-by-distance row for every caller that reads it. A retriever that can only answer
        # when it has literal evidence may add to an answer; it may not decide what it leads with.
        nq = fulltext_query(names or [])
        if nq:
            shown["name_query"] = nq
            shown["name_bound"] = NAME_HIT_BOUND
            try:
                nrows, nms = self._run(
                    "has_this_been_tried_by_name", self.HAS_THIS_BEEN_TRIED_BY_NAME,
                    {"q": nq, "cap": NAME_HIT_BOUND + 1,
                     "now": self.now_ms, "msYear": MS_PER_YEAR},
                )
            except Exception:
                # A missing index is a missing capability, not a failed answer. Reported in the
                # arguments rather than swallowed, because an answer that quietly stopped
                # consulting one of its two indexes is the kind of thing nobody notices.
                nrows, nms = [], 0.0
                shown["name_index"] = "unavailable"
            ms += nms
            shown["name_hits"] = len(nrows)
            if 0 < len(nrows) <= NAME_HIT_BOUND:
                rows = list(rows) + list(nrows)
                cypher = (self.HAS_THIS_BEEN_TRIED.rstrip() + "\n\n// --- and, for the names in "
                          "the question, the text index over the options the vector index cannot "
                          "see ---\n" + self.HAS_THIS_BEEN_TRIED_BY_NAME.lstrip())
            elif len(nrows) > NAME_HIT_BOUND:
                # Said out loud in the arguments the UI prints. "Your name matched too much of
                # this corpus to be a name" is a real answer about a real limit.
                shown["name_hits"] = f">{NAME_HIT_BOUND}"

        if not rows:
            return Answer("NOT_IN_GRAPH", "has_this_been_tried",
                          coverage=self._coverage(similarity=True, by_name=bool(nq)), ms=ms,
                          cypher=cypher, params=shown,
                          note="No recorded rejected alternative within the distance threshold.")
        return Answer("ANSWERED_WITH_PATH", "has_this_been_tried", rows=rows, ms=ms,
                      cypher=cypher, params=shown)

    # ---------- TOOL 2 ----------
    # NOTE: this query replaced an earlier, WRONG one.
    #
    # The first version claimed a directory was "orphaned" when every approver in its own OWNERS
    # file had departed. That is false. Kubernetes OWNERS files INHERIT: prow treats a directory
    # as covered by its own approvers PLUS every ancestor's, unless an OWNERS on the way up sets
    # `options.no_parent_owners`. Checked against kubernetes.dev/docs/guide/owners: ALL seven
    # directories I called orphaned are in fact covered by an ancestor. Zero are unowned.
    #
    # The true finding is both correct and more interesting: those directories lost every
    # DEDICATED approver, so approval silently falls back to a broader group who never
    # specifically owned that code. That is expertise dilution, and computing it requires
    # walking up the tree -- a traversal, not a lookup.
    OWNERSHIP_DILUTION = """
// 1. areas where every dedicated approver has departed
MATCH (departed:Person)-[:EMERITUS_OF]->(area:OwnersFile)
OPTIONAL MATCH (own:Person)-[:APPROVES]->(area)
WITH area, collect(DISTINCT departed.key) AS departed_owners, count(DISTINCT own) AS own_live
WHERE own_live = 0

// 2. walk UP the OWNERS tree to the nearest ancestor that still has live approvers
MATCH path = (area)-[:INHERITS_FROM*1..8]->(anc:OwnersFile)
MATCH (fb:Person)-[:APPROVES]->(anc)
WITH area, departed_owners, anc, length(path) AS up, count(DISTINCT fb) AS n_fb
ORDER BY up ASC
WITH area, departed_owners,
     collect({path: anc.path, up: up, n: n_fb})[0] AS nearest

RETURN area.path             AS area,
       departed_owners,
       size(departed_owners) AS n_departed,
       nearest.path          AS approval_falls_back_to,
       nearest.up            AS levels_up,
       nearest.n             AS fallback_approvers,
       area.url              AS source_url
ORDER BY fallback_approvers ASC, n_departed DESC
LIMIT $limit
"""

    def ownership_dilution(self, limit: int = 20) -> Answer:
        """Which areas lost every dedicated owner, and who inherits them now?

        Not "unowned" -- almost nothing in Kubernetes is literally unowned. This is the real
        failure: the people who specifically owned a directory have all gone, and approval now
        falls back to a broader group who never signed up for that code. The fallback is found by
        walking the OWNERS tree, so it is a traversal a lookup cannot do.
        """
        rows, ms = self._run("ownership_dilution", self.OWNERSHIP_DILUTION, {"limit": limit})
        shape = "ANSWERED_WITH_PATH" if rows else "NOT_IN_GRAPH"
        return Answer(shape, "ownership_dilution", rows=rows, ms=ms,
                      params={"limit": limit},
                      cypher=self.OWNERSHIP_DILUTION, coverage=self._coverage())

    # ---------- TOOL 3 ----------
    DEPARTED_BRIDGES = """
CALL algo.betweenness({nodeLabels:['Person'], relationshipTypes:['CO_AUTHORED'], samplingSeed: $seed})
YIELD node, score
WITH node AS p, score AS bridge
MATCH (p)-[:EMERITUS_OF]->(f:OwnersFile)
OPTIONAL MATCH (p)-[liveRole:APPROVES]->()
WITH p, bridge, count(DISTINCT f) AS abandoned_areas, count(liveRole) AS live_roles
WHERE live_roles = 0 AND abandoned_areas >= $minAreas
RETURN p.key                        AS stepped_back_bridge,
       round(bridge * 100) / 100     AS betweenness,
       abandoned_areas
ORDER BY bridge DESC
LIMIT $limit
"""

    def stepped_back_bridges(self, min_areas: int = 3, limit: int = 10, seed: int = 42) -> Answer:
        """Who held the most CONNECTIVE authority before stepping back, not just the most files?

        Betweenness centrality is the point: it is a whole-graph property, so neither a traversal
        nor a vector search can produce it. The seed is pinned because algo.betweenness is sampled
        (samplingSize default 32) and its default seed is time-based, so unseeded runs are not
        reproducible.
        """
        params = {"minAreas": min_areas, "limit": limit, "seed": seed}
        rows, ms = self._run("stepped_back_bridges", self.DEPARTED_BRIDGES, params)
        shape = "ANSWERED_WITH_PATH" if rows else "NOT_IN_GRAPH"
        return Answer(shape, "stepped_back_bridges", rows=rows, ms=ms,
                      cypher=self.DEPARTED_BRIDGES, coverage=self._coverage(),
                      params={"min_areas": min_areas, "limit": limit, "seed": seed},
                      # A row reading 0.00 is the sampled estimate, not a proof of zero: it means
                      # no sampled shortest path happened to run through that person. Saying so
                      # matters because the list is ranked, and a reader meeting 0.00 at the
                      # bottom will otherwise take it as "held no connective authority at all".
                      note="betweenness is sampled (size 32, seed pinned) -- approximate, "
                           "reproducible. 0.00 means no sampled path ran through them, which is "
                           "weaker than a measured zero")

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
                      cypher=self.SUCCESSOR_FOR, params={"handle": resolved, "limit": limit},
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
        tot = self.g.ro_query(
            "MATCH (:Kep)-[r:CITES_MISSING]->(m:MissingRecord) "
            "RETURN count(DISTINCT m), count(r)").result_set[0]
        return Answer(shape, "broken_lineage", rows=rows, ms=ms, cypher=self.BROKEN_LINEAGE,
                      totals={"records": tot[0], "citations": tot[1]},
                      params={"min_cites": min_cites, "limit": limit})

    # ---------- TOOL 6: which GROUP is hollowing out ----------
    HOLLOWING_COMMUNITIES = """
CALL algo.labelPropagation({nodeLabels:['Person'], relationshipTypes:['CO_AUTHORED']})
YIELD node, communityId
WITH communityId, collect(node) AS members, count(node) AS size
WHERE size >= $minSize
UNWIND members AS m
OPTIONAL MATCH (m)-[gone:EMERITUS_OF]->()
OPTIONAL MATCH (m)-[live:APPROVES]->()
WITH communityId, size, m, count(gone) AS g, count(live) AS l
WITH communityId, size,
     sum(CASE WHEN g > 0 AND l = 0 THEN 1 ELSE 0 END) AS stepped_back,
     sum(CASE WHEN l > 0 THEN 1 ELSE 0 END)           AS still_approving,
     collect(CASE WHEN g > 0 AND l = 0 THEN m.key ELSE null END) AS gone_names
WHERE stepped_back > 0
RETURN communityId                                        AS community,
       size,
       stepped_back,
       still_approving,
       round(100.0 * stepped_back / size)                 AS pct_stepped_back,
       [x IN gone_names WHERE x IS NOT NULL][0..5]        AS who_stepped_back
ORDER BY pct_stepped_back DESC, size DESC
LIMIT $limit
"""

    def hollowing_communities(self, min_size: int = 5, limit: int = 8) -> Answer:
        """Which contributor COMMUNITY is losing its people fastest?

        Individual attrition is a traversal. "Which group is hollowing out" is not: the groups
        are not declared anywhere — no SIG membership file produces them — they are discovered by
        running community detection over who has actually worked on decisions together. Label
        propagation partitions that graph, and only then can you ask what fraction of each
        partition still holds authority.

        FalkorDB has no Louvain or Leiden, so label propagation is the available algorithm. It is
        non-deterministic and has no resolution parameter, which is stated in the answer rather
        than hidden.
        """
        params = {"minSize": max(2, min_size), "limit": limit}
        rows, ms = self._run("hollowing_communities", self.HOLLOWING_COMMUNITIES, params)
        shape = "ANSWERED_WITH_PATH" if rows else "NOT_IN_GRAPH"
        return Answer(shape, "hollowing_communities", rows=rows, ms=ms,
                      cypher=self.HOLLOWING_COMMUNITIES,
                      params={"min_size": max(2, min_size), "limit": limit},
                      coverage=self._coverage(),
                      note="Communities are discovered by label propagation over co-authorship, "
                           "not declared. The algorithm is non-deterministic and has no "
                           "resolution parameter — run it twice and boundaries may shift.")

    # ---------- TOOL 7: bus factor ----------
    # ---------- the query behind the one ACTION this agent takes ----------
    # `emeritus_approvers` is Kubernetes' explicit, written record of "this person stepped back
    # from this area". It is PER-AREA, so stepping back from nine areas and keeping a tenth is
    # normal. What this finds is the lopsided shape: a systematic step-back with one straggler
    # still naming them an active approver. That is a question for a human, not a verdict, and
    # the drafting layer in act.py refuses to patch the cases it cannot justify.
    #
    # Vendored trees are excluded IN THE QUERY because they are synced from other repositories.
    # The strongest-looking signal in this corpus is excluded by exactly this line.
    STEPPED_BACK_BUT_STILL_LISTED = """
MATCH (p:Person)-[:EMERITUS_OF]->(e:OwnersFile)
WITH p, collect(DISTINCT e.path) AS stepped_back
WHERE size(stepped_back) >= $min_stepped_back
MATCH (p)-[:APPROVES]->(a:OwnersFile)
WHERE NOT a.path STARTS WITH 'vendor/' AND NOT a.path STARTS WITH 'third_party/'
WITH p, stepped_back, collect(DISTINCT a.path) AS still_listed
WHERE size(still_listed) <= $max_active
RETURN p.key              AS person,
       size(stepped_back) AS stepped_back_in,
       stepped_back[0..5] AS stepped_back_sample,
       still_listed       AS still_listed_in
ORDER BY stepped_back_in DESC, person
LIMIT $limit
"""

    def stepped_back_but_still_listed(self, min_stepped_back: int = 3,
                                      max_active: int = 2, limit: int = 10) -> Answer:
        """Whose ownership record is lopsided: stepped back from many areas, still listed in one?

        This is the finding the `draft_owners_patch` action turns into a reviewable change. On its
        own it asserts nothing: a person may have kept one area deliberately.
        """
        rows, ms = self._run("stepped_back_but_still_listed", self.STEPPED_BACK_BUT_STILL_LISTED,
                             {"min_stepped_back": min_stepped_back, "max_active": max_active,
                              "limit": limit})
        shape = "ANSWERED_WITH_PATH" if rows else "NOT_IN_GRAPH"
        return Answer(shape, "stepped_back_but_still_listed", rows=rows, ms=ms,
                      params={"min_stepped_back": min_stepped_back, "limit": limit},
                      cypher=self.STEPPED_BACK_BUT_STILL_LISTED, coverage=self._coverage())

    SOLE_APPROVER = """
MATCH (p:Person)-[:APPROVES]->(o:OwnersFile)
WITH o, collect(DISTINCT p.key) AS approvers
WHERE size(approvers) = 1
WITH approvers[0] AS sole, collect(o.path) AS areas
RETURN sole                AS only_approver,
       size(areas)         AS areas_held_alone,
       areas[0..5]         AS sample_areas
ORDER BY areas_held_alone DESC, only_approver
LIMIT $limit
"""

    def sole_approver_risk(self, limit: int = 12) -> Answer:
        """Which areas have exactly ONE approver, and who is it?

        No simulation needed: for a single person this is exact. 45 areas in Kubernetes have a
        bus factor of one. The counterfactual engine exists for the COMPOUND case, where coverage
        cascades up the inheritance tree and an exact query stops being a one-liner.
        """
        rows, ms = self._run("sole_approver_risk", self.SOLE_APPROVER, {"limit": limit})
        shape = "ANSWERED_WITH_PATH" if rows else "NOT_IN_GRAPH"
        tot = self.g.ro_query(
            "MATCH (o:OwnersFile)<-[:APPROVES]-(p:Person) "
            "WITH o, collect(DISTINCT p) AS ps WHERE size(ps) = 1 "
            "RETURN count(DISTINCT o), count(DISTINCT ps[0])").result_set[0]
        return Answer(shape, "sole_approver_risk", rows=rows, ms=ms,
                      params={"limit": limit},
                      totals={"areas": tot[0], "people": tot[1]},
                      cypher=self.SOLE_APPROVER, coverage=self._coverage())

    # ---------- TOOL 7: keeping knowledge current ----------
    # NOTE: an earlier version of this query inferred "no living author" from the ABSENCE of an
    # APPROVES edge. That was wrong. 72% of KEP authors appear in no OWNERS file at all, so
    # absence of an approver role mostly means "was never an OWNERS approver", not "has left".
    #
    # This version uses `EMERITUS_OF` as POSITIVE evidence of stepping back, and reports the
    # authors whose status this corpus genuinely does not know, rather than counting them as gone.
    STALE_KNOWLEDGE = """
MATCH (other:Kep)-[:SEE_ALSO|REPLACES]->(k:Kep)
WHERE k.status IN ['provisional', 'implementable']
  AND k.created_ms > 0
  AND ($now - k.created_ms) > $ageMs
WITH k, count(DISTINCT other) AS still_cited_by

MATCH (author:Person)-[:AUTHORED|APPROVED]->(k)
OPTIONAL MATCH (author)-[liveRole:APPROVES]->()
OPTIONAL MATCH (author)-[gone:EMERITUS_OF]->()
WITH k, still_cited_by, author, count(liveRole) AS live, count(gone) AS emeritus
WITH k, still_cited_by,
     count(DISTINCT author)                                     AS authors,
     sum(CASE WHEN live > 0 THEN 1 ELSE 0 END)                   AS with_current_role,
     sum(CASE WHEN emeritus > 0 AND live = 0 THEN 1 ELSE 0 END)  AS verifiably_departed,
     sum(CASE WHEN emeritus = 0 AND live = 0 THEN 1 ELSE 0 END)  AS status_unknown

RETURN k.num                           AS kep,
       k.title                         AS title,
       k.status                        AS status,
       k.sig                           AS sig,
       ($now - k.created_ms) / $msYear AS years_undecided,
       still_cited_by,
       authors,
       with_current_role,
       verifiably_departed,
       status_unknown,
       CASE WHEN with_current_role = 0 AND verifiably_departed > 0 THEN 'AUTHOR_STEPPED_BACK'
            WHEN with_current_role = 0 THEN 'NO_AUTHOR_HOLDS_A_ROLE'
            ELSE 'AUTHOR_STILL_ACTIVE' END AS currency,
       k.url                           AS source_url
ORDER BY with_current_role ASC, verifiably_departed DESC, still_cited_by DESC
LIMIT $limit
"""

    def stale_knowledge(self, min_years: int = 3, limit: int = 10) -> Answer:
        """What does this graph know that is going stale?

        Track 3 asks for "keeping knowledge current". The honest version of that on a real corpus
        is not a freshness timestamp -- it is: which decisions are still being cited by other
        decisions, are still formally undecided years later, AND have no author left who could
        say why. Each of those three alone is noise; together they are a knowledge-decay signal.
        """
        params = {"now": self.now_ms, "ageMs": max(0, min_years) * MS_PER_YEAR,
                  "msYear": MS_PER_YEAR, "limit": limit}
        rows, ms = self._run("stale_knowledge", self.STALE_KNOWLEDGE, params)
        # The population, not the page. Caught by the invariant added for the sole-approver and
        # broken-lineage chips rather than reported: this one also returned a full page of 10 and
        # put that 10 in the headline as though it were the count of stale decisions.
        _tot = self.g.ro_query(
            "MATCH (other:Kep)-[:SEE_ALSO|REPLACES]->(k:Kep) "
            "WHERE k.status IN ['provisional', 'implementable'] AND k.created_ms > 0 "
            "  AND ($now - k.created_ms) > $ageMs "
            "RETURN count(DISTINCT k)",
            params={"now": params["now"], "ageMs": params["ageMs"]}).result_set[0][0]
        if not rows:
            return Answer("NOT_IN_GRAPH", "stale_knowledge", ms=ms,
                          cypher=self.STALE_KNOWLEDGE, coverage=self._coverage(),
                          note=f"No decision older than {min_years} years is still being cited "
                               f"while formally undecided.")
        return Answer("ANSWERED_WITH_PATH", "stale_knowledge", rows=rows, ms=ms,
                      cypher=self.STALE_KNOWLEDGE, totals={"decisions": _tot},
                      params={"min_years": min_years, "limit": limit})

    # ---------- TOOL 8: the depth contrast the rubric asks for ----------
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
       CASE WHEN size(live_approvers) = 0 THEN 'NO_DEDICATED_OWNER' ELSE 'OWNED' END AS status
LIMIT $limit
"""

    def who_owns(self, path: str, depth: int = 1, limit: int = 20) -> Answer:
        """Same question, two depths. Depth 1 is what any database serves; depth 4 is the graph."""
        resolved = self.resolve_path(path)
        if not resolved:
            return Answer("UNKNOWN_ENTITY", "who_owns",
                          note=f"'{path}' is not an ownership file in this graph. Nothing else was run.",
                          coverage=self._coverage())
        # Only two depths exist: the shallow control and the full traversal. Clamp anything else
        # rather than inventing a third tool name the renderer has never heard of.
        depth = 1 if depth <= 1 else 4
        cypher = self.WHO_OWNS_DEPTH1 if depth == 1 else self.WHO_OWNS_DEPTH4
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
    "ownership_dilution": "Which areas lost every approver with dedicated authority, and which broader group inherits them now? Walks the OWNERS tree. Args: none.",
    "stepped_back_bridges": "Rank people by how much CONNECTIVE authority was concentrated in them before they stepped back from approving (betweenness centrality). Args: min_areas.",
    "successor_for": "Suggest who should inherit a departed person's areas, from co-ownership overlap. Args: handle.",
    "broken_lineage": "List decision records that other decisions cite but which do not exist. Args: min_cites.",
    "who_owns": "Who owns an area. depth=1 gives the approver list; depth=4 adds what the departed owner decided elsewhere. Args: path, depth.",
    "hollowing_communities": "Which contributor community is losing its people fastest? Communities are discovered by label propagation over co-authorship, not declared anywhere. Args: min_size.",
    "sole_approver_risk": "Which areas have exactly ONE approver — a bus factor of one — and who is it? Args: none.",
    "what_if_they_go": "Simulate a group stepping back from approving all at once, and report which areas would be left with no live owner anywhere. Args: handles (list).",
    "stale_knowledge": "What does this graph know that is going stale? Decisions still cited by others, still undecided years later, whose authors have stepped back. Args: min_years.",
    "recall": "Has this graph been asked something like this before, and what did that answer cite? Args: question.",
    "stepped_back_but_still_listed": "Whose ownership record is lopsided — recorded as having stepped back from many areas, yet still named an active approver in one or two? Args: min_stepped_back.",
    "draft_owners_patch": "ACT: turn that finding into a reviewable OWNERS patch that retires the straggler entry, refusing the cases it cannot justify (vendored trees, approval held via an alias) and saying why. Drafts only; sends nothing. Args: min_stepped_back.",
}
