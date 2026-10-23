"""Generate the README's screenshots from the running app, so they cannot go stale silently.

The drafting action is the thing this product does that the others do not, and it had no image on
a page that judges skim. Committing a screenshot is easy; committing one that quietly stops
matching the app is the failure mode. So these are generated from the live app through the same
deep links the walkthrough uses, and regenerating them is one command.

Usage:  ./run.sh    (in another shell)
        python scripts_gen_readme_shots.py
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
import urllib.request

APP = os.environ.get("APP", "http://localhost:8099")


# The README's screenshots must show what a judge sees on a freshly deployed Space, which is an
# EMPTY memory and so ANSWERED_WITH_PATH. Regenerating these after an afternoon of testing
# captured ANSWERED_FROM_MEMORY instead -- true, and not the first thing a reader should meet.
# The walkthrough builder has cleared memory before capture for exactly this reason; the shots
# did not, which is how the two drifted apart.
# agent.py writes the PROSE in every one of these frames, and it was not here. A rendering
# change -- "6 decisions" to "6 decisions, including" -- left all three artefacts stale
# while every freshness check reported them current. tools.py was listed because frames
# render query hashes; the sentence above the hash is at least as load-bearing.
SHOT_SOURCES = ("scripts_gen_readme_shots.py",
                "web/app.js", "web/style.css", "web/index.html",
                "src/tombstone/agent.py",
                # The data in these frames comes from the corpus through build.py. A reseed
                # changes names and counts on screen while every file above is untouched.
                "data/corpus.json.gz", "src/tombstone/build.py",
                # drafted-patch.png is the output of _draft_owners_patch, which selects its
                # candidates with a tools.py query and builds each diff in act.py. Either one
                # changes what that image shows without touching anything above.
                "src/tombstone/tools.py", "src/tombstone/act.py")
FINGERPRINT = "docs/img/.shots-fingerprint.json"


def _fingerprint() -> dict:
    """What the UI looked like when these images were taken.

    A screenshot's content IS the interface, so a UI change can invalidate it in a way nothing
    else notices -- drafted-patch.png sat in the README for a day showing "1 candidate(s)", a
    plural the product had stopped producing. mtimes cannot answer this: a fresh clone gives every
    file the same checkout time. A hash of the files that decide what the page looks like can.
    """
    import hashlib
    return {f: hashlib.sha256(open(f, "rb").read()).hexdigest()[:16] for f in SHOT_SOURCES}


def _write_fingerprint() -> None:
    import json as _json
    with open(FINGERPRINT, "w") as fh:
        _json.dump(_fingerprint(), fh, indent=2, sort_keys=True)
        fh.write("\n")


def _clear_memory() -> None:
    try:
        sys.path.insert(0, "src")
        from graphkit.ingest import connect as _connect
        _connect().select_graph(os.environ.get("GRAPH", "tomb:k8s")).query(
            "MATCH (a:Answer) DETACH DELETE a")
        print("  cleared remembered answers, so the shots show a first visit")
    except Exception as exc:
        print(f"  WARNING: could not clear memory ({exc}); shots may show ANSWERED_FROM_MEMORY")


_clear_memory()
OUT = "docs/img"

SHOTS = [
    ("drafted-patch.png", "run=draft_owners_patch&focus=1", 1280, 1400),
    ("keyless-refusal.png", "ask=write+me+a+poem+about+kubernetes&focus=1", 1280, 420),
]


def chrome() -> str | None:
    if os.environ.get("CHROME"):
        return os.environ["CHROME"]
    mac = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
    if os.path.exists(mac):
        return mac
    for name in ("google-chrome", "google-chrome-stable", "chromium", "chromium-browser"):
        found = shutil.which(name)
        if found:
            return found
    return None


CHROME = chrome()
if not CHROME:
    sys.exit("no Chrome found; set CHROME=/path/to/chrome")
try:
    with urllib.request.urlopen(f"{APP}/api/health", timeout=5) as r:
        if b'"up"' not in r.read():
            sys.exit("the app reports FalkorDB down")
except Exception as e:
    sys.exit(f"{APP} is not serving ({e}). Start it with ./run.sh")

os.makedirs(OUT, exist_ok=True)
for name, query, width, height in SHOTS:
    path = os.path.join(OUT, name)
    # A fresh profile per capture: headless Chrome instances sharing the default user-data-dir can
    # attach to an existing one and screenshot a page that never ran.
    with tempfile.TemporaryDirectory() as profile:
        subprocess.run(
            [CHROME, "--headless=new", "--disable-gpu", "--hide-scrollbars", "--no-first-run",
             "--no-default-browser-check", f"--user-data-dir={profile}",
             "--force-device-scale-factor=1", f"--window-size={width},{height}",
             "--virtual-time-budget=15000", f"--screenshot={path}", f"{APP}/?{query}"],
            check=True, capture_output=True)
    size = os.path.getsize(path)
    if size < 15_000:
        sys.exit(f"{name} came back near-empty ({size} bytes) -- did the page actually run?")
    print(f"  {name}  {width}x{height}  {size // 1024}KB")

_write_fingerprint()
print(f"  fingerprinted against {', '.join(SHOT_SOURCES)}")
