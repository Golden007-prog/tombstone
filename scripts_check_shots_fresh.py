"""Are the README's screenshots still pictures of this interface?

drafted-patch.png sat in the README for a day showing "1 candidate(s) refused" -- a plural the
product had stopped producing that afternoon. Nothing noticed, because an image cannot be
re-queried the way a number can, and mtimes say nothing useful: a fresh clone gives every file
the same checkout time.

So the generator records a hash of the three files that decide what the page looks like, and this
compares. It lives in ./preflight.sh and NOT in CI, deliberately: regenerating needs a running app
and a browser, so the right moment to be told is while you are at the machine that has both. A
cosmetic edit turning CI red for a screenshot nobody can regenerate there is the kind of check
people learn to skip.

Run: python scripts_check_shots_fresh.py
"""
from __future__ import annotations

import hashlib
import json
import os
import sys

SOURCES = ("web/app.js", "web/style.css", "web/index.html")
# Two generators, two fingerprints, because running one must not mark the other's output fresh.
# depth-contrast.gif is the README's FIRST image and carries the product's central argument, and
# until today it was hand-made with no pipeline at all -- the same flaw the walkthrough video had.
ARTEFACTS = (
    ("docs/img/.shots-fingerprint.json", "scripts_gen_readme_shots.py",
     ("docs/img/drafted-patch.png", "docs/img/keyless-refusal.png")),
    ("docs/img/.depthgif-fingerprint.json", "scripts_gen_depth_gif.py",
     ("docs/img/depth-contrast.gif",)),
)


def main() -> int:
    bad = 0
    now = {f: hashlib.sha256(open(f, "rb").read()).hexdigest()[:16] for f in SOURCES}
    for fingerprint, generator, images in ARTEFACTS:
        missing = [i for i in images if not os.path.exists(i)]
        if missing:
            print("  FAIL  the README references images that do not exist: " + ", ".join(missing))
            bad += 1
            continue
        if not os.path.exists(fingerprint):
            print(f"  FAIL  {fingerprint} is missing — run {generator}")
            bad += 1
            continue
        recorded = json.load(open(fingerprint))
        moved = [f for f in SOURCES if recorded.get(f) != now[f]]
        if moved:
            print(f"  FAIL  the interface changed since {', '.join(os.path.basename(i) for i in images)} "
                  f"{'was' if len(images) == 1 else 'were'} taken:")
            for f in moved:
                print(f"          {f}  {recorded.get(f, 'not recorded')} -> {now[f]}")
            print(f"        ./run.sh in another shell, then: python {generator}")
            bad += 1
        else:
            print(f"  {', '.join(os.path.basename(i) for i in images)} "
                  f"{'was' if len(images) == 1 else 'were'} taken from this exact interface")
    return 1 if bad else 0


if __name__ == "__main__":
    raise SystemExit(main())
