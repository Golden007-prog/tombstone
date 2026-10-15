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
OUT = "docs/img"

SHOTS = [
    ("drafted-patch.png", "run=draft_owners_patch&focus=1", 1280, 980),
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
