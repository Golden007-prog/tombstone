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
FINGERPRINT = "docs/img/.shots-fingerprint.json"
SHOTS = ("docs/img/drafted-patch.png", "docs/img/keyless-refusal.png")


def main() -> int:
    missing = [s for s in SHOTS if not os.path.exists(s)]
    if missing:
        print("  FAIL  the README references screenshots that do not exist: " + ", ".join(missing))
        return 1
    if not os.path.exists(FINGERPRINT):
        print(f"  FAIL  {FINGERPRINT} is missing — run scripts_gen_readme_shots.py")
        return 1

    recorded = json.load(open(FINGERPRINT))
    now = {f: hashlib.sha256(open(f, "rb").read()).hexdigest()[:16] for f in SOURCES}
    moved = [f for f in SOURCES if recorded.get(f) != now[f]]
    if moved:
        print("  FAIL  the interface changed since the README's screenshots were taken:")
        for f in moved:
            print(f"          {f}  {recorded.get(f, 'not recorded')} -> {now[f]}")
        print("        ./run.sh in another shell, then: python scripts_gen_readme_shots.py")
        return 1
    print(f"  the README's screenshots were taken from this exact interface "
          f"({', '.join(os.path.basename(s) for s in SHOTS)})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
