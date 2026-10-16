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
    ("ask=show+me+the+areas+that+depend+on+one+person", 9, [
        "A real question it cannot place: two tools score too close to call, so it declines -",
        "and offers the candidates it was torn between, with their scores. You choose."]),
    ("run=what_if_they_go", 10, [
        "Forward-looking: if this whole cohort stops approving, one area loses its last approver.",
        "The others survive by inheriting coverage upward - which is why a forked copy is needed."]),
    ("run=stepped_back_bridges", 8, [
        "Whose stepping back cost the most connective authority - betweenness centrality.",
        "A whole-graph property. No search index and no embedding produces this."]),
]


def card(path: str, secs: int, lines: list[tuple[str, int]]) -> str:
    """A plain text card on the same canvas, for the open and the close.

    The video used to begin mid-answer, on a screenshot of a result, with no statement of what
    the thing is. A judge who opens the fallback video cold has no commentary to orient them --
    that is the whole point of it being the fallback -- so it now says what it is and where to
    find it. `fontsize` is per line because a title and a subtitle are not the same weight.
    """
    draws = []
    for i, (text, size) in enumerate(lines):
        y = (H + BAND) // 2 - (len(lines) * 34) + i * 56
        draws.append(
            f"drawtext=fontfile={FONT}:text='{esc(text)}':"
            f"x=(w-text_w)/2:y={y}:fontsize={size}:fontcolor=0xe8e6e3")
    subprocess.run([*FFMPEG, "-y", "-f", "lavfi",
                    "-i", f"color=c=0x121214:s={W}x{H + BAND}:d={secs}",
                    "-vf", ",".join(draws), "-r", str(FPS), "-pix_fmt", "yuv420p",
                    "-c:v", "libx264", "-preset", "veryslow", "-crf", "30", path],
                   check=True, capture_output=True)
    return path

def esc(text: str) -> str:
    """Escape for ffmpeg drawtext.

    The `%` assertion is not defensive paranoia: drawtext silently DROPS a line containing an
    unescaped percent sign, and that is how "72%" vanished from the caption of the first cut of
    this video without any error at all.
    """
    assert "%" not in text, f"drawtext silently drops lines containing %: {text!r}"
    # An apostrophe survives the shell but not drawtext's own parser -- "Kubernetes' record"
    # rendered as "Kubernetes record" with no warning, which reads as a typo rather than a bug.
    assert "'" not in text, f"drawtext drops apostrophes; reword instead: {text!r}"
    return text.replace("\\", r"\\").replace(":", r"\:").replace("'", r"\'")


def require(cond, msg):
    if not cond:
        sys.exit(f"cannot build the walkthrough: {msg}")


require(FONT, "no usable TTF font found for captions")
def _ffmpeg() -> list[str]:
    """The ffmpeg to use: the local one if it actually runs, else a container.

    Present is not the same as working. A Homebrew x265 bump left ffmpeg 8.0.1 linked against
    libx265.215 while the cellar held 217, so every invocation died on start -- and the failure
    surfaced as a CalledProcessError on the first frame, thirty lines from the cause. So the local
    binary has to prove it runs, and when it cannot, the build uses a pinned container rather than
    stopping. Regenerating the video should not depend on the state of somebody's package manager.
    """
    probe = subprocess.run(["ffmpeg", "-version"], capture_output=True, text=True) \
        if shutil.which("ffmpeg") else None
    if probe is not None and probe.returncode == 0:
        return ["ffmpeg"]

    why = "not on PATH" if probe is None else \
        ((probe.stderr or probe.stdout).strip().splitlines() or ["failed to start"])[0]
    if not shutil.which("docker"):
        sys.exit(f"ffmpeg cannot be used ({why}) and there is no docker to fall back to.\n"
                 f"  On macOS the usual cause is a dependency bump: brew reinstall ffmpeg")
    print(f"  local ffmpeg unusable ({why[:70]}) -- using the container instead")
    return ["docker", "run", "--rm", "-v", f"{os.path.abspath('.')}:/repo", "-w", "/repo",
            "--entrypoint", "ffmpeg", "linuxserver/ffmpeg:latest"]


FFMPEG = _ffmpeg()
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
    sys.path.insert(0, "src")
    from graphkit.ingest import connect as _connect
    _g = _connect().select_graph(os.environ.get("GRAPH", "tomb:k8s"))
    # nodes_deleted, not relationships_deleted: the count being reported is answers forgotten.
    # It arrives as a float, so an int() keeps "3" from printing as "3.0".
    _n = int(_g.query("MATCH (a:Answer) DETACH DELETE a").nodes_deleted or 0)
    print(f"  forgot {_n} remembered answer{'' if _n == 1 else 's'}, "
          f"so the frames show a first visit")
except Exception as exc:
    print(f"  WARNING: could not clear memory ({exc}); frames may show ANSWERED_FROM_MEMORY")

# Inside the repo, so a containerised ffmpeg sees these paths under its one mount.
work = os.environ.get("WORKDIR", "build/walkthrough")
if FFMPEG[0] == "docker":
    work = "build/walkthrough"
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
    subprocess.run([*FFMPEG, "-y", "-loop", "1", "-i", png, "-t", str(secs),
                    "-vf", f"pad={W}:{H + BAND}:0:0:color=0x121214,{draws}",
                    "-r", str(FPS), "-pix_fmt", "yuv420p", "-c:v", "libx264",
                    "-preset", "veryslow", "-crf", "30", clip],
                   check=True, capture_output=True)
    clips.append(clip)
    print(f"  beat {i + 1}/{len(BEATS)}  {secs}s  {query}")

opening = card(os.path.join(work, "open.mp4"), 4, [
    ("Tombstone", 54),
    ("The decisions your org already made and forgot.", 28),
    ("Asked as a graph, over the real Kubernetes governance record.", 24),
])
closing = card(os.path.join(work, "close.mp4"), 5, [
    ("Numbers re-checked against the live graph on every push.", 26),
    ("github.com/aviralgarg05/tombstone", 30),
    ("Graph Hacks 2026 - Track 3, Company Brain", 22),
])
clips = [opening] + clips + [closing]

listing = os.path.join(work, "clips.txt")
with open(listing, "w") as fh:
    # Basenames, because the concat demuxer resolves each `file` entry RELATIVE TO THE LISTING,
    # not to the working directory. A path that looks correct from the shell becomes
    # build/walkthrough/build/walkthrough/open.mp4 and fails with a bare exit code. The clips sit
    # beside the listing, so their names alone are right under any ffmpeg, local or containerised.
    fh.writelines(f"file '{os.path.basename(c)}'\n" for c in clips)

subprocess.run([*FFMPEG, "-y", "-f", "concat", "-safe", "0", "-i", listing,
                "-c", "copy", OUT], check=True, capture_output=True)

total = sum(b[1] for b in BEATS) + 9
print(f"\n{OUT}  —  {total}s, {len(BEATS)} beats, {os.path.getsize(OUT) // 1024}KB")

# Fingerprint the sources whose output APPEARS IN THE FRAMES. I argued this file needed no
# staleness guard because its captions state behaviours that named checks already assert -- true
# of the captions, and wrong about the frames. Every answer in this video renders the hash of the
# query that produced it, so changing a Cypher constant leaves the video showing a hash that no
# longer exists. It did: tools.py changed at 05:47 and this was built at 04:04.
import hashlib as _hashlib
import json as _json

# server.py belongs here for the same reason tools.py does, and I only noticed because I
# changed an edge LABEL in it: the video renders reasoning pictures, and the subgraph
# endpoint decides what is in them. A server-side change to the drawing could have left
# this video showing an edge name the product no longer uses, with every check green.
_SOURCES = ("web/app.js", "web/style.css", "web/index.html",
            "src/tombstone/tools.py", "src/tombstone/server.py")
with open("docs/video/.walkthrough-fingerprint.json", "w") as _fh:
    _json.dump({f: _hashlib.sha256(open(f, "rb").read()).hexdigest()[:16] for f in _SOURCES},
               _fh, indent=2, sort_keys=True)
    _fh.write("\n")
print(f"  fingerprinted against {', '.join(_SOURCES)}")
