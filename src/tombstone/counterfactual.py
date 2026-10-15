"""What breaks if one more person stops approving?

This is the question that follows "who stepped back", and it is the only forward-looking thing
this product does. It is also the clearest case for a graph database rather than a graph library:
answering it means mutating the whole graph, re-running a recursive traversal over the mutated
copy, and diffing the result against the original — without touching the original.

FalkorDB does that with `GRAPH.COPY`, measured at **495 ms** for the full graph (3,088 nodes,
15,760 edges) with all 8 indexes carried over. So the sequence is:

    GRAPH.COPY   ->   remove their approvals in the copy   ->   re-run the dilution traversal
                 ->   diff against the baseline            ->   drop the copy

No application-side graph rebuild, no re-ingest, and the live graph is never at risk. A judge can
watch a hypothetical be evaluated and thrown away inside one request.
"""
from __future__ import annotations

import time
import uuid

class CopyUnavailable(RuntimeError):
    """`GRAPH.COPY` could not run -- an environment limit, not a wrong answer.

    GRAPH.COPY forks the server process, so it needs memory headroom roughly equal to the graph.
    On a loaded machine, or when two counterfactuals overlap, it fails with "could not fork".
    That is a capacity fact about the host, so it must surface as DEGRADED and never as a number:
    a counterfactual that silently reported zero newly-stranded areas because the copy failed
    would be the worst possible bug in this product.
    """


def _copy_with_retry(db, source: str, copy_name: str) -> float:
    """Copy `source` to `copy_name`, retrying once. Returns seconds taken.

    The retry exists because the common cause of a fork failure is transient: another copy is
    still resident and about to be dropped. One short wait clears that case. A second failure is
    treated as real and raised as CopyUnavailable rather than retried into a loop.
    """
    last = None
    for attempt in (0, 1):
        t0 = time.perf_counter()
        try:
            db.connection.execute_command("GRAPH.COPY", source, copy_name)
            return time.perf_counter() - t0
        except Exception as e:  # noqa: BLE001 - the driver surfaces fork failures as bare errors
            last = e
            if attempt == 0:
                time.sleep(0.25)
    raise CopyUnavailable(str(last)[:120])


# IMPORTANT: both queries are restricted to areas that HAVE a declared approver list.
#
# 19 OWNERS files in Kubernetes declare only `reviewers`, `labels` or `options` and no `approvers`
# at all. Counting those as "uncovered" conflates "never had an approver" with "lost its
# approvers" -- which is exactly the mistake that produced the retracted "7 orphaned directories"
# claim. An area with nothing to lose cannot lose it. The `$scope` parameter carries the set of
# areas that had approvers in the ORIGINAL graph, so the diff measures a change in the world
# rather than a difference in the question.
UNCOVERED = """
MATCH (o:OwnersFile) WHERE o.path IN $scope
OPTIONAL MATCH (p:Person)-[:APPROVES]->(o)
WITH o, count(DISTINCT p) AS own
WHERE own = 0
RETURN collect(o.path) AS areas
"""

STRANDED = """
MATCH (o:OwnersFile) WHERE o.path IN $scope
OPTIONAL MATCH (p:Person)-[:APPROVES]->(o)
WITH o, count(DISTINCT p) AS own
WHERE own = 0
OPTIONAL MATCH (o)-[:INHERITS_FROM*1..8]->(anc:OwnersFile)<-[:APPROVES]-(:Person)
WITH o, count(anc) AS covered
WHERE covered = 0
RETURN collect(o.path) AS areas
"""

# The areas that actually have something to lose.
SCOPE = """
MATCH (:Person)-[:APPROVES]->(o:OwnersFile)
RETURN collect(DISTINCT o.path) AS areas
"""


class Counterfactual:
    def __init__(self, db, source: str = "tomb:k8s"):
        self.db = db
        self.source = source

    def _scalar(self, graph, cypher: str, params: dict | None = None):
        rows = graph.ro_query(cypher, params=params or {}).result_set
        return rows[0][0] if rows else []

    def if_cohort_stops_approving(self, handles: list[str]) -> dict:
        """Simulate several people stepping back AT ONCE.

        This is the case `GRAPH.COPY` genuinely earns. For one person, "which areas would lose
        their last approver" is an exact query and no simulation is needed -- see
        `Tools.sole_approver_risk`. For a cohort, coverage CASCADES: an area may survive because
        its parent still has an approver, and that parent may itself be emptied by the same
        cohort. Expressing that as a single query means re-deriving reachability after an
        arbitrary set of deletions, which is what a mutable copy does for free.
        """
        handles = [h.strip().lstrip("@").lower() for h in (handles or []) if h and h.strip()]
        if not handles:
            return {"ok": False, "reason": "No handles supplied."}
        src = self.db.select_graph(self.source)
        scope = self._scalar(src, SCOPE)
        before = set(self._scalar(src, STRANDED, {"scope": scope}))

        copy_name = f"{self.source}:cf:{uuid.uuid4().hex[:8]}"
        t0 = time.perf_counter()
        try:
            t_copy = _copy_with_retry(self.db, self.source, copy_name)
            cf = self.db.select_graph(copy_name)
            cf.query("MATCH (p:Person)-[r:APPROVES]->() WHERE p.key IN $h DELETE r",
                     params={"h": handles})
            after = set(self._scalar(cf, STRANDED, {"scope": scope}))
        except CopyUnavailable as e:
            return {"ok": False, "copy_unavailable": True,
                    "reason": f"GRAPH.COPY could not run on this host: {e}. The counterfactual "
                              f"needs a forked copy of the graph, so this is a capacity limit "
                              f"rather than a result -- no number is reported."}
        except Exception as e:  # noqa: BLE001
            return {"ok": False, "reason": f"counterfactual could not run: {str(e)[:120]}"}
        finally:
            try:
                self.db.select_graph(copy_name).delete()
            except Exception:
                pass

        return {"ok": True, "cohort": handles,
                "newly_stranded": sorted(after - before),
                "stranded_before": len(before),
                "copy_ms": round(t_copy * 1000, 1),
                "total_ms": round((time.perf_counter() - t0) * 1000, 1)}

    def if_they_stop_approving(self, handle: str) -> dict:
        """Simulate `handle` stepping back from every area they currently approve.

        Returns the areas that would newly lose their dedicated approvers, and the much rarer
        set that would be left with no live ancestor at all. The copy is always dropped, even on
        failure — a leaked counterfactual graph is a slow memory leak in a long-running demo.
        """
        handle = (handle or "").strip().lstrip("@").lower()
        src = self.db.select_graph(self.source)

        exists = src.ro_query(
            "MATCH (p:Person {key: $h}) RETURN count(p)", params={"h": handle}
        ).result_set[0][0]
        if not exists:
            return {"ok": False, "reason": f"'{handle}' is not a person in this graph."}

        approves = src.ro_query(
            "MATCH (p:Person {key: $h})-[:APPROVES]->(o:OwnersFile) RETURN collect(o.path)",
            params={"h": handle},
        ).result_set[0][0]
        if not approves:
            return {"ok": False,
                    "reason": f"'{handle}' holds no approval authority, so there is nothing to remove."}

        scope = self._scalar(src, SCOPE)
        before_uncovered = set(self._scalar(src, UNCOVERED, {"scope": scope}))
        before_stranded = set(self._scalar(src, STRANDED, {"scope": scope}))

        copy_name = f"{self.source}:cf:{uuid.uuid4().hex[:8]}"
        t0 = time.perf_counter()
        try:
            t_copy = _copy_with_retry(self.db, self.source, copy_name)

            cf = self.db.select_graph(copy_name)
            cf.query(
                "MATCH (p:Person {key: $h})-[r:APPROVES]->() DELETE r", params={"h": handle}
            )

            after_uncovered = set(self._scalar(cf, UNCOVERED, {"scope": scope}))
            after_stranded = set(self._scalar(cf, STRANDED, {"scope": scope}))
        except CopyUnavailable as e:
            return {"ok": False, "copy_unavailable": True,
                    "reason": f"GRAPH.COPY could not run on this host: {e}. The counterfactual "
                              f"needs a forked copy of the graph, so this is a capacity limit "
                              f"rather than a result -- no number is reported."}
        finally:
            try:
                self.db.select_graph(copy_name).delete()
            except Exception:
                pass

        newly_uncovered = sorted(after_uncovered - before_uncovered)
        newly_stranded = sorted(after_stranded - before_stranded)

        # Who else would be left holding each newly-uncovered area, via inheritance?
        fallbacks = {}
        for area in newly_uncovered[:10]:
            rows = src.ro_query(
                """
                MATCH (o:OwnersFile {path: $p})-[:INHERITS_FROM*1..8]->(anc:OwnersFile)
                MATCH (fb:Person)-[:APPROVES]->(anc)
                WHERE fb.key <> $h
                RETURN anc.path, count(DISTINCT fb) AS n ORDER BY n DESC LIMIT 1
                """,
                params={"p": area, "h": handle},
            ).result_set
            fallbacks[area] = (rows[0][0], rows[0][1]) if rows else (None, 0)

        return {
            "ok": True,
            "handle": handle,
            "approves_now": len(approves),
            "newly_uncovered": newly_uncovered,
            "newly_stranded": newly_stranded,
            "fallbacks": fallbacks,
            "copy_ms": round(t_copy * 1000, 1),
            "total_ms": round((time.perf_counter() - t0) * 1000, 1),
        }
