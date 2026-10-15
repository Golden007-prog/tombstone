// Tombstone front end. Deliberately plain: no framework, no build step.
// The scripted questions call /api/tool, so the live site works with no API key and no signup
// while the Cypher still runs for real. Free-text routing needs a key and is advertised as such.

const $ = (id) => document.getElementById(id);

// Each chip is a real tool call. The first two are the same question at two depths, which is the
// contrast the brief asks for: shallow finds silence, deep finds the reason for the silence.
const CHIPS = [
  { label: "Who owns the apiserver metrics endpoint? (shallow)",
    tool: "who_owns", args: { path: "staging/src/k8s.io/apiserver/pkg/endpoints/metrics/OWNERS", depth: 1 },
    graph: { path: "staging/src/k8s.io/apiserver/pkg/endpoints/metrics/OWNERS" } },
  { label: "…now ask the graph properly (4 hops)",
    tool: "who_owns", args: { path: "staging/src/k8s.io/apiserver/pkg/endpoints/metrics/OWNERS", depth: 4 },
    graph: { path: "staging/src/k8s.io/apiserver/pkg/endpoints/metrics/OWNERS" } },
  { label: "Has anyone tried moving this into the kubelet?",
    tool: "has_this_been_tried",
    args: { idea_text: "let the kubelet manage this state itself instead of the API server" } },
  { label: "Which areas lost every dedicated owner?",
    tool: "ownership_dilution", args: {} },
  { label: "Whose stepping back cost the most authority?",
    tool: "stepped_back_bridges", args: { min_areas: 3 } },
  { label: "Who should inherit lavalamp's areas?",
    tool: "successor_for", args: { handle: "lavalamp" }, graph: { handle: "lavalamp" } },
  { label: "Which cited decisions no longer exist?",
    tool: "broken_lineage", args: { min_cites: 2 } },
  { label: "Ask something it cannot know",
    tool: "has_this_been_tried",
    args: { idea_text: "rewrite the control plane in COBOL on a mainframe", max_dist: 0.15 } },
  { label: "Which areas have exactly one approver?",
    tool: "sole_approver_risk", args: {} },
  { label: "What if the apiserver reviewers all stepped back?",
    tool: "what_if_they_go",
    args: { handles: ["deads2k", "liggitt", "jpbetz", "smarterclayton", "enj", "serathius"] } },
  { label: "What knowledge here is going stale?",
    tool: "stale_knowledge", args: { min_years: 3 } },
  { label: "Has this graph been asked this before?",
    tool: "recall", args: { question: "who currently owns the podgc controller" } },
];

// Resolve the palette ONCE, to plain hex strings. Cytoscape style values must be concrete:
// a function mapper that returns an unparseable colour fails the whole stylesheet silently and
// the canvas renders nothing, with no console error.
function palette() {
  const cs = getComputedStyle(document.documentElement);
  const v = (n, fb) => (cs.getPropertyValue(n) || "").trim() || fb;
  return {
    gone: v("--gone", "#e0796c"), live: v("--live", "#6fbd92"),
    area: v("--area", "#d4ab5a"), dec: v("--dec", "#7fa3d8"),
    rej: v("--rej", "#b08cc4"), ink: v("--ink", "#f0ece4"),
    line: v("--line", "#2e2c26"), muted: v("--muted", "#a39b8c"),
    panel: v("--panel", "#1b1a16"), edge: v("--edge", "#5d574c"),
  };
}

async function health() {
  const el = $("health");
  try {
    const h = await (await fetch("/api/health")).json();
    const up = h.falkordb === "up";
    el.className = "health " + (up ? "up" : "down");
    if (up) {
      const c = h.graph_contents || {};
      el.textContent = window.innerWidth < 620
        ? `FalkorDB up · ${c.decisions ?? "?"} decisions · ${c.named_options ?? "?"} rejected options`
        : `FalkorDB up · ${h.ms}ms · ${c.decisions ?? "?"} decisions, ${c.named_options ?? "?"} rejected options`;
    } else {
      el.textContent = "FalkorDB DOWN — nothing to reason over";
    }
    $("hint").textContent = h.llm_configured
      ? "Free-text routing is on: a model picks one tool, then hand-written Cypher answers."
      : "No LLM key on this instance, so free-text routing is off. The buttons below call the same tools directly and run the same Cypher.";
    if (!h.llm_configured) { $("q").disabled = true; $("go").disabled = true; }
  } catch (e) {
    el.className = "health down";
    el.textContent = "server unreachable";
  }
}

function chips() {
  const box = $("chips");
  CHIPS.forEach((c) => {
    const b = document.createElement("button");
    b.className = "chip";
    b.textContent = c.label;
    b.onclick = () => runTool(c);
    box.appendChild(b);
  });
}

function show(data, graphArgs) {
  $("result").classList.remove("hidden");
  $("shape").textContent = data.shape || "?";
  const bits = [];
  if (data.tool || data.routed_to) bits.push(data.tool || data.routed_to);
  if (data.ms != null) bits.push(`${data.ms}ms`);
  if (data.rows) bits.push(`${data.rows.length} row${data.rows.length === 1 ? "" : "s"}`);
  $("meta").textContent = bits.join("  ·  ");
  $("answer").textContent = data.answer || "(no answer)";

  const cov = data.coverage && Object.keys(data.coverage).length ? data.coverage : null;
  $("covwrap").classList.toggle("hidden", !cov);
  if (cov) $("coverage").textContent = JSON.stringify(cov, null, 2);

  $("cypher").textContent = (data.cypher || "").trim() || "(none)";
  $("sha").textContent = data.query_sha || "";

  if (graphArgs && data.shape === "ANSWERED_WITH_PATH") drawGraph(graphArgs);
  else $("graphwrap").classList.add("hidden");
  $("result").scrollIntoView({ behavior: "smooth", block: "nearest" });
}

async function runTool(c) {
  $("answer").textContent = "running…";
  $("result").classList.remove("hidden");
  try {
    const r = await fetch("/api/tool", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ tool: c.tool, args: c.args }),
    });
    show(await r.json(), c.graph);
  } catch (e) {
    show({ shape: "DEGRADED", answer: "Request failed: " + e });
  }
}

async function ask() {
  const q = $("q").value.trim();
  if (!q) return;
  $("answer").textContent = "routing…";
  $("result").classList.remove("hidden");
  try {
    const r = await fetch("/api/ask", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ question: q }),
    });
    const d = await r.json();
    const g = d.routed_args && d.routed_args.path ? { path: d.routed_args.path }
            : d.routed_args && d.routed_args.handle ? { handle: d.routed_args.handle } : null;
    show(d, g);
  } catch (e) {
    show({ shape: "DEGRADED", answer: "Request failed: " + e });
  }
}

async function drawGraph(args) {
  const qs = new URLSearchParams(args).toString();
  const d = await (await fetch("/api/subgraph?" + qs)).json();
  if (!d.nodes || !d.nodes.length) { $("graphwrap").classList.add("hidden"); return; }
  $("graphwrap").classList.remove("hidden");
  renderPath(d);
}

// Hand-drawn SVG rather than a force layout. For the ten-or-so nodes on one answer's path a
// deliberate left-to-right layering is far more legible than a physics simulation, it renders
// identically every time (which matters when recording), and there is no library to misbehave.
// The full graph is never drawn: a hairball would be decoration, and the path is the evidence.
const LANE = { person_gone: 0, person_live: 0, area: 1, decision: 2, rejected: 3 };
const LANE_LABEL = ["people", "area", "decision", "rejected ideas"];

function renderPath(d) {
  const host = $("cy");
  host.innerHTML = "";
  const P = palette();

  // bucket nodes into lanes
  const lanes = [[], [], [], []];
  d.nodes.forEach((n) => lanes[LANE[n.kind] ?? 0].push(n));
  const used = lanes.map((l) => l.length).filter(Boolean).length;

  const W = Math.max(host.clientWidth || 760, 560);
  const rowH = 38;
  const maxRows = Math.max(...lanes.map((l) => l.length), 1);
  const H = Math.max(266, maxRows * rowH + 88);
  const laneX = [];
  const activeLanes = lanes.map((l, i) => (l.length ? i : -1)).filter((i) => i >= 0);
  activeLanes.forEach((li, idx) => {
    laneX[li] = 90 + (idx * (W - 200)) / Math.max(activeLanes.length - 1, 1);
  });

  const pos = {};
  lanes.forEach((list, li) => {
    const span = H - 62;
    list.forEach((n, i) => {
      pos[n.id] = { x: laneX[li], y: 62 + (span - 32) * ((i + 0.5) / list.length),
                    kind: n.kind, label: n.label, full: n.full };
    });
  });

  const esc = (t) => String(t).replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
  const col = { person_gone: P.gone, person_live: P.live, area: P.area, decision: P.dec, rejected: P.rej };

  let svg = `<svg viewBox="0 0 ${W} ${H}" width="100%" height="${H}" role="img" aria-label="The path behind this answer">`;
  svg += `<defs><marker id="ar" viewBox="0 0 8 8" refX="7" refY="4" markerWidth="7" markerHeight="7" orient="auto-start-reverse"><path d="M0 0 L8 4 L0 8 z" fill="${P.edge}"/></marker></defs>`;

  // lane captions
  activeLanes.forEach((li) => {
    svg += `<text x="${laneX[li]}" y="12" fill="${P.ink}" font-size="9.5" text-anchor="middle" font-family="ui-monospace,Menlo,monospace" opacity="0.55">${LANE_LABEL[li]}</text>`;
  });

  // Edges behind the nodes. Each relationship type is labelled ONCE per lane pair -- repeating
  // "REJECTED" six times down a column is noise that collides with the node text.
  const labelled = new Set();
  d.edges.forEach((e) => {
    const a = pos[e.source], b = pos[e.target];
    if (!a || !b) return;
    const mx = (a.x + b.x) / 2;
    svg += `<path d="M${a.x + 10} ${a.y} C ${mx} ${a.y}, ${mx} ${b.y}, ${b.x - 12} ${b.y}" fill="none" stroke="${P.edge}" stroke-width="1.4" marker-end="url(#ar)"/>`;
    const lane = `${LANE[a.kind] ?? 0}>${LANE[b.kind] ?? 0}:${e.label}`;
    if (!labelled.has(lane)) {
      // Two relationship types can span the same pair of lanes (an owner who stepped back LEFT BEHIND an
      // area that a successor ALREADY APPROVES), so stack their captions instead of overprinting.
      const stack = [...labelled].filter((k) => k.startsWith(lane.split(":")[0])).length;
      labelled.add(lane);
      svg += `<text x="${mx}" y="${30 + stack * 11}" fill="${P.muted}" font-size="8.5" text-anchor="middle" font-family="ui-monospace,Menlo,monospace" letter-spacing="0.04em">${esc(e.label)}</text>`;
    }
  });

  // nodes
  Object.entries(pos).forEach(([, n]) => {
    const c = col[n.kind] || P.muted;
    const gone = n.kind === "person_gone";
    if (n.kind === "decision") {
      svg += `<rect x="${n.x - 9}" y="${n.y - 7}" width="18" height="14" rx="3" fill="${c}"/>`;
    } else if (n.kind === "rejected") {
      svg += `<path d="M${n.x} ${n.y - 8} L${n.x + 8} ${n.y} L${n.x} ${n.y + 8} L${n.x - 8} ${n.y} z" fill="${c}"/>`;
    } else {
      svg += `<circle cx="${n.x}" cy="${n.y}" r="${gone ? 9 : 7}" fill="${c}"${gone ? ` stroke="${c}" stroke-opacity="0.3" stroke-width="5"` : ""}/>`;
      if (gone) svg += `<path d="M${n.x - 4} ${n.y - 4} L${n.x + 4} ${n.y + 4}" stroke="${P.panel}" stroke-width="1.6"/>`;
    }
    const anchor = n.x > W * 0.6 ? "end" : "start";
    const tx = anchor === "end" ? n.x - 14 : n.x + 14;
    svg += `<text x="${tx}" y="${n.y + 3.5}" fill="${P.ink}" font-size="10.5" text-anchor="${anchor}">${esc(n.label)}<title>${esc(n.full || n.label)}</title></text>`;
  });

  svg += `</svg>`;
  host.innerHTML = svg;
}

$("go").onclick = ask;
$("q").addEventListener("keydown", (e) => { if (e.key === "Enter") ask(); });
chips();
health();
