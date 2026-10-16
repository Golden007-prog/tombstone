// Tombstone front end. Deliberately plain: no framework, no build step.
// The scripted questions call /api/tool, so the live site works with no API key and no signup
// while the Cypher still runs for real. Free-text routing needs a key and is advertised as such.

const $ = (id) => document.getElementById(id);

// Each chip is a real tool call. The first two are the same question at two depths, which is the
// contrast the brief asks for: shallow finds silence, deep finds the reason for the silence.
//
// KEEP LABELS SHORT, and here is the actual budget rather than a feeling about it. `.chip` is
// `white-space:nowrap; flex-shrink:0`, so a label can neither wrap nor compress: a long one
// overflows its container instead. Measured in a browser at 375x812 against this exact CSS, the
// longest label here -- "Whose stepping back cost the most connective authority?", 55 characters
// -- renders 356px wide, against a 343px content box inside `.wrap`'s 16px gutters. It overflows
// INTO the gutter and the page still does not scroll sideways, because 356 < 375. So there are
// roughly three characters of headroom before a phone gets horizontal scroll.
//
// Three characters, not a rule: this is a proportional font, so "WWW" costs far more than "iii"
// and a character limit would be a bad proxy. If you add a longer label, open the page at 375px
// and look, the way this number was obtained.
const CHIPS = [
  { label: "Who owns the apiserver metrics endpoint? (shallow)", step: 1,
    question: "who owns the apiserver metrics endpoint",
    tool: "who_owns", args: { path: "staging/src/k8s.io/apiserver/pkg/endpoints/metrics/OWNERS", depth: 1 },
    graph: { path: "staging/src/k8s.io/apiserver/pkg/endpoints/metrics/OWNERS" } },
  { label: "…now ask the graph properly (4 hops)", step: 2,
    question: "who really owns the apiserver metrics endpoint",
    tool: "who_owns", args: { path: "staging/src/k8s.io/apiserver/pkg/endpoints/metrics/OWNERS", depth: 4 },
    graph: { path: "staging/src/k8s.io/apiserver/pkg/endpoints/metrics/OWNERS" } },
  { label: "Draft the fix \u2014 don't just report it", step: 3,
    question: "draft the fix for the ownership records that contradict themselves",
    tool: "draft_owners_patch", args: { min_stepped_back: 3 } },
  { label: "Has anyone tried moving this into the kubelet?",
    tool: "has_this_been_tried",
    args: { idea_text: "let the kubelet manage this state itself instead of the API server" } },
  { label: "Which areas lost every dedicated owner?",
    tool: "ownership_dilution", args: {} },
  { label: "Whose stepping back cost the most connective authority?",
    tool: "stepped_back_bridges", args: { min_areas: 3 } },
  { label: "Who should inherit lavalamp's areas?",
    tool: "successor_for", args: { handle: "lavalamp" }, graph: { handle: "lavalamp" } },
  { label: "Which cited decisions no longer exist?",
    tool: "broken_lineage", args: { min_cites: 2 } },
  { label: "Ask something it cannot know",
    question: "has anyone proposed rewriting the control plane in COBOL",
    tool: "has_this_been_tried",
    args: { idea_text: "rewrite the control plane in COBOL on a mainframe", max_dist: 0.15 } },
  { label: "Which contributor group is hollowing out?",
    tool: "hollowing_communities", args: { min_size: 5 } },
  { label: "Which areas have exactly one approver?",
    tool: "sole_approver_risk", args: {} },
  { label: "What if the apiserver reviewers all stepped back?",
    tool: "what_if_they_go",
    args: { handles: ["deads2k", "liggitt", "jpbetz", "smarterclayton", "enj", "serathius"] },
    graph: { from: "answer" } },
  { label: "What knowledge here is going stale?",
    tool: "stale_knowledge", args: { min_years: 3 } },
  // Deliberately a REWORDING of chip 1, not a new subject. The point of this chip is that recall
  // is semantic and survives different phrasing -- and on a freshly deployed instance, memory
  // only contains what this visitor has just clicked. Asking about an unrelated area returned
  // "never asked", correctly, which made the one beat about memory show nothing.
  { label: "Has this graph been asked this before?",
    tool: "recall", args: { question: "who actually owns the apiserver metrics endpoint" } },
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
      // The second sentence is a disclosure, not a feature note. An answered question is written
      // into the graph as an (:Answer) node carrying the question text, and the recall chip
      // surfaces it to whoever visits next. Everything else about this product is stated plainly
      // to the person reading it; what happens to their own input should be too.
      : "No API key on this instance, so your question is routed locally by meaning against a fixed catalogue — then the same hand-written Cypher answers it. It refuses rather than guess. Answered questions are stored in the graph — that is the memory feature, and it means a later visitor can see what was asked.";
    $("q").disabled = false; $("go").disabled = false;
  } catch (e) {
    el.className = "health down";
    el.textContent = "server unreachable";
  }
}

function chips() {
  const box = $("chips");
  CHIPS.forEach((c) => {
    const b = document.createElement("button");
    // Fourteen chips in a row give a visitor with three minutes no idea where to start, so the
    // three that actually make the argument are numbered: the question answered shallowly, the
    // same question answered properly, and the agent acting on what it found. The rest are there
    // to be explored, not worked through in order.
    b.className = c.step ? "chip step" : "chip";
    b.textContent = c.step ? `${c.step}. ${c.label}` : c.label;
    b.dataset.tool = c.tool;
    b.onclick = () => runTool(c, b);
    box.appendChild(b);
  });
}

// `?run=<tool>` runs that chip on load, so an answer is deep-linkable: a link can land someone on
// a RESULT rather than on an empty box they have to know what to do with. It also makes the
// walkthrough frames capturable headlessly, which is why the build script can regenerate the
// video instead of depending on somebody driving a mouse.
// When several chips share a tool (who_owns runs at two depths) `&i=` picks which one.
function runFromUrl() {
  const p = new URLSearchParams(location.search);
  // `?ask=<text>` deep-links a FREE-TEXT question: it fills the box and submits, so a question
  // and its answer can be shared as a URL, and so the walkthrough can capture someone typing
  // rather than only clicking. Works keyless, because routing does.
  const typed = p.get("ask");
  if (typed) {
    // Keep the ask box on screen for a typed question even in focus mode -- hiding it would
    // hide the thing being demonstrated, which is that someone typed this.
    if (p.get("focus") === "1") document.body.classList.add("focus", "show-ask");
    $("q").value = typed;
    document.body.dataset.autorun = "pending";
    ask().finally(() => { document.body.dataset.autorun = "done"; });
    return;
  }

  const want = p.get("run");
  if (!want) return;
  const matches = CHIPS.map((c, i) => [c, i]).filter(([c]) => c.tool === want);
  if (!matches.length) return;
  const pick = Math.min(parseInt(p.get("i") || "0", 10) || 0, matches.length - 1);
  const [chip, idx] = matches[pick];
  const btn = $("chips").children[idx];
  // `&focus=1` hides everything above the answer, so a screenshot or a demo frame is just the
  // result. The walkthrough build depends on it; it is also the cleanest way to show one answer.
  if (p.get("focus") === "1") document.body.classList.add("focus");
  document.body.dataset.autorun = "pending";
  runTool(chip, btn).finally(() => { document.body.dataset.autorun = "done"; });
}


// A unified diff in a proportional font is not a diff: the - and + columns stop lining up, which
// is precisely the thing the reader is scanning for. So contiguous diff lines are lifted into a
// monospace block that scrolls sideways rather than wrapping -- wrapping a diff on a phone
// destroys it just as thoroughly.
//
// Built with text nodes, never innerHTML. The content is the product's own output, but a
// rendering path that interprets markup is a rendering path that can be made to interpret
// markup, and there is no reason to have one here.
const DIFF_START = /^--- /;
const DIFF_LINE = /^(\+\+\+ |@@ |[-+ ])/;

function renderAnswer(text) {
  const host = $("answer");
  host.textContent = "";
  const lines = text.split("\n");
  let i = 0;
  while (i < lines.length) {
    if (DIFF_START.test(lines[i])) {
      const block = [];
      while (i < lines.length && (DIFF_START.test(lines[i]) || DIFF_LINE.test(lines[i]))) {
        block.push(lines[i]); i++;
      }
      const pre = document.createElement("pre");
      pre.className = "diff";
      pre.textContent = block.join("\n");
      host.appendChild(pre);
    } else {
      const start = i;
      while (i < lines.length && !DIFF_START.test(lines[i])) i++;
      const chunk = lines.slice(start, i).join("\n");
      if (chunk.trim()) host.appendChild(document.createTextNode(chunk + "\n"));
    }
  }
}

// An answer is "from rows" when a query actually produced it. Refusals and degraded answers are
// not, and must not carry the provenance claim.
function cyRan(data) {
  return (data.cypher || "").trim() && Array.isArray(data.rows);
}

// Returns the promise for the graph panel, so a caller can wait until the answer is FULLY
// rendered. It used to call drawGraph and drop the promise, which made `data-autorun="done"`
// mean "the answer text is in" while the SVG was still a fetch in flight. Anything snapshotting
// the DOM on that signal -- the rendered-state check, and the walkthrough video's frame capture
// -- could photograph the moment before the path appeared.
function show(data, graphArgs) {
  $("result").classList.remove("hidden");
  $("shape").textContent = data.shape || "?";
  const bits = [];
  if (data.tool || data.routed_to) bits.push(data.tool || data.routed_to);
  if (data.ms != null) bits.push(`${data.ms}ms`);
  if (data.rows) bits.push(`${data.rows.length} row${data.rows.length === 1 ? "" : "s"}`);
  $("meta").textContent = bits.join("  ·  ");
  renderAnswer(data.answer || "(no answer)");

  // The one number that is the point, pulled from the rows by the server — never written by
  // hand and never by the model, so it cannot disagree with the answer underneath it.
  const h = data.headline;
  $("headline").classList.toggle("hidden", !h);
  if (h) { $("hstat").textContent = h.stat; $("hlabel").textContent = h.label; }

  const cov = data.coverage && Object.keys(data.coverage).length ? data.coverage : null;
  $("covwrap").classList.toggle("hidden", !cov);
  if (cov) $("coverage").textContent = JSON.stringify(cov, null, 2);

  // The provenance line belongs to answers that came from a query. A refusal did not run one,
  // and claiming "formatted from rows this query returned" under it would be false.
  const fromRows = !!cyRan(data);
  $("provenance").classList.toggle("hidden", !fromRows);
  if (fromRows) {
    $("provenance").lastElementChild.nextSibling.textContent =
      data.routed_by === "llm"
        ? " — the model's only decision is which tool to call."
        : " — the model's only decision is which tool to call, and on this instance there is no model at all.";
  }

  // No Cypher ran, so do not offer to show it. A disclosure that opens onto "(none)" with an
  // empty hash beside it looks like something failed, when nothing did -- the router declined.
  const cy = (data.cypher || "").trim();
  $("cywrap").classList.toggle("hidden", !cy);
  $("cypher").textContent = cy;
  $("sha").textContent = data.query_sha || "";
  // The arguments this answer was produced with. The hash identifies the query TEXT -- that it
  // is one of the thirteen constants and was not rewritten -- and deliberately not the arguments,
  // so the same query and the same hash can answer two different questions: the chip narrows
  // broken_lineage to min_cites 2 and a typed question uses the default 1, which is 5 rows
  // against 15. These are the tool's own argument names rather than the Cypher's binding names,
  // because the two do not map one to one -- who_owns' depth picks between two constants instead
  // of templating into one, and stale_knowledge's min_years reaches the query as $ageMs.
  const prm = data.params && Object.keys(data.params).length ? data.params : null;
  const pel = $("cyparams");
  if (pel) {
    pel.classList.toggle("hidden", !prm || !cy);
    pel.textContent = prm
      ? "answered with: " + Object.entries(prm)
          .map(([k, v]) => k + " = " + (Array.isArray(v) ? v.length + " values" : v)).join(", ")
      : "";
  }

  // ANSWERED_FROM_MEMORY belongs here as much as ANSWERED_WITH_PATH does. A remembered answer
  // is not a cached string: the tool was re-run, the rows are the rows it just returned, and the
  // shape changed only because the citations still resolve. Drawing the path for one and not the
  // other meant the headline chip stopped showing its four-hop picture the second time anyone
  // clicked it -- which is what a judge does, and what the video capture does on a warm instance.
  const drawable = data.shape === "ANSWERED_WITH_PATH" || data.shape === "ANSWERED_FROM_MEMORY";
  // A declined near-tie names two tools it could not choose between. Offering them as buttons is
  // not the router guessing after all: it declined, showed both scores, and a person chose. The
  // arguments are still extracted from the question by rule, so nothing clicked enters a query.
  const picks = $("choices");
  picks.textContent = "";
  const near = (data.shape === "UNSURE_WHICH_TOOL" && Array.isArray(data.near)) ? data.near : [];
  picks.classList.toggle("hidden", !near.length);
  near.forEach((n) => {
    const b = document.createElement("button");
    b.className = "pick";
    b.appendChild(document.createTextNode(n.tool));
    const sc = document.createElement("span");
    sc.className = "sc";
    sc.textContent = String(n.score);
    b.appendChild(sc);
    b.addEventListener("click", () => ask(data.question || $("q").value, n.tool));
    picks.appendChild(b);
  });

  let drawing = Promise.resolve();
  if (graphArgs && drawable) drawing = drawGraph(graphArgs);
  else $("graphwrap").classList.add("hidden");
  // In focus mode the answer is already at the top, and scrolling to it pushes the typed
  // question off-screen -- which hides the thing a capture of this view is meant to show.
  if (!document.body.classList.contains("focus")) {
    $("result").scrollIntoView({ behavior: "smooth", block: "nearest" });
  }
  return drawing;
}

// A chip's label is written for the eye; what memory stores has to be a QUESTION, because recall
// searches it by meaning. "…now ask the graph properly (4 hops)" is a good button and a useless
// memory key -- it shares no words and no meaning with "who owns this area", so a later recall
// could never find it. Chips whose label is not already a question carry an explicit one.
async function runTool(c, btn) {
  $("answer").textContent = "running the Cypher…";
  $("headline").classList.add("hidden");
  $("graphwrap").classList.add("hidden");
  $("result").classList.remove("hidden");
  if (btn) btn.classList.add("loading");
  try {
    const r = await fetch("/api/tool", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ tool: c.tool, args: c.args, question: c.question || c.label }),
    });
    const d = await r.json();
    await show(d, graphArgsFor(c, d));
  } catch (e) {
    show({ shape: "DEGRADED", answer: "Request failed: " + e });
  } finally {
    if (btn) btn.classList.remove("loading");
  }
}

async function ask(forcedQuestion, forcedTool) {
  const q = (forcedQuestion || $("q").value).trim();
  if (!q) return;
  $("answer").textContent = "routing…";
  $("headline").classList.add("hidden");
  $("result").classList.remove("hidden");
  try {
    const r = await fetch("/api/ask", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify(forcedTool ? { question: q, force: forcedTool } : { question: q }),
    });
    const d = await r.json();
    // Both ask paths now return the chosen arguments under `routed_args` (they used to disagree,
    // and this read a field one of them never set, so a typed question never drew its path).
    const ra = d.routed_args || (d.routing && d.routing.args) || {};
    const g = ra.path ? { path: ra.path } : ra.handle ? { handle: ra.handle } : null;
    await show(d, g);
  } catch (e) {
    show({ shape: "DEGRADED", answer: "Request failed: " + e });
  }
}

// Most chips carry their graph arguments statically. The counterfactual cannot: which areas a
// cohort strands is decided by a GRAPH.COPY on the server, so the picture has to be built from the
// answer the user is looking at rather than from anything known in advance. If the run came back
// DEGRADED, or stranded nothing, this returns null and no panel opens -- an empty picture would
// read as "no answer" rather than "nothing breaks".
function graphArgsFor(c, d) {
  if (!c.graph) return null;
  if (c.tool === "what_if_they_go") {
    const row = (d.rows && d.rows[0]) || null;
    if (!row || !Array.isArray(row[1]) || !row[1].length) return null;
    return { handles: (row[0] || []).join(","), stranded: row[1].join(",") };
  }
  return c.graph;
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
const LANE = { person_gone: 0, person_live: 0, area: 1, area_stranded: 1, decision: 2, rejected: 3 };
const LANE_LABEL = ["people", "area", "decision", "rejected ideas"];

function renderPath(d) {
  const host = $("cy");
  host.innerHTML = "";
  const P = palette();

  // bucket nodes into lanes
  const lanes = [[], [], [], []];
  d.nodes.forEach((n) => lanes[LANE[n.kind] ?? 0].push(n));
  const used = lanes.map((l) => l.length).filter(Boolean).length;

  // The lane layout needs about 560 units of width to read. When the container is narrower than
  // that -- a phone, or the Space's iframe at a narrow breakpoint -- the viewBox stays 560 and
  // the browser scales the whole drawing down to fit. At 307px that is a factor of 0.53, which
  // rendered the node labels at about 5.6 real pixels: present, correctly laid out, and unreadable.
  // So typography is multiplied by the same factor the browser is about to divide by, which keeps
  // text at its intended SIZE ON SCREEN at any width.
  const CW = host.clientWidth || 760;
  const W = Math.max(CW, 560);
  const k = W / Math.max(CW, 1);          // >= 1; exactly 1 on a wide screen
  const fs = (pt) => Math.round(pt * k * 10) / 10;
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
  const col = { person_gone: P.gone, person_live: P.live, area: P.area, decision: P.dec,
                rejected: P.rej, area_stranded: P.gone };

  let svg = `<svg viewBox="0 0 ${W} ${H}" width="100%" height="${H}" role="img" aria-label="The path behind this answer">`;
  svg += `<defs><marker id="ar" viewBox="0 0 8 8" refX="7" refY="4" markerWidth="7" markerHeight="7" orient="auto-start-reverse"><path d="M0 0 L8 4 L0 8 z" fill="${P.edge}"/></marker></defs>`;

  // lane captions
  activeLanes.forEach((li) => {
    svg += `<text x="${laneX[li]}" y="12" fill="${P.ink}" font-size="${fs(9.5)}" text-anchor="middle" font-family="ui-monospace,Menlo,monospace" opacity="0.55">${LANE_LABEL[li]}</text>`;
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
      svg += `<text x="${mx}" y="${30 + stack * 11}" fill="${P.muted}" font-size="${fs(8.5)}" text-anchor="middle" font-family="ui-monospace,Menlo,monospace" letter-spacing="0.04em">${esc(e.label)}</text>`;
    }
  });

  // nodes
  Object.entries(pos).forEach(([, n]) => {
    const c = col[n.kind] || P.muted;
    const gone = n.kind === "person_gone";
    if (n.kind === "area_stranded") {
      // Same square as any other area, in the colour of what has been lost, struck through. The
      // shape says "this is an area"; the mark says "nobody is left on it".
      svg += `<rect x="${n.x - 10}" y="${n.y - 8}" width="20" height="16" rx="3" fill="${c}"/>`;
      svg += `<path d="M${n.x - 6} ${n.y - 5} L${n.x + 6} ${n.y + 5}" stroke="${P.panel}" stroke-width="1.8"/>`;
    } else if (n.kind === "decision") {
      svg += `<rect x="${n.x - 9}" y="${n.y - 7}" width="18" height="14" rx="3" fill="${c}"/>`;
    } else if (n.kind === "rejected") {
      svg += `<path d="M${n.x} ${n.y - 8} L${n.x + 8} ${n.y} L${n.x} ${n.y + 8} L${n.x - 8} ${n.y} z" fill="${c}"/>`;
    } else {
      svg += `<circle cx="${n.x}" cy="${n.y}" r="${gone ? 9 : 7}" fill="${c}"${gone ? ` stroke="${c}" stroke-opacity="0.3" stroke-width="5"` : ""}/>`;
      if (gone) svg += `<path d="M${n.x - 4} ${n.y - 4} L${n.x + 4} ${n.y + 4}" stroke="${P.panel}" stroke-width="1.6"/>`;
    }
    const anchor = n.x > W * 0.6 ? "end" : "start";
    const tx = anchor === "end" ? n.x - 14 : n.x + 14;
    // Fit the label to the room it actually has, rather than trusting the server's fixed-length
    // truncation. That length is right for a wide screen and too long for a phone: the viewBox
    // stays 560 wide while the container is 375, so fs() draws every label ~1.5x larger in viewBox
    // units, and the area node's path ran off the right edge -- losing its own ellipsis, so it read
    // as a path that simply stopped rather than one that was shortened. The full value is in the
    // <title> either way, so nothing is lost by cutting it here.
    const em = fs(10.5) * 0.55;                       // rough advance width of one character
    const room = (anchor === "end" ? tx : W - tx) - 4;
    let label = n.label;
    if (label.length * em > room) {
      label = label.slice(0, Math.max(1, Math.floor(room / em) - 1)) + "…";
    }
    // paint-order="stroke" draws the panel-coloured stroke BEHIND the glyphs, so a label sits in
    // its own halo instead of having an edge run through it. That was not merely untidy here: a
    // line through a label reads as a strikethrough, and a strike is exactly what this picture
    // uses to mean "gone" -- on the person node and on an area with nobody left. A decision with
    // a line through it looked like a decision that had been struck.
    svg += `<text x="${tx}" y="${n.y + 3.5}" fill="${P.ink}" font-size="${fs(10.5)}" `
        + `text-anchor="${anchor}" stroke="${P.panel}" stroke-width="${fs(3)}" `
        + `stroke-linejoin="round" paint-order="stroke">`
        + `${esc(label)}<title>${esc(n.full || n.label)}</title></text>`;
  });

  svg += `</svg>`;
  host.innerHTML = svg;
}

$("go").onclick = ask;
$("q").addEventListener("keydown", (e) => { if (e.key === "Enter") ask(); });
chips();
health();
runFromUrl();
