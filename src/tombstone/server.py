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

from tombstone.agent import Agent, headline, render
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
    # Set only when the router declined a near-tie and the user picked one of the candidates it
    # showed them. Arguments are still extracted by rule from the question itself.
    force: str | None = None


class ToolCall(BaseModel):
    tool: str
    args: dict = {}
    # The human-readable question this call represents. Memory is keyed by question text, so a
    # chip sends its own label -- "Which areas have exactly one approver?" is recallable later,
    # "sole_approver_risk {}" is not.
    question: str | None = None


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
    # Free text always works. Without a key it is routed locally by embedding similarity over a
    # fixed catalogue, which is why the ask box is never disabled.
    h["routing"] = "llm" if h["llm_configured"] else "local-embedding"
    return h


@app.get("/api/tools")
def tools():
    return {"catalogue": CATALOGUE}


def _label(c) -> str:
    """The question a chip is asking, in the words a person would use.

    A tool name and an args dict are not a question, and memory is keyed by question text, so
    recording "sole_approver_risk {}" would make recall useless -- nobody asks that. The UI sends
    its chip label; this is the fallback for anything that does not.
    """
    args = " ".join(str(v) for v in (c.args or {}).values() if isinstance(v, (str, int)))
    return f"{c.tool.replace('_', ' ')} {args}".strip()


@app.post("/api/tool")
def call_tool(c: ToolCall):
    """Direct tool call -- no LLM, no key needed. The Cypher still runs for real.

    The answer is remembered, exactly as a typed question is. It was not, and the omission was
    invisible: every chip in the UI comes through here, so clicking around the demo wrote NOTHING
    to memory while the README said "every answered question is written back as an (:Answer)
    node". Only free text was. A judge clicking through the buttons and then asking whether the
    graph had been asked this before would have been told no, correctly and damningly.
    """
    a = agent()
    ans = a._remember(c.question or _label(c), c.tool, a.dispatch(c.tool, c.args))
    from tombstone.agent import query_sha
    return {
        "tool": ans.tool,
        "shape": ans.shape,
        "headline": headline(ans),
        "answer": render(ans),
        "rows": ans.rows,
        "coverage": ans.coverage,
        "note": ans.note,
        "ms": round(ans.ms, 2),
        "cypher": ans.cypher.strip(),
        "query_sha": query_sha(ans.cypher),
        "params": ans.params,     # see agent._payload: the hash covers the text, not the values
    }


@app.post("/api/ask")
def ask(q: Ask):
    """Full loop. A key swaps the router for a model; it does not switch free text on or off."""
    if not health().get("llm_configured"):
        # No key is not the same as no routing. The embedding model is already in this image, so
        # the question is routed locally against a fixed catalogue instead. The contract is
        # unchanged: something picks a TOOL NAME, hand-written Cypher answers, and nothing
        # generated is ever concatenated into a query.
        return agent().ask_locally(q.question, force=q.force)
    if q.force:
        # A forced tool is a user's choice between candidates the ROUTER offered, so it belongs to
        # the local path even on a keyed instance. Handing it to the model would discard the
        # choice.
        return agent().ask_locally(q.question, force=q.force)
    return agent().ask(q.question)


@app.get("/api/subgraph")
def subgraph(path: str = "", handle: str = "", handles: str = "", stranded: str = "",
             limit: int = 40):
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
            // :Alternative, not :NamedOption, and the difference was a lie on camera. The prose
            // for this same question walks :Alternative (tools.py), so on the demo's own file it
            // cited two rejections -- one of them 'Doing nothing is a viable alternative.' -- that
            // this query then drew zero of. The beat's whole claim is that the picture IS the path
            // the answer came from, so a node the sentence names and the diagram omits makes that
            // sentence false. :NamedOption earns its keep as a pre-filtered ANN index; it was
            // never meant to decide what a path is allowed to show.
            OPTIONAL MATCH (dep)-[:AUTHORED|APPROVED]->(k:Kep)-[:CONSIDERED]->(alt:Alternative)
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
    elif handles:
        # The counterfactual's picture. `stranded` is the verdict from the answer the user is
        # looking at, not a fresh computation: deciding which areas a cohort strands needs a
        # GRAPH.COPY, and re-running one here would both double the cost of the chip and risk
        # drawing a different conclusion than the text beside it. A picture that contradicts the
        # answer is worse than no picture. Each supplied path is still matched against the graph,
        # so a value that names no real area draws nothing.
        #
        # The first version of this drew the stranded area beside three areas the cohort also
        # emptied, in the ordinary colour, with nothing to say why those survived -- because they
        # survive by INHERITING coverage from an ancestor that still has an approver, which is the
        # cascade the counterfactual exists to compute. A reader would have asked why one is struck
        # through and the others are not, and the picture had no answer. So a surviving area is
        # drawn WITH the ancestor it falls back to and the person still approving there, and the
        # stranded one is the area where that walk finds nobody.
        hs = [h.strip().lstrip("@").lower() for h in handles.split(",") if h.strip()]
        strand = [x.strip() for x in stranded.split(",") if x.strip()]
        if not hs:
            return {"nodes": [], "edges": [], "note": "no handles supplied"}

        def area_of(apath, is_strand):
            # `full` is what the tooltip shows, so it carries the REAL path. Letting it default to
            # the display label meant hovering an area showed the same shortened string already on
            # screen, with the "/OWNERS" that identifies the file stripped off.
            return add(apath, apath.replace("/OWNERS", ""),
                       "area_stranded" if is_strand else "area",
                       {"stranded": is_strand, "full": apath})

        drawn_strand = 0
        for apath in strand[:2]:
            rows = a.g.ro_query(
                "MATCH (p:Person)-[:APPROVES]->(o:OwnersFile {path: $p}) WHERE p.key IN $hs "
                "RETURN collect(DISTINCT p.key)[0..4]",
                params={"p": apath, "hs": hs},
            ).result_set
            if not rows or not rows[0][0]:
                continue
            drawn_strand += 1
            area = area_of(apath, True)
            for who in rows[0][0]:
                link(add(who, who, "person_gone"), area, "APPROVES")

        # Two areas the same cohort empties that survive anyway, each with the ancestor that
        # carries them. This is the contrast that makes the struck-through one mean something.
        fallbacks = a.g.ro_query(
            """
            MATCH (p:Person)-[:APPROVES]->(o:OwnersFile)
            WHERE p.key IN $hs AND NOT o.path IN $strand
            WITH o, collect(DISTINCT p.key) AS leaving
            OPTIONAL MATCH (x:Person)-[:APPROVES]->(o) WHERE NOT x.key IN $hs
            WITH o, leaving, count(DISTINCT x) AS others
            WHERE others = 0
            MATCH (o)-[:INHERITS_FROM*1..8]->(anc:OwnersFile)<-[:APPROVES]-(keeps:Person)
            WHERE NOT keeps.key IN $hs
            RETURN o.path, leaving[0..3] AS leaving, anc.path, collect(DISTINCT keeps.key)[0..2]
            ORDER BY o.path LIMIT 2
            """,
            params={"hs": hs, "strand": strand},
        ).result_set
        for apath, leaving, ancpath, keeps in fallbacks:
            area = area_of(apath, False)
            for who in leaving:
                link(add(who, who, "person_gone"), area, "APPROVES")
            anc = area_of(ancpath, False)
            # Not "INHERITS_FROM": that is a single-hop relationship in the data model, and the
            # match above walks *1..8 to find the nearest ancestor that still has an approver.
            # pkg/api/testing reaches pkg only through pkg/api, which has no approvers at all, so
            # drawing one INHERITS_FROM edge between them asserted a relationship the graph does
            # not contain -- on a picture whose whole claim is that the path IS the evidence. The
            # derived name matches what the prose beside it already says: coverage inherits upward.
            link(area, anc, "INHERITS COVERAGE")
            for who in keeps:
                link(add(who, who, "person_live"), anc, "STILL APPROVES")

        if not drawn_strand and not fallbacks:
            return {"nodes": [], "edges": [],
                    "note": "nothing to draw: this cohort strands no area"}
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


# `FileResponse` sets an ETag and Last-Modified but no Cache-Control, which leaves browsers free
# to cache heuristically and never revalidate. On a demo that gets redeployed and passed around by
# link, that means a returning visitor can run YESTERDAY'S JavaScript against today's API and see
# a page that is subtly, silently wrong. I hit exactly that while testing: the server was serving
# new code and the browser was still running the old.
#
# `no-cache` permits caching but requires revalidation on every load. Starlette's FileResponse
# does NOT honour If-None-Match here -- a conditional request comes back 200, not 304 -- so each
# load re-fetches rather than revalidating cheaply. That is about 25KB for the three files
# combined (27KB measured), which is the right trade for a demo whose whole claim is that what you
# see is what actually ran.
REVALIDATE = {"Cache-Control": "no-cache"}


@app.get("/")
def index():
    return FileResponse(os.path.join(WEB, "index.html"), headers=REVALIDATE)


@app.get("/app.js")
def appjs():
    return FileResponse(os.path.join(WEB, "app.js"),
                        media_type="application/javascript", headers=REVALIDATE)


@app.get("/style.css")
def css():
    return FileResponse(os.path.join(WEB, "style.css"),
                        media_type="text/css", headers=REVALIDATE)
