"""The agent loop.

Division of labour, which is the whole design:
  - the MODEL picks one tool from a fixed catalogue and fills its arguments. That is all it does.
  - the TOOLS run hand-written parameterised Cypher. No model output is ever concatenated into a
    query.
  - a DETERMINISTIC renderer turns rows into the answer. The model never phrases a finding, so it
    cannot soften a negative into a maybe or invent a name that is not in the graph.

This mirrors the organizer's own guidance ("fix the queries, parameterise them, and let the model
choose between them rather than compose them", "the agent never writes a query") and FalkorDB's
own praise for projects where a deterministic component holds authority over the LLM.

There is no in-memory mirror and no cached fallback. With FalkorDB unreachable the agent returns
DEGRADED and says so, because a product that still works with the database off is decoration.
"""
from __future__ import annotations

import hashlib
import os
import time

from graphkit.ingest import connect
from tombstone.tools import CATALOGUE, Answer, Tools

SYSTEM = """You route questions about an engineering organisation's decision history to exactly one tool.

The graph holds Kubernetes' own governance record: enhancement proposals (decisions), the rejected
alternatives recorded inside them, the people who authored and approved them, and the ownership
files that say who currently approves each area and who has departed.

Pick the single best tool. Do not answer the question yourself -- you cannot see the data.
If the question names a person, pass their GitHub handle as `handle`.
If it names a file or directory path, pass it as `path`.
If it describes a design idea, pass the idea text as `idea_text`."""


def query_sha(cypher: str) -> str:
    """Stamp every answer with a hash of the query that produced it, so the README's query
    catalogue is verifiably the thing that ran rather than a retelling."""
    return hashlib.sha256(" ".join((cypher or "").split()).encode()).hexdigest()[:12]


class Agent:
    def __init__(self, graph_name: str = "tomb:k8s", now_ms: int | None = None, embedder=None):
        self.graph_name = graph_name
        self.now_ms = now_ms or int(time.time() * 1000)
        self._embedder = embedder
        self._provider = None
        self.connect_error: str | None = None
        # Connect defensively. With the database gone this product has nothing to do, but it
        # should say so in a sentence rather than raise out of a constructor.
        try:
            self.db = connect()
            self.g = self.db.select_graph(graph_name)
            self.tools = Tools(self.g, self.now_ms)
        except Exception as e:
            self.db = self.g = self.tools = None
            self.connect_error = str(e)[:200]

    # ---- lazily loaded so the CLI starts fast and a keyless demo still works ----
    def embedder(self):
        if self._embedder is None:
            from fastembed import TextEmbedding
            self._embedder = TextEmbedding(model_name="BAAI/bge-small-en-v1.5")
        return self._embedder

    def provider(self):
        if self._provider is None:
            from tombstone.llm import Provider
            self._provider = Provider()
        return self._provider

    def _reconnect(self) -> bool:
        """Try to re-establish a dropped connection.

        Without this, an instance that happened to start while FalkorDB was briefly unavailable
        would stay broken forever, because the agent is cached per process. A judge clicking
        during a restart would get a permanently dead site.
        """
        try:
            self.db = connect()
            self.g = self.db.select_graph(self.graph_name)
            self.tools = Tools(self.g, self.now_ms)
            self.connect_error = None
            return True
        except Exception as e:
            self.db = self.g = self.tools = None
            self.connect_error = str(e)[:200]
            return False

    def health(self) -> dict:
        """Used by the UI's kill switch: is the graph actually there?"""
        if self.g is None and not self._reconnect():
            return {"falkordb": "down", "error": self.connect_error or "not connected"}
        try:
            t0 = time.perf_counter()
            self.g.ro_query("RETURN 1")
            return {"falkordb": "up", "ms": round((time.perf_counter() - t0) * 1000, 2),
                    "graph": self.graph_name}
        except Exception as e:
            # The socket died after a good start. Try once to pick it back up before reporting down.
            if self._reconnect():
                try:
                    t0 = time.perf_counter()
                    self.g.ro_query("RETURN 1")
                    return {"falkordb": "up", "ms": round((time.perf_counter() - t0) * 1000, 2),
                            "graph": self.graph_name, "reconnected": True}
                except Exception:
                    pass
            return {"falkordb": "down", "error": str(e)[:200]}

    def dispatch(self, tool: str, args: dict) -> Answer:
        """Run one tool by name. Unknown names are refused, never guessed."""
        if tool not in CATALOGUE:
            return Answer("UNKNOWN_ENTITY", tool,
                          note=f"'{tool}' is not a tool in this catalogue. Nothing was run.")
        if self.tools is None and not self._reconnect():
            return Answer("DEGRADED", tool,
                          note="FalkorDB is unreachable, so there is nothing to reason over. "
                               "There is no fallback by design — no in-memory mirror, no cached "
                               "answers.")
        def num(v, default, cast=int):
            """A malformed argument is a bad request, not a graph failure."""
            try:
                return cast(v)
            except (TypeError, ValueError):
                return default

        try:
            if tool == "has_this_been_tried":
                text = args.get("idea_text") or args.get("text") or ""
                if not text.strip():
                    return Answer("UNKNOWN_ENTITY", tool, note="No idea text supplied.")
                qvec = list(self.embedder().embed([text]))[0].tolist()
                return self.tools.has_this_been_tried(
                    qvec, max_dist=num(args.get("max_dist", 0.45), 0.45, float))
            if tool == "orphaned_ownership":
                return self.tools.orphaned_ownership()
            if tool == "departed_bridges":
                return self.tools.departed_bridges(min_areas=max(0, num(args.get("min_areas", 3), 3)))
            if tool == "successor_for":
                return self.tools.successor_for(args.get("handle") or "")
            if tool == "broken_lineage":
                return self.tools.broken_lineage(min_cites=max(1, num(args.get("min_cites", 1), 1)))
            if tool == "who_owns":
                return self.tools.who_owns(args.get("path") or "", depth=num(args.get("depth", 4), 4))
        except Exception as e:
            # Fail loudly. No cached answer, no in-memory mirror.
            msg = str(e)
            unreachable = any(
                t in msg.lower()
                for t in ("connection refused", "connection error", "timeout", "connection reset",
                          "cannot connect", "error 61", "broken pipe")
            )
            if unreachable:
                return Answer(
                    "DEGRADED", tool,
                    note="FalkorDB is unreachable, so there is nothing to reason over. "
                         "There is no fallback by design — no in-memory mirror, no cached answers. "
                         f"({msg[:90]})",
                )
            return Answer("DEGRADED", tool, note=f"The graph query could not complete: {msg[:220]}")
        return Answer("UNKNOWN_ENTITY", tool, note="Tool matched no handler.")

    def ask(self, question: str) -> dict:
        """Full loop: model routes, Cypher answers, renderer phrases it."""
        h = self.health()
        if h.get("falkordb") != "up":
            return {"shape": "DEGRADED", "question": question,
                    "answer": "FalkorDB is unreachable, so this agent has nothing to reason over. "
                              "There is no fallback by design.",
                    "health": h}
        try:
            choice = self.provider().choose_tool(SYSTEM, question, CATALOGUE)
        except Exception as e:
            return {"shape": "DEGRADED", "question": question,
                    "answer": f"Tool routing failed: {str(e)[:220]}", "health": h}

        ans = self.dispatch(choice["tool"], choice.get("args", {}))
        return {
            "question": question,
            "routed_to": choice["tool"],
            "routed_args": choice.get("args", {}),
            "shape": ans.shape,
            "answer": render(ans),
            "rows": ans.rows,
            "coverage": ans.coverage,
            "note": ans.note,
            "ms": ans.ms,
            "query_sha": query_sha(ans.cypher),
            "cypher": ans.cypher,
        }


def render(a: Answer) -> str:
    """Deterministic phrasing. The model is never asked to describe what the graph returned."""
    if a.shape == "UNKNOWN_ENTITY":
        return a.note or "That name does not resolve in this graph, so nothing was run."
    if a.shape == "DEGRADED":
        return a.note or "The query could not complete."
    if a.shape == "NOT_IN_GRAPH":
        cov = a.coverage or {}
        scope = ", ".join(
            f"{v} {k.replace('_', ' ')}" for k, v in cov.items() if isinstance(v, int)
        )
        head = a.note or "Nothing in this graph matches that."
        # The caveat is NOT optional. A tool-specific note adds precision; it never replaces the
        # statement of what was actually searched, because an empty traversal only means this
        # corpus does not record it.
        return (
            head
            + (f"\n\nSearched: {scope}." if scope else "")
            + "\nAn empty traversal means this corpus does not record it — that is not proof it never happened."
        )

    t = a.tool
    n = len(a.rows)
    if t == "has_this_been_tried":
        lines = []
        for r in a.rows:
            idea, rationale, kep, title, status, sig, url, years, deciders, live, own, dist = r
            when = "date not recorded" if years is None or years < 0 else f"{years}y ago"
            lines.append(
                f"• “{idea}” — rejected in KEP-{kep} ({status}, {sig}, {when})\n"
                f"  reason: {str(rationale)[:220]}\n"
                f"  decided by: {', '.join(deciders) if deciders else 'unrecorded'} "
                f"[{'no one who made this call still approves anything' if own == 'NO_LIVING_OWNER' else 'at least one decider is still active'}]\n"
                f"  source: {url}"
            )
        return f"Yes — {n} recorded rejection(s) of something close to this:\n\n" + "\n\n".join(lines)
    if t == "orphaned_ownership":
        lines = [f"• {r[0]} — last known owners: {', '.join(r[1])}" for r in a.rows]
        return (f"{n} area(s) have NO current approver at all, only departed ones:\n\n"
                + "\n".join(lines))
    if t == "departed_bridges":
        lines = [f"• {r[0]} — betweenness {r[1]}, left {r[2]} area(s) behind" for r in a.rows]
        return ("Ranked by how much CONNECTIVE knowledge left with them (betweenness centrality "
                "over the co-authorship graph, sampled, seed pinned):\n\n" + "\n".join(lines))
    if t == "successor_for":
        lines = [f"• {r[0]} already approves {r[1]} of their {r[2]} abandoned areas "
                 f"(owns {r[3]} overall)" for r in a.rows]
        return "Most-overlapping current approvers:\n\n" + "\n".join(lines)
    if t == "broken_lineage":
        lines = [f"• {r[0]} — cited by {r[1]} decision(s): {', '.join(str(x) for x in r[2])}"
                 for r in a.rows]
        return (f"{n} cited decision record(s) do not exist:\n\n" + "\n".join(lines))
    if t == "who_owns(depth=1)":
        lines = [f"• {r[0]} approves {r[1]}" for r in a.rows]
        return f"Current approvers ({n}):\n" + "\n".join(lines)
    if t == "who_owns(depth=4)":
        area = a.rows[0][0] if a.rows else "?"
        live = a.rows[0][1] if a.rows else []
        status = a.rows[0][7] if a.rows else "?"
        head = (f"{area} is {status}."
                + (f" Current approvers: {', '.join(live)}." if live
                   else " There are no current approvers at all."))
        lines = []
        for r in a.rows:
            _, _, departed, ndec, decisions, ideas, sigs, _ = r
            if not departed:
                continue
            bit = f"• {departed} (departed) shaped {ndec} decision(s)"
            if decisions:
                bit += f": KEP-{', KEP-'.join(str(d) for d in decisions)}"
            if ideas:
                bit += f"\n    and personally rejected: “{ideas[0]}”"
            if sigs:
                bit += f"\n    reaching into: {', '.join(sigs)}"
            lines.append(bit)
        return head + ("\n\n" + "\n".join(lines) if lines else "")
    return f"{n} row(s): " + "; ".join(str(r) for r in a.rows[:5])
