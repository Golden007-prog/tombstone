"""Rebuild docs/img/depth-contrast.gif — the first image in the README — from the running app.

That GIF carries the product's central argument: the same question at depth 1 returns nothing,
and at depth 4 names the person. It is the first thing a judge sees on the page, and it was made
by hand, with no committed pipeline. That is the exact flaw the walkthrough video had before it
got one: an artefact nobody can regenerate goes stale the moment the interface moves, and nothing
notices, because an image cannot be re-queried the way a number can. The drafting screenshot had
already drifted that way — it showed a plural the product had stopped producing.

Both frames are real headless screenshots of the live app through the deep links the UI already
supports, so this cannot drift from the product without the product's own checks drifting too.

Usage:  ./run.sh    (in another shell)
        python scripts_gen_depth_gif.py
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
OUT = "docs/img/depth-contrast.gif"
W, H = 760, 570
HOLD = 25          # frames at 10fps, so 2.5s on each side of the contrast

FRAMES = [
    ("shallow", "run=who_owns&i=0&focus=1"),
    ("deep", "run=who_owns&i=1&focus=1"),
]


def chrome() -> str:
    if os.environ.get("CHROME"):
        return os.environ["CHROME"]
    for c in ("/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
              shutil.which("google-chrome"), shutil.which("chromium"),
              shutil.which("chromium-browser")):
        # Smoke-tested rather than trusted: /usr/local/bin/google-chrome is often a symlink that
        # Chrome cannot execute, because it resolves its framework relative to the executable.
        if c and os.path.exists(c):
            try:
                subprocess.run([c, "--version"], capture_output=True, timeout=20, check=True)
                return c
            except Exception:
                continue
    sys.exit("no working Chrome found; set CHROME=/path/to/chrome")


def ffmpeg(args: list[str], mount: str) -> None:
    """Local ffmpeg if it runs, else a container. A dependency bump can leave the local one
    linked against a dylib that no longer exists, and regenerating should not depend on the
    state of a package manager."""
    try:
        subprocess.run(["ffmpeg", "-version"], capture_output=True, timeout=20, check=True)
        subprocess.run(["ffmpeg", "-y", *args], check=True, capture_output=True)
        return
    except Exception:
        pass
    subprocess.run(
        ["docker", "run", "--rm", "-v", f"{mount}:/w", "-w", "/w",
         "linuxserver/ffmpeg:latest", "-y", *args],
        check=True, capture_output=True)
    print("  (local ffmpeg unusable — used the container)")


def main() -> int:
    try:
        with urllib.request.urlopen(f"{APP}/api/health", timeout=5) as r:
            if b'"up"' not in r.read():
                sys.exit("the app reports FalkorDB down")
    except Exception as e:
        sys.exit(f"{APP} is not serving ({e}). Start it with ./run.sh")

    # A judge on a freshly deployed Space has an empty memory and sees ANSWERED_WITH_PATH. These
    # frames must show that, not the ANSWERED_FROM_MEMORY an afternoon of testing produces.
    try:
        sys.path.insert(0, "src")
        from graphkit.ingest import connect
        connect().select_graph(os.environ.get("GRAPH", "tomb:k8s")).query(
            "MATCH (a:Answer) DETACH DELETE a")
        print("  cleared remembered answers, so both frames show a first visit")
    except Exception as exc:
        print(f"  WARNING: could not clear memory ({exc})")

    chrome_bin = chrome()
    work = tempfile.mkdtemp(prefix="depthgif-")
    shots = []
    for name, query in FRAMES:
        path = os.path.join(work, f"{name}.png")
        with tempfile.TemporaryDirectory() as profile:
            subprocess.run(
                [chrome_bin, "--headless=new", "--disable-gpu", "--hide-scrollbars",
                 "--no-first-run", "--no-default-browser-check", f"--user-data-dir={profile}",
                 "--force-device-scale-factor=1", f"--window-size={W},{H}",
                 "--virtual-time-budget=15000", f"--screenshot={path}", f"{APP}/?{query}"],
                check=True, capture_output=True)
        if os.path.getsize(path) < 15_000:
            sys.exit(f"{name} came back near-empty -- did the page actually run?")
        shots.append(path)
        print(f"  captured {name}  {os.path.getsize(path) // 1024}KB")

    # Hold on each frame rather than crossfading: the point is a comparison, and a reader needs
    # time on each side of it.
    listing = os.path.join(work, "frames.txt")
    with open(listing, "w") as fh:
        for _ in range(2):                      # two full cycles, so it reads as deliberate
            for shot in shots:
                for _f in range(HOLD):
                    fh.write(f"file '{os.path.basename(shot)}'\nduration 0.1\n")
        fh.write(f"file '{os.path.basename(shots[-1])}'\n")

    out_abs = os.path.abspath(OUT)
    ffmpeg(["-f", "concat", "-safe", "0", "-i", "frames.txt",
            "-vf", f"fps=10,scale={W}:-1:flags=lanczos,split[a][b];[a]palettegen[p];[b][p]paletteuse",
            out_abs if os.path.dirname(out_abs).startswith(work) else "/w/out.gif"], work)
    produced = os.path.join(work, "out.gif")
    if os.path.exists(produced):
        shutil.move(produced, OUT)
    # Same guard as the screenshots: record what interface this was a picture of, so a UI change
    # fails a check instead of quietly leaving the README's first image showing an older product.
    import hashlib
    with open("docs/img/.depthgif-fingerprint.json", "w") as fh:
        json.dump({f: hashlib.sha256(open(f, "rb").read()).hexdigest()[:16]
                   for f in ("web/app.js", "web/style.css", "web/index.html")},
                  fh, indent=2, sort_keys=True)
        fh.write("\n")
    print(f"  {OUT}  {W}x{H}  {os.path.getsize(OUT) // 1024}KB, fingerprinted")
    shutil.rmtree(work, ignore_errors=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
