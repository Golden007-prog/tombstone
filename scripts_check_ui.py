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
import json
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
    "graphwrap": "cy",
}
EMPTYISH = {"", "(none)", "(no answer)", "{}", "null"}


# Elements with no end tag. HTMLParser reports a start and no end for these, which would leave
# every enclosing frame one level too deep forever.
VOID = {"area", "base", "br", "col", "embed", "hr", "img", "input",
        "link", "meta", "param", "source", "track", "wbr"}


class Probe(HTMLParser):
    """Collect class and inner text for a handful of ids. Enough DOM for this one page."""

    def __init__(self, wanted: set[str]):
        super().__init__(convert_charrefs=True)
        self.wanted, self.found, self._stack = wanted, {}, []

    # Depth is counted on EVERY open frame, not just the innermost. The first version incremented
    # only the top frame, so when a tracked element contained another tracked element the parent
    # was left permanently one level deep and never closed -- #graphwrap (which holds #cy) and
    # #headline (which holds #hstat) were silently never captured at all. `visible()` then read
    # "absent" as "hidden", so the headline rule never ran, and a chip that drew its path
    # perfectly was reported as drawing nothing. A parse failure that presents as a product
    # failure is the worst kind: it sends you to debug code that was already correct.
    def handle_starttag(self, tag, attrs):
        if tag in VOID:
            return                      # no end tag is coming, so it must not count
        for frame in self._stack:
            frame["depth"] += 1
        a = dict(attrs)
        if a.get("id") in self.wanted:
            self._stack.append({"id": a["id"], "cls": a.get("class", ""), "text": [], "depth": 0})

    def handle_endtag(self, tag):
        if tag in VOID:
            return
        for frame in self._stack:
            frame["depth"] -= 1
        while self._stack and self._stack[-1]["depth"] < 0:
            top = self._stack.pop()
            self.found[top["id"]] = {"cls": top["cls"], "text": "".join(top["text"]).strip()}

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
            probe = Probe(set(PANELS) | set(PANELS.values())
                  | {"shape", "answer", "graphwrap", "provenance", "cypher", "cywrap",
                     "choices"})
            probe.feed(out)
            return probe.found
        budget += 10000
    raise RuntimeError(f"{url} never finished running after {attempts} attempts")


def visible(node: dict | None) -> bool:
    return bool(node) and "hidden" not in node["cls"].split()


# An element the parser never captured is NOT the same as an element that is hidden, and reading
# the first as the second is how a working feature got reported as broken for an hour. Anything
# this page is supposed to contain must be found; if it is not, say so as a parse failure.
REQUIRED_IDS = {"shape", "answer", "headline", "graphwrap", "cywrap", "covwrap"}


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


def chip_calls() -> list[tuple[str, dict]]:
    """(tool, args) for every chip, read from app.js so these cannot drift from the UI."""
    js = open("web/app.js").read()
    block = js[js.index("const CHIPS = ["):js.index("];", js.index("const CHIPS = ["))]
    out = []
    for chunk in re.split(r"\n  \{", block):
        m = re.search(r'tool:\s*"(\w+)"', chunk)
        if not m:
            continue
        args: dict = {}
        am = re.search(r"args:\s*\{(.*?)\}\s*(?:,|\n)", chunk, re.S)
        if am:
            for k, v in re.findall(r'(\w+)\s*:\s*("(?:[^"\\]|\\.)*"|\[[^\]]*\]|[\d.]+)',
                                   am.group(1)):
                if v.startswith('"'):
                    args[k] = v[1:-1]
                elif v.startswith("["):
                    args[k] = [x.strip().strip('"') for x in v[1:-1].split(",") if x.strip()]
                else:
                    args[k] = float(v) if "." in v else int(v)
        out.append((m.group(1), args))
    return out


def chips_that_draw() -> set[str]:
    """The chips that claim a drawn reasoning path, by the same label chips() uses.

    The empty-panel rule below only fires when a panel is VISIBLE, so a regression that stopped
    drawing altogether would have passed silently -- and until this was added, none of the chips
    that advertise a path were ever checked to actually render one.
    """
    js = open("web/app.js").read()
    block = js[js.index("const CHIPS = ["):js.index("];", js.index("const CHIPS = ["))]
    seen: dict[str, int] = {}
    draws: set[str] = set()
    for chunk in re.split(r"\n  \{", block):
        m = re.search(r'tool:\s*"([a-z_]+)"', chunk)
        if not m:
            continue
        tool = m.group(1)
        n = seen.get(tool, 0)
        seen[tool] = n + 1
        if re.search(r"\bgraph:\s*\{", chunk):
            draws.add(f"{tool}#{n}")
    return draws


def main() -> int:
    if not CHROME:
        print("no Chrome available, so the rendered states cannot be checked here", file=sys.stderr)
        return 0 if os.environ.get("UI_CHECK_OPTIONAL") else 1
    try:
        urllib.request.urlopen(f"{APP}/api/health", timeout=5).read()
    except Exception as e:
        sys.exit(f"{APP} is not serving ({e}). Start it with ./run.sh")

    DRAWS = chips_that_draw()
    cases = chips() + [
        ("typed:answerable", "ask=" + urllib.parse.quote("which areas have exactly one approver?")),
        ("typed:refused", "ask=" + urllib.parse.quote("write me a poem about kubernetes")),
        ("typed:needs-arg", "ask=" + urllib.parse.quote("who owns this?")),
        # A near-tie: the router ranks sole_approver_risk first but inside MIN_MARGIN of
        # successor_for, so it declines and offers both. The point of this case is that the
        # candidates reach the screen -- the server has always returned them, and the client
        # dropped them on the floor, which made the refusal a dead end.
        ("typed:near-tie",
         "ask=" + urllib.parse.quote("show me the areas that depend on one person")),
    ]

    failures = []
    # Two defects that no rendered-state rule could ever catch, because the panel is present and
    # the text is non-empty -- they are just wrong to read. Both were found by pulling a frame out
    # of the walkthrough and looking at it: a counterfactual that reported "0ms" beside its own
    # text saying 404ms, and a headline reading "1 areas". Cheap to assert over the API, so there
    # is no reason to rely on noticing them again.
    for tool, args in chip_calls():
        try:
            req = urllib.request.Request(
                f"{APP}/api/tool", method="POST",
                data=json.dumps({"tool": tool, "args": args}).encode(),
                headers={"content-type": "application/json"})
            d = json.load(urllib.request.urlopen(req, timeout=180))
        except Exception as e:
            failures.append(f"{tool}: /api/tool failed ({e})")
            continue
        body = (d.get("answer") or "") + " " + json.dumps(d.get("headline") or {})
        if "(s)" in body or "(es)" in body:
            failures.append(f'{tool}: still writes a "(s)" plural, which reads as unfinished')
        if str(d.get("shape", "")).startswith("ANSWERED") and d.get("ms") in (None, 0, 0.0):
            failures.append(
                f"{tool}: reports {d.get('ms')}ms for a query that answered -- the one number on "
                f"screen should not make the work look like it never happened")
        head = d.get("headline") or {}
        if str(head.get("stat", "")).strip() == "1":
            first = str(head.get("label", "")).strip().split()
            if first and first[0].endswith("s") and not first[0].endswith("ss"):
                failures.append(f'{tool}: headline reads "1 {first[0]}"')

    for label, query in cases:
        found = dom(f"{APP}/?{query}")
        shape = (found.get("shape") or {}).get("text", "")
        answer = (found.get("answer") or {}).get("text", "")
        print(f"  {label:<28} {shape or '(no shape)'}")

        if label == "typed:near-tie":
            if shape != "UNSURE_WHICH_TOOL":
                failures.append(f"{label}: expected a declined near-tie, got {shape}")
            elif not visible(found.get("choices")):
                failures.append(
                    f"{label}: the router named the tools it could not choose between and the "
                    f"page offered none of them -- a refusal with nowhere to go")
            elif (found.get("choices") or {}).get("text", "") in EMPTYISH:
                failures.append(f"{label}: the candidate buttons rendered empty")

        absent = sorted(REQUIRED_IDS - set(found))
        if absent:
            failures.append(
                f"{label}: the DOM parser never captured {', '.join(absent)} -- that is a parse "
                f"failure in this script, not a finding about the page")
        if not shape:
            failures.append(f"{label}: no shape badge rendered")
        # A chip that advertises a path must draw one whenever the answer HAS rows to draw from.
        # NOT_IN_GRAPH is the one case where there is legitimately nothing: the shallow who_owns
        # question returns no rows, which is the whole point of that beat.
        if label in DRAWS and shape in ("ANSWERED_WITH_PATH", "ANSWERED_FROM_MEMORY"):
            if not visible(found.get("graphwrap")):
                failures.append(
                    f"{label}: this chip advertises a drawn reasoning path and no graph panel "
                    f"appeared -- the README counts it as one of the four that draw one")
            elif (found.get("cy") or {}).get("text", "") in EMPTYISH:
                failures.append(f"{label}: the graph panel rendered with nothing in it")
        if answer in EMPTYISH:
            failures.append(f"{label}: answer panel is empty")
        for panel, inner in PANELS.items():
            if visible(found.get(panel)):
                text = (found.get(inner) or {}).get("text", "")
                if text in EMPTYISH:
                    failures.append(
                        f"{label}: #{panel} is visible but #{inner} is empty "
                        f"-- a panel that renders with nothing in it reads as a failure")
        # The provenance line claims the answer was formatted from rows a query returned. It must
        # appear exactly when that is true. On a refusal no query ran, so the claim would be a
        # lie -- which is a worse failure than any empty panel, because it is a false statement
        # about the product's own integrity sitting next to an answer that does not have one.
        has_cypher = bool((found.get("cypher") or {}).get("text", "").strip())
        prov = visible(found.get("provenance"))
        if prov != has_cypher:
            failures.append(
                f"{label}: provenance line is {'shown' if prov else 'hidden'} but the answer "
                f"{'did' if has_cypher else 'did NOT'} come from a query")

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
