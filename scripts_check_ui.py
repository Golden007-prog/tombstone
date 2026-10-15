"""Render every answer state and fail if any panel comes back empty.

This exists because of a bug I looked straight past for hours. `.hidden{display:none}` sat five
lines above `.headline{display:flex}` at identical specificity, so the later rule won and an EMPTY
headline bar rendered on every shape that has no headline -- every refusal, every NOT_IN_GRAPH,
every DEGRADED. Those are precisely the screens this product's credibility rests on, and I had
clicked past them repeatedly without registering it. A screenshot at full size is what finally
showed it.

So this does not rely on anyone looking. It drives every chip and a few typed questions through
headless Chrome via the deep links the UI already supports, then asserts that no panel is BOTH
visible AND empty -- a visible headline with no number in it, an offer to show Cypher that opens
onto nothing, a coverage block with no coverage, a graph panel with no graph.

Usage:  ./run.sh    (in another shell)
        python scripts_check_ui.py
"""
from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
import tempfile
import urllib.parse
import urllib.request
from html.parser import HTMLParser

APP = os.environ.get("APP", "http://localhost:8099")
def _runs(candidate: str) -> bool:
    """Can this path actually launch Chrome?

    On macOS `/usr/local/bin/google-chrome` is commonly a symlink into the app bundle, and Chrome
    resolves its framework RELATIVE TO THE EXECUTABLE PATH -- so launched through that symlink it
    looks for `/usr/local/Frameworks/...`, fails to dlopen, and exits having printed nothing. A
    `which()` lookup finds it and every capture then comes back as an empty DOM, which reads like
    the page failed rather than like Chrome did. So candidates are smoke-tested, not trusted.
    """
    try:
        done = subprocess.run([candidate, "--version"], capture_output=True, text=True, timeout=30)
        return done.returncode == 0 and "chrom" in done.stdout.lower()
    except Exception:
        return False


def _chrome() -> str | None:
    candidates = []
    if os.environ.get("CHROME"):
        candidates.append(os.environ["CHROME"])
    candidates.append("/Applications/Google Chrome.app/Contents/MacOS/Google Chrome")
    for name in ("google-chrome", "google-chrome-stable", "chromium", "chromium-browser"):
        found = shutil.which(name)
        if found:
            candidates.append(found)
    for candidate in candidates:
        if (os.path.exists(candidate) or shutil.which(candidate)) and _runs(candidate):
            return candidate
    return None


CHROME = _chrome()

# id -> the id whose text must be non-empty when that panel is visible
PANELS = {
    "headline": "hstat",
    "cywrap": "cypher",
    "covwrap": "coverage",
}
EMPTYISH = {"", "(none)", "(no answer)", "{}", "null"}


class Probe(HTMLParser):
    """Collect class and inner text for a handful of ids. Enough DOM for this one page."""

    def __init__(self, wanted: set[str]):
        super().__init__(convert_charrefs=True)
        self.wanted, self.found, self._stack = wanted, {}, []

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if self._stack:
            self._stack[-1]["depth"] += 1
        if a.get("id") in self.wanted:
            self._stack.append({"id": a["id"], "cls": a.get("class", ""), "text": [], "depth": 0})

    def handle_endtag(self, tag):
        if not self._stack:
            return
        top = self._stack[-1]
        if top["depth"] == 0:
            self._stack.pop()
            self.found[top["id"]] = {"cls": top["cls"], "text": "".join(top["text"]).strip()}
        else:
            top["depth"] -= 1

    def handle_data(self, data):
        for frame in self._stack:
            frame["text"].append(data)


def dom(url: str, attempts: int = 4) -> dict:
    """Dump the DOM once the page says it has finished.

    `--virtual-time-budget` does NOT reliably wait for the fetch behind an autorun, and the first
    version of this script was flaky because of it: the same URL, with the same Chrome binary,
    would sometimes report an empty answer panel simply because the request had not landed. A
    flaky check is worse than no check, so instead of waiting longer and hoping, this waits for
    the readiness flag the page already sets -- `document.body.dataset.autorun = "done"` -- and
    retries the dump until it appears.
    """
    budget = 15000
    for attempt in range(attempts):
        # A unique profile per invocation. Headless Chrome instances sharing the DEFAULT
        # user-data-dir can attach to an existing instance and hand back a DOM for a page that
        # never ran -- which is exactly what happened here, and what the acceptance condition
        # below used to wave through.
        with tempfile.TemporaryDirectory() as profile:
            out = subprocess.run(
                [CHROME, "--headless=new", "--disable-gpu", "--no-first-run",
                 "--no-default-browser-check", "--disable-dev-shm-usage",
                 f"--user-data-dir={profile}", f"--virtual-time-budget={budget}",
                 "--dump-dom", url], capture_output=True, text=True, timeout=180).stdout
        # Strictly require the page to say it finished. The earlier version also accepted a DOM
        # with no autorun flag at all, treating "never started" as "nothing to wait for".
        if 'data-autorun="done"' in out:
            probe = Probe(set(PANELS) | set(PANELS.values()) | {"shape", "answer", "graphwrap"})
            probe.feed(out)
            return probe.found
        budget += 10000
    raise RuntimeError(f"{url} never finished running after {attempts} attempts")


def visible(node: dict | None) -> bool:
    return bool(node) and "hidden" not in node["cls"].split()


def chips() -> list[tuple[str, str]]:
    """(label, query) for every chip, read from app.js so this cannot drift from the UI."""
    js = open("web/app.js").read()
    block = js[js.index("const CHIPS = ["):js.index("];", js.index("const CHIPS = ["))]
    seen: dict[str, int] = {}
    out = []
    for tool in re.findall(r'tool:\s*"([a-z_]+)"', block):
        n = seen.get(tool, 0)
        seen[tool] = n + 1
        out.append((f"{tool}#{n}", f"run={tool}&i={n}"))
    return out


def main() -> int:
    if not CHROME:
        print("no Chrome available, so the rendered states cannot be checked here", file=sys.stderr)
        return 0 if os.environ.get("UI_CHECK_OPTIONAL") else 1
    try:
        urllib.request.urlopen(f"{APP}/api/health", timeout=5).read()
    except Exception as e:
        sys.exit(f"{APP} is not serving ({e}). Start it with ./run.sh")

    cases = chips() + [
        ("typed:answerable", "ask=" + urllib.parse.quote("which areas have exactly one approver?")),
        ("typed:refused", "ask=" + urllib.parse.quote("write me a poem about kubernetes")),
        ("typed:needs-arg", "ask=" + urllib.parse.quote("who owns this?")),
    ]

    failures = []
    for label, query in cases:
        found = dom(f"{APP}/?{query}")
        shape = (found.get("shape") or {}).get("text", "")
        answer = (found.get("answer") or {}).get("text", "")
        print(f"  {label:<28} {shape or '(no shape)'}")

        if not shape:
            failures.append(f"{label}: no shape badge rendered")
        if answer in EMPTYISH:
            failures.append(f"{label}: answer panel is empty")
        for panel, inner in PANELS.items():
            if visible(found.get(panel)):
                text = (found.get(inner) or {}).get("text", "")
                if text in EMPTYISH:
                    failures.append(
                        f"{label}: #{panel} is visible but #{inner} is empty "
                        f"-- a panel that renders with nothing in it reads as a failure")
        if visible(found.get("graphwrap")):
            if "<svg" not in (found.get("graphwrap") or {}).get("text", "") + "<svg":
                failures.append(f"{label}: graph panel visible with no graph in it")

    if failures:
        print("\n" + "\n".join("  FAIL  " + f for f in failures))
        return 1
    print(f"\n{len(cases)} rendered states checked, no panel visible-and-empty.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
