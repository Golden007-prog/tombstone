import json, sys, urllib.request, html

# Regenerate the README figure from the live API, using the same lane layout as the web renderer.
d = json.load(urllib.request.urlopen("http://127.0.0.1:8099/api/subgraph?path=pkg/controller/podgc/OWNERS"))
LANE = {"person_gone": 0, "person_live": 0, "area": 1, "decision": 2, "rejected": 3}
LABEL = ["people", "area", "decision", "rejected ideas"]
COL = {"person_gone": "#e0796c", "person_live": "#6fbd92", "area": "#d4ab5a",
       "decision": "#7fa3d8", "rejected": "#b08cc4"}
# These mirror web/style.css's dark palette by hand. Eight of the nine matched; EDGE did
# not, because --edge moved to #5d574c in the stylesheet and this copy was never updated.
BG, INK, MUTED, EDGE = "#1b1a16", "#f0ece4", "#a39b8c", "#5d574c"

lanes = [[], [], [], []]
for n in d["nodes"]:
    lanes[LANE[n["kind"]]].append(n)
active = [i for i, l in enumerate(lanes) if l]
W = 860
rowH = 38
H = max(266, max(len(l) for l in lanes) * rowH + 88)
laneX = {}
for idx, li in enumerate(active):
    laneX[li] = 95 + idx * (W - 215) / max(len(active) - 1, 1)
pos = {}
for li, lst in enumerate(lanes):
    span = H - 62
    for i, n in enumerate(lst):
        pos[n["id"]] = dict(x=laneX[li], y=62 + (span - 32) * ((i + 0.5) / len(lst)), **n)

e = html.escape
out = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" width="{W}" height="{H}" '
       f'font-family="ui-sans-serif,-apple-system,Segoe UI,Helvetica,Arial,sans-serif">',
       f'<rect width="{W}" height="{H}" rx="8" fill="{BG}"/>',
       f'<defs><marker id="ar" viewBox="0 0 8 8" refX="7" refY="4" markerWidth="7" markerHeight="7" '
       f'orient="auto-start-reverse"><path d="M0 0 L8 4 L0 8 z" fill="{EDGE}"/></marker></defs>']
for li in active:
    out.append(f'<text x="{laneX[li]:.0f}" y="16" fill="{INK}" font-size="10" text-anchor="middle" '
               f'opacity="0.5" font-family="ui-monospace,Menlo,monospace">{LABEL[li]}</text>')
seen = set()
for ed in d["edges"]:
    a, b = pos.get(ed["source"]), pos.get(ed["target"])
    if not a or not b:
        continue
    mx = (a["x"] + b["x"]) / 2
    out.append(f'<path d="M{a["x"]+10:.0f} {a["y"]:.0f} C {mx:.0f} {a["y"]:.0f}, {mx:.0f} {b["y"]:.0f}, '
               f'{b["x"]-12:.0f} {b["y"]:.0f}" fill="none" stroke="{EDGE}" stroke-width="1.4" marker-end="url(#ar)"/>')
    key = (LANE[a["kind"]], LANE[b["kind"]], ed["label"])
    if key not in seen:
        seen.add(key)
        out.append(f'<text x="{mx:.0f}" y="34" fill="{MUTED}" font-size="8.5" text-anchor="middle" '
                   f'font-family="ui-monospace,Menlo,monospace">{e(ed["label"])}</text>')
for n in pos.values():
    c, x, y = COL[n["kind"]], n["x"], n["y"]
    if n["kind"] == "decision":
        out.append(f'<rect x="{x-9:.0f}" y="{y-7:.0f}" width="18" height="14" rx="3" fill="{c}"/>')
    elif n["kind"] == "rejected":
        out.append(f'<path d="M{x:.0f} {y-8:.0f} L{x+8:.0f} {y:.0f} L{x:.0f} {y+8:.0f} L{x-8:.0f} {y:.0f} z" fill="{c}"/>')
    else:
        gone = n["kind"] == "person_gone"
        out.append(f'<circle cx="{x:.0f}" cy="{y:.0f}" r="{9 if gone else 7}" fill="{c}"'
                   + (f' stroke="{c}" stroke-opacity="0.3" stroke-width="5"' if gone else "") + "/>")
        if gone:
            out.append(f'<path d="M{x-4:.0f} {y-4:.0f} L{x+4:.0f} {y+4:.0f}" stroke="{BG}" stroke-width="1.6"/>')
    anchor = "end" if x > W * 0.6 else "start"
    tx = x - 14 if anchor == "end" else x + 14
    out.append(f'<text x="{tx:.0f}" y="{y+3.5:.0f}" fill="{INK}" font-size="11" text-anchor="{anchor}">{e(n["label"])}</text>')
out.append("</svg>")
open("docs/img/path.svg", "w").write("\n".join(out))
print(f"wrote docs/img/path.svg  nodes={len(d['nodes'])} edges={len(d['edges'])} bytes={len(''.join(out))}")
