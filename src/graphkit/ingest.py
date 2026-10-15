"""Fast FalkorDB ingest.

The whole point of this module is one measured fact: creating edges by matching nodes on an
indexed property runs at ~3,000 edges/sec, while creating them by internal node id runs at
~222,000 edges/sec -- a 73x difference. GRAPH.EXPLAIN shows why: `NodeByIdSeek` is an O(1)
offset lookup, `Node By Index Scan` is a B-tree probe per row.

So every ingest here is two-phase:
  1. create nodes with UNWIND, and keep the business_key -> internal id map in process memory
  2. create edges by internal id only

Two further measured constraints are baked in:
  - batches must stay around 1,000. The planner builds a Cartesian Product per row, so a
    batch of 10,000 collapses to ~378 edges/sec -- 8x SLOWER than batch=1,000.
  - a single `MATCH (n) RETURN ...` silently truncates at RESULTSET_SIZE (default 10,000)
    with no error, so id maps are always read back paginated.
"""
from __future__ import annotations

import os
from typing import Any, Iterable, Iterator, Sequence

from falkordb import FalkorDB

BATCH = 1000          # measured optimum; do not raise, it gets slower
READ_PAGE = 5000      # stay under RESULTSET_SIZE


def connect(host: str | None = None, port: int | None = None) -> FalkorDB:
    """Connect to FalkorDB.

    Defaults to port 6380, not 6379: a local Homebrew `redis-server` commonly owns 6379 and
    silently shadows Docker's published port, which surfaces as
    `ResponseError: unknown command 'GRAPH.QUERY'`.
    """
    return FalkorDB(
        host=host or os.environ.get("FALKORDB_HOST", "localhost"),
        port=int(port or os.environ.get("FALKORDB_PORT", 6380)),
    )


def expand_aliases(names: Iterable[str], alias_table: dict[str, list[str]]) -> list[str]:
    """Expand group aliases to real handles; pass real handles through unchanged.

    Kubernetes OWNERS files reference group aliases such as `sig-api-machinery-approvers`
    rather than people, and the expansion table lives in a separate OWNERS_ALIASES file.
    Skipping this silently turns 8% of a `Person` population into groups and understates
    ownership by several hundred edges, so it is not optional.
    """
    out: list[str] = []
    for n in names:
        if not isinstance(n, str):
            continue
        h = n.strip().lstrip("@").lower()
        if not h:
            continue
        out.extend(alias_table.get(h, [h]))
    return out


def is_bot(handle: str) -> bool:
    h = handle.lower()
    return h.endswith("[bot]") or h.endswith("-bot") or "prow" in h or h in {"k8s-ci-robot"}


def chunked(rows: Sequence[Any], size: int = BATCH) -> Iterator[Sequence[Any]]:
    for i in range(0, len(rows), size):
        yield rows[i : i + size]


class Ingestor:
    """Two-phase loader for one graph. Holds the key -> internal id map for each label."""

    def __init__(self, graph, drop: bool = False):
        self.g = graph
        self.ids: dict[str, dict[Any, int]] = {}
        if drop:
            try:
                self.g.delete()
            except Exception:
                pass

    # ---- phase 1: nodes -------------------------------------------------
    def nodes(self, label: str, rows: Sequence[dict], key: str = "key") -> dict[Any, int]:
        """Create :label nodes from `rows` and return {row[key]: internal id}.

        Every row must carry `key`. Properties are set from the rest of the row, so all rows
        for a label should share a shape.
        """
        if not rows:
            self.ids.setdefault(label, {})
            return self.ids[label]

        props = [k for k in rows[0] if k != key]
        set_clause = ", ".join([f"{key}: r.{key}"] + [f"{p}: r.{p}" for p in props])
        q = f"UNWIND $rows AS r CREATE (:{label} {{{set_clause}}})"
        for batch in chunked(rows):
            self.g.query(q, params={"rows": list(batch)})

        self.g.query(f"CREATE INDEX FOR (n:{label}) ON (n.{key})")
        self.ids[label] = self._read_ids(label, key)
        return self.ids[label]

    def _read_ids(self, label: str, key: str) -> dict[Any, int]:
        """Read back key -> id(n), paginated because RESULTSET_SIZE truncates silently."""
        out: dict[Any, int] = {}
        offset = 0
        while True:
            res = self.g.ro_query(
                f"MATCH (n:{label}) RETURN n.{key}, id(n) ORDER BY id(n) SKIP $o LIMIT $l",
                params={"o": offset, "l": READ_PAGE},
            ).result_set
            if not res:
                break
            for k, nid in res:
                out[k] = nid
            if len(res) < READ_PAGE:
                break
            offset += READ_PAGE
        return out

    # ---- phase 2: edges -------------------------------------------------
    def edges(
        self,
        src_label: str,
        rel: str,
        dst_label: str,
        pairs: Iterable[tuple],
        props: bool = False,
    ) -> tuple[int, int]:
        """Create (src)-[:rel]->(dst) edges by INTERNAL ID. Returns (created, skipped).

        `pairs` is (src_key, dst_key) or, when `props`, (src_key, dst_key, {prop: value}).
        Pairs whose endpoints are not in the id map are skipped and counted, never guessed --
        a dangling reference is a finding, not an error to paper over.
        """
        smap = self.ids.get(src_label, {})
        dmap = self.ids.get(dst_label, {})
        rows, skipped = [], 0
        for pair in pairs:
            if props:
                s, d, p = pair
            else:
                (s, d), p = pair, None
            si, di = smap.get(s), dmap.get(d)
            if si is None or di is None:
                skipped += 1
                continue
            row = {"a": si, "b": di}
            if p:
                row["p"] = p
            rows.append(row)

        if not rows:
            return 0, skipped

        if props:
            q = (
                f"UNWIND $rows AS r MATCH (a),(b) WHERE id(a)=r.a AND id(b)=r.b "
                f"CREATE (a)-[e:{rel}]->(b) SET e = r.p"
            )
        else:
            q = (
                f"UNWIND $rows AS r MATCH (a),(b) WHERE id(a)=r.a AND id(b)=r.b "
                f"CREATE (a)-[:{rel}]->(b)"
            )
        for batch in chunked(rows):
            self.g.query(q, params={"rows": list(batch)})
        return len(rows), skipped

    # ---- indexes --------------------------------------------------------
    def vector_index(self, label: str, prop: str, dim: int = 384, metric: str = "cosine") -> None:
        self.g.query(
            f"CREATE VECTOR INDEX FOR (n:{label}) ON (n.{prop}) "
            f"OPTIONS {{dimension: {dim}, similarityFunction: '{metric}'}}"
        )

    def fulltext_index(self, label: str, *props: str) -> None:
        args = ", ".join(f"'{p}'" for p in props)
        self.g.query(f"CALL db.idx.fulltext.createNodeIndex('{label}', {args})")

    def stats(self) -> dict:
        labels = [r[0] for r in self.g.ro_query("CALL db.labels()").result_set]
        rels = [r[0] for r in self.g.ro_query("CALL db.relationshipTypes()").result_set]
        counts = {}
        for lb in labels:
            counts[lb] = self.g.ro_query(f"MATCH (n:{lb}) RETURN count(n)").result_set[0][0]
        for rt in rels:
            counts[f"-[:{rt}]->"] = self.g.ro_query(
                f"MATCH ()-[r:{rt}]->() RETURN count(r)"
            ).result_set[0][0]
        return counts
