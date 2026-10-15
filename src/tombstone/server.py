"""HTTP surface for Tombstone.

Two design choices worth stating:

1. `/api/ask` routes through the LLM; `/api/tool` calls a named tool directly with no model in the
   loop at all. The demo's scripted questions use `/api/tool`, so a judge can use the live site
   with no API key, no signup, and no cost to anyone -- while the Cypher still executes for real
   against FalkorDB. Nothing is canned: remove the database and every endpoint returns DEGRADED.

2. `/api/subgraph` returns ONLY the nodes and edges on the reasoning path for one answer, never the
   whole graph. A full-graph render is the standard way a graph demo turns into an unreadable
   hairball, and it would also be decoration -- the point is the path, not the cloud.
"""
from __future__ import annotations

import os
import time

from fastapi import FastAPI
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel

from tombstone.agent import Agent, render
from tombstone.tools import CATALOGUE

HERE = os.path.dirname(os.path.abspath(__file__))
WEB = os.path.join(HERE, "..", "..", "web")

app = FastAPI(title="Tombstone", docs_url="/api/docs")
_agent: Agent | None = None
_started = time.time()


def agent() -> Agent:
    global _agent
    if _agent is None:
        _agent = Agent(graph_name=os.environ.get("TOMBSTONE_GRAPH", "tomb:k8s"))
    return _agent


class Ask(BaseModel):
    question: str


class ToolCall(BaseModel):
    tool: str
    args: dict = {}


@app.get("/api/health")
def health():
    a = agent()
    h = a.health()
    if h.get("falkordb") == "up":
        try:
            stats = a.g.ro_query(
                """
                MATCH (k:Kep) WITH count(k) AS keps
                MATCH (n:NamedOption) WITH keps, count(n) AS options
                MATCH (p:Person) WITH keps, options, count(p) AS people
                MATCH (o:OwnersFile) RETURN keps, options, people, count(o) AS owners
                """
            ).result_set[0]
            h["graph_contents"] = dict(
                zip(("decisions", "named_options", "people", "ownership_files"), stats)
            )
        except Exception as e:
            h["graph_contents_error"] = str(e)[:120]
    h["uptime_s"] = round(time.time() - _started, 1)
    h["llm_configured"] = bool(
        os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("OPENAI_API_KEY")
        or os.environ.get("GEMINI_API_KEY") or os.environ.get("GROQ_API_KEY")
    )
    return h


@app.get("/api/tools")
def tools():
    return {"catalogue": CATALOGUE}


@app.post("/api/tool")
def call_tool(c: ToolCall):
    """Direct tool call -- no LLM, no key needed. The Cypher still runs for real."""
    a = agent()
    ans = a.dispatch(c.tool, c.args)
    from tombstone.agent import query_sha
    return {
        "tool": ans.tool,
        "shape": ans.shape,
        "answer": render(ans),
        "rows": ans.rows,
        "coverage": ans.coverage,
        "note": ans.note,
        "ms": round(ans.ms, 2),
        "cypher": ans.cypher.strip(),
        "query_sha": query_sha(ans.cypher),
    }


@app.post("/api/ask")
def ask(q: Ask):
    """Full loop with the model routing. Needs a key."""
    if not health().get("llm_configured"):
        return JSONResponse(
            status_code=503,
            content={
                "shape": "DEGRADED",
                "answer": "No LLM key is configured on this instance, so free-text routing is "
                          "off. The buttons below call the same tools directly and run the same "
                          "Cypher against the same graph.",
                "catalogue": CATALOGUE,
            },
        )
    return agent().ask(q.question)


@app.get("/api/subgraph")
def subgraph(path: str = "", handle: str = "", limit: int = 40):
    """Only the reasoning path for one answer. Never the whole graph."""
    a = agent()
    if a.g is None:
        return {"nodes": [], "edges": [], "error": "FalkorDB unreachable"}
    nodes: dict[str, dict] = {}
    # Dedupe edges. One SQL-ish row per (owner, decision, alternative) means the same
    # owner->area edge is emitted once per alternative; six alternatives produced six identical
    # paths stacked on each other, inflating the edge count without changing the picture.
    edge_set: dict[tuple, dict] = {}

    def link(source, target, label):
        edge_set.setdefault((source, target, label),
                            {"source": source, "target": target, "label": label})

    def add(nid, label, kind, extra=None):
        key = f"{kind}:{nid}"
        if key not in nodes:
            # Graph labels must stay short or the layout's bounding box explodes and the fit
            # zooms out to nothing. The full text stays available in the answer card.
            text = str(label)
            if len(text) > 34:
                text = text[:33].rstrip() + "…"
            nodes[key] = {"id": key, "label": text, "kind": kind,
                          "full": str(label)[:200], **(extra or {})}
        return key

    if path:
        rows = a.g.ro_query(
            """
            MATCH (o:OwnersFile {path: $p})
            OPTIONAL MATCH (live:Person)-[:APPROVES]->(o)
            OPTIONAL MATCH (dep:Person)-[:EMERITUS_OF]->(o)
            OPTIONAL MATCH (dep)-[:AUTHORED|APPROVED]->(k:Kep)-[:CONSIDERED]->(alt:NamedOption)
            RETURN o.path, live.key, dep.key, k.num, k.title, alt.title LIMIT $l
            """,
            params={"p": path, "l": limit},
        ).result_set
        if not rows:
            return {"nodes": [], "edges": [], "note": "no such ownership file"}
        area = add(path, path.replace("/OWNERS", ""), "area")
        for _p, live, dep, knum, ktitle, alttitle in rows:
            if live:
                link(add(live, live, "person_live"), area, "APPROVES")
            if dep:
                d = add(dep, dep, "person_gone")
                link(d, area, "EMERITUS_OF")
                if knum:
                    k = add(knum, f"KEP-{knum}", "decision", {"title": ktitle})
                    link(d, k, "SHAPED")
                    if alttitle and sum(1 for n in nodes.values() if n["kind"] == "rejected") < 6:
                        link(k, add(f"{knum}:{alttitle}", alttitle, "rejected"), "REJECTED")
    elif handle:
        # Deliberately narrow. The full overlap is dozens of people against dozens of areas, and
        # drawing all of it produces exactly the hairball this panel exists to avoid. Show the
        # three strongest successors against the areas they actually share -- the ranked list in
        # the answer already carries the full result.
        rows = a.g.ro_query(
            """
            MATCH (p:Person {key: $h})-[:EMERITUS_OF]->(o:OwnersFile)
            MATCH (cand:Person)-[:APPROVES]->(o)
            WITH cand, collect(DISTINCT o.path) AS shared, count(DISTINCT o) AS n
            ORDER BY n DESC LIMIT 3
            RETURN cand.key, shared[0..3], n
            """,
            params={"h": handle},
        ).result_set
        if not rows:
            return {"nodes": [], "edges": [], "note": "no such person, or they left nothing behind"}
        who = add(handle, handle, "person_gone")
        seen_area = set()
        for cand, shared, n in rows:
            c = add(cand, f"{cand} ({n})", "person_live")
            for areapath in shared:
                ar = add(areapath, areapath.replace("/OWNERS", ""), "area")
                if areapath not in seen_area:
                    seen_area.add(areapath)
                    link(who, ar, "LEFT BEHIND")
                link(c, ar, "ALREADY APPROVES")
    return {"nodes": list(nodes.values()), "edges": list(edge_set.values())}


@app.get("/")
def index():
    return FileResponse(os.path.join(WEB, "index.html"))


@app.get("/app.js")
def appjs():
    return FileResponse(os.path.join(WEB, "app.js"), media_type="application/javascript")


@app.get("/style.css")
def css():
    return FileResponse(os.path.join(WEB, "style.css"), media_type="text/css")
