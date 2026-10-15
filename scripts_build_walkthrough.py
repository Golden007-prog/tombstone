"""Rebuild docs/video/walkthrough-silent.mp4 from the RUNNING app.

The first version of this video was assembled by hand and the pipeline was never committed, so
`docs/video/README.md` pointed at "the ffmpeg pipeline in the commit that added this file" and that
commit contained only the .mp4. The video could not be regenerated, which meant it would quietly
go stale the moment the UI or the numbers changed. This script is that missing pipeline.

Every frame is a real screenshot of the live app, captured headlessly through the deep links the
UI already supports (`?run=<tool>&focus=1`) -- not a mockup and not a reconstruction. If the app
is not serving, this fails rather than producing a stale video.

Usage:  ./run.sh          (in another shell)
        python scripts_build_walkthrough.py
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
import urllib.request

APP = os.environ.get("APP", "http://localhost:8099")
OUT = "docs/video/walkthrough-silent.mp4"
W, H, BAND = 1280, 860, 130          # frame, plus a caption band beneath it
FPS = 25
CHROME = os.environ.get("CHROME", "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome")
FONT = next((f for f in (
    "/System/Library/Fonts/Supplemental/Arial.ttf",
    "/System/Library/Fonts/Helvetica.ttc",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
) if os.path.exists(f)), None)

# (deep-link query, seconds, caption lines). Two lines maximum: a third does not fit the band.
BEATS = [
    ("run=who_owns&i=0", 7, [
        "Who owns this part of the codebase? Depth 1 returns nothing.",
        "It says what it searched, instead of guessing a plausible wrong name."]),
    ("run=who_owns&i=1", 9, [
        "Same question, four hops. Nobody named on that file still holds approval authority -",
        "and here is what they decided elsewhere, including the alternatives they rejected."]),
    ("ask=has+anyone+tried+moving+this+into+the+kubelet%3F", 9, [
        "Typed, not clicked - and this instance has no API key. The question is routed",
        "locally by meaning, then the same hand-written Cypher answers it."]),
    ("run=draft_owners_patch", 9, [
        "It does not just report the problem. It drafts the fix:",
        "a real OWNERS patch, written to disk. Nothing is sent anywhere."]),
    ("run=draft_owners_patch", 9, [
        "And it refuses what it cannot justify. One handle is not in the file at all -",
        "an alias expands to it, so no edit to that file would remove it."]),
    ("ask=write+me+a+poem+about+kubernetes", 7, [
        "Ask it something outside the graph and it declines, by name.",
        "A router that always picks something is confidently wrong on everything else."]),
    ("run=stepped_back_bridges", 8, [
        "Whose stepping back cost the most connective authority - betweenness centrality.",
        "A whole-graph property. No search index and no embedding produces this."]),
]


def esc(text: str) -> str:
    """Escape for ffmpeg drawtext.

    The `%` assertion is not defensive paranoia: drawtext silently DROPS a line containing an
    unescaped percent sign, and that is how "72%" vanished from the caption of the first cut of
    this video without any error at all.
    """
    assert "%" not in text, f"drawtext silently drops lines containing %: {text!r}"
    return text.replace("\\", r"\\").replace(":", r"\:").replace("'", r"\'")


def require(cond, msg):
    if not cond:
        sys.exit(f"cannot build the walkthrough: {msg}")


require(FONT, "no usable TTF font found for captions")
require(shutil.which("ffmpeg"), "ffmpeg is not on PATH")
require(os.path.exists(CHROME) or shutil.which(CHROME), f"no Chrome at {CHROME}")
try:
    with urllib.request.urlopen(f"{APP}/api/health", timeout=5) as r:
        require(b'"up"' in r.read(), "the app reports FalkorDB down")
except Exception as e:
    sys.exit(f"cannot build the walkthrough: {APP} is not serving ({e}). Start it with ./run.sh")

# Capture a FIRST VISIT. This app remembers answers, so a question asked while building the video
# comes back ANSWERED_FROM_MEMORY the next time -- which is correct behaviour and the wrong frame:
# a judge opening a freshly deployed Space has an empty memory and sees ANSWERED_WITH_PATH. The
# first cut of this video shipped a beat about ROUTING whose badge said the answer came from
# memory, because the question had been asked twenty times that afternoon while testing.
try:
    import urllib.request as _u
    _req = _u.Request(f"{APP}/api/tool", method="POST",
                      data=json.dumps({"tool": "forget_everything", "args": {}}).encode(),
                      headers={"content-type": "application/json"})
    _u.urlopen(_req, timeout=30)
except Exception:
    pass  # falls through to the direct clear below

try:
    sys.path.insert(0, "src")
    from graphkit.ingest import connect as _connect
    _g = _connect().select_graph(os.environ.get("GRAPH", "tomb:k8s"))
    _n = _g.query("MATCH (a:Answer) DETACH DELETE a").relationships_deleted
    print(f"  cleared remembered answers, so the frames show a first visit")
except Exception as exc:
    print(f"  WARNING: could not clear memory ({exc}); frames may show ANSWERED_FROM_MEMORY")

work = os.environ.get("WORKDIR", "build/walkthrough")
os.makedirs(work, exist_ok=True)
clips = []

for i, (query, secs, caption) in enumerate(BEATS):
    png = os.path.join(work, f"frame{i}.png")
    url = f"{APP}/?{query}&focus=1"
    # Unique profile per capture: headless Chrome instances sharing the default user-data-dir
    # can attach to an existing one and screenshot a page that never ran.
    with tempfile.TemporaryDirectory() as profile:
        subprocess.run([CHROME, "--headless=new", "--disable-gpu", "--hide-scrollbars",
                        "--no-first-run", "--no-default-browser-check",
                        f"--user-data-dir={profile}",
                        "--force-device-scale-factor=1", f"--window-size={W},{H}",
                        "--virtual-time-budget=12000", f"--screenshot={png}", url],
                       check=True, capture_output=True)
    require(os.path.getsize(png) > 20_000, f"frame {i} came back blank — is {url} running?")

    y0 = H + 34
    draws = ",".join(
        f"drawtext=fontfile={FONT}:text='{esc(line)}':x=46:y={y0 + n * 38}:"
        f"fontsize=25:fontcolor=0xe8e6e3"
        for n, line in enumerate(caption))
    clip = os.path.join(work, f"clip{i}.mp4")
    subprocess.run(["ffmpeg", "-y", "-loop", "1", "-i", png, "-t", str(secs),
                    "-vf", f"pad={W}:{H + BAND}:0:0:color=0x121214,{draws}",
                    "-r", str(FPS), "-pix_fmt", "yuv420p", "-c:v", "libx264",
                    "-preset", "veryslow", "-crf", "30", clip],
                   check=True, capture_output=True)
    clips.append(clip)
    print(f"  beat {i + 1}/{len(BEATS)}  {secs}s  {query}")

listing = os.path.join(work, "clips.txt")
with open(listing, "w") as fh:
    fh.writelines(f"file '{os.path.abspath(c)}'\n" for c in clips)
subprocess.run(["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", listing,
                "-c", "copy", OUT], check=True, capture_output=True)

total = sum(b[1] for b in BEATS)
print(f"\n{OUT}  —  {total}s, {len(BEATS)} beats, {os.path.getsize(OUT) // 1024}KB")
