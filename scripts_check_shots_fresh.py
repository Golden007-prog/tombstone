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

I overrode that paragraph without reading it. A comment I added to `web/app.js` staled three
artefacts, nothing said so for two commits, and I concluded the exclusion was an oversight and put
this in CI -- where the reasoning above says a failure is unfixable and therefore ignorable. The
paragraph was right and I had quoted from this very file earlier the same day.

The actual gap was narrower, and `--hashes-only` is it: the hash comparison needs no app and no
browser, so it can run in the push gate, on the machine that CAN regenerate, at the moment the
staleness is introduced. The live `path.svg` probe still needs a served instance and stays in
preflight. That catches what happened to me without putting an unfixable failure in CI.

Run: python scripts_check_shots_fresh.py
"""
from __future__ import annotations

import hashlib
import json
import os
import sys

# No SOURCES list here any more. This file used to keep its own copy of what each artefact
# depends on, and it fell behind the generators twice -- a list that looks authoritative
# and is out of date is worse than no list, because it reads as the answer. Each
# fingerprint now declares its own sources and this file hashes exactly those.
# Two generators, two fingerprints, because running one must not mark the other's output fresh.
# depth-contrast.gif is the README's FIRST image and carries the product's central argument, and
# until today it was hand-made with no pipeline at all -- the same flaw the walkthrough video had.
ARTEFACTS = (
    ("docs/img/.shots-fingerprint.json", "scripts_gen_readme_shots.py",
     ("docs/img/drafted-patch.png", "docs/img/keyless-refusal.png")),
    ("docs/img/.depthgif-fingerprint.json", "scripts_gen_depth_gif.py",
     ("docs/img/depth-contrast.gif",)),
    # The walkthrough too, and it is the one I argued did not need this. Its CAPTIONS state
    # behaviours that named checks assert, which is why they cannot go quietly wrong -- but its
    # FRAMES render the hash of the query behind every answer, so changing a Cypher constant
    # leaves the video showing a hash that no longer exists. It had: tools.py moved at 05:47 and
    # the video was built at 04:04. Hence tools.py in its source list and not in the others'.
    ("docs/video/.walkthrough-fingerprint.json", "scripts_build_walkthrough.py",
     ("docs/video/walkthrough-silent.mp4",)),
)


def _hash(path: str) -> str:
    return hashlib.sha256(open(path, "rb").read()).hexdigest()[:16]


HASHES_ONLY = "--hashes-only" in sys.argv


def main() -> int:
    bad = 0
    # Hash exactly whatever each fingerprint recorded, instead of keeping a second list here that
    # has to be edited every time a generator's sources change. That second list was the bug twice
    # running: server.py and then agent.py were added to the generators while this file still
    # hashed its own older set, so a source the artefact genuinely depended on went unchecked.
    # A key recorded by a generator and unreadable here should fail loudly, not be skipped.
    now: dict[str, str] = {}
    for _fp, _gen, _imgs in ARTEFACTS:
        if not os.path.exists(_fp):
            continue
        for _src in json.load(open(_fp)):
            if _src in now:
                continue
            if not os.path.exists(_src):
                print(f"  FAIL  {_fp} was taken against {_src}, which no longer exists")
                bad += 1
                continue
            now[_src] = _hash(_src)
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
        if not recorded:
            # A fingerprint recording nothing makes the comparison below vacuous: there are no
            # sources to compare, so `moved` comes out empty and this printed "matches the code
            # and corpus it was made from" about a file it had not looked at. Same shape as the
            # doc-counts guard that reported success over zero claims.
            print(f"  FAIL  {fingerprint} records no sources, so nothing was compared"
                  f" — regenerate it")
            bad += 1
            continue
        # Compare only the sources that artefact was fingerprinted against: the images do not
        # render a query hash, the video does.
        moved = [f for f in recorded if recorded.get(f) != now.get(f)]
        if moved:
            # Not "the interface changed": these fingerprints now cover the corpus and build.py
            # too, and a reseed is not an interface change. Naming the wrong cause sends whoever
            # reads this to the wrong file.
            print(f"  FAIL  {', '.join(os.path.basename(i) for i in images)} "
                  f"{'is' if len(images) == 1 else 'are'} out of date — what "
                  f"{'it was' if len(images) == 1 else 'they were'} made from has changed:")
            for f in moved:
                print(f"          {f}  {recorded.get(f, 'not recorded')} -> {now[f]}")
            print(f"        ./run.sh in another shell, then: python {generator}")
            bad += 1
        else:
            print(f"  {', '.join(os.path.basename(i) for i in images)} "
                  f"{'matches' if len(images) == 1 else 'match'} the code and corpus "
                  f"{'it was' if len(images) == 1 else 'they were'} made from")
    if HASHES_ONLY:
        # The push gate's half: hashes only, no served instance needed. Said out loud rather than
        # skipped silently, so nobody mistakes this for the full check.
        print("  (hashes only — the live path.svg probe needs ./run.sh; ./preflight.sh does it)")
        return bad
    return bad + _figure_matches_its_data()


def _figure_matches_its_data() -> int:
    """docs/img/path.svg is the one README artefact with a generator but no freshness guard.

    A fingerprint is the wrong instrument for it. The other three are pictures of the INTERFACE,
    so hashing web/* catches drift. This one is drawn from graph DATA -- a subgraph for one path --
    so the interface could sit still while the figure quietly stops describing the graph. That is
    the same failure as a stale number in the README, and every number in the README is checked
    against the live graph, so this should be too.

    The path comes out of the generator rather than being repeated here; a check that keeps its own
    copy of the thing it is checking drifts from it, which is how the demo script came to state a
    word count nobody re-derived.
    """
    import re
    import urllib.request

    svg_path, gen = "docs/img/path.svg", "scripts_gen_readme_figure.py"
    if not os.path.exists(svg_path):
        print(f"  FAIL  {svg_path} is missing — run {gen}")
        return 1
    url = re.search(r'urlopen\("([^"]+)"\)', open(gen).read())
    if not url:
        print(f"  FAIL  cannot find the API call in {gen}, so the figure's source is unknown")
        return 1
    try:
        with urllib.request.urlopen(url.group(1), timeout=20) as r:
            live = json.load(r)
    except Exception as exc:
        print(f"  FAIL  {svg_path} could not be checked against {url.group(1)} ({exc})")
        return 1

    svg = open(svg_path).read()
    drawn = {re.sub(r"<[^>]+>", "", t).strip()
             for t in re.findall(r"<text[^>]*>.*?</text>", svg, re.S)}
    missing = []
    for node in live["nodes"]:
        label = node.get("label") or node.get("id") or ""
        # The renderer truncates long titles with an ellipsis, so a drawn label matches when it is
        # the live one or a prefix of it.
        if not any(d == label or (d.endswith("…") and label.startswith(d[:-1])) for d in drawn):
            missing.append(label)
    if missing:
        print(f"  FAIL  {svg_path} no longer draws what that subgraph returns; absent now:")
        for m in missing[:6]:
            print(f"          {m[:60]}")
        # No redirect: the generator writes the file itself and prints a summary line, so
        # `> docs/img/path.svg` would overwrite the figure with that one line of text.
        print(f"        ./run.sh in another shell, then: python {gen}")
        return 1
    # The generator keeps its own hand-written copy of the dark palette, because an SVG in a
    # README cannot read a stylesheet. Eight of its nine colours matched web/style.css and one did
    # not: --edge had moved and the copy had not. Nothing observable broke, which is exactly why it
    # went unnoticed -- so the duplication is now asserted rather than trusted.
    css = open("web/style.css").read().lower()
    adrift = sorted({c for c in re.findall(r"#[0-9a-f]{6}", open(gen).read().lower())
                     if c not in css})
    if adrift:
        print(f"  FAIL  {gen} draws colours web/style.css no longer defines: {', '.join(adrift)}")
        return 1
    print(f"  path.svg still draws all {len(live['nodes'])} nodes that subgraph returns, "
          f"in the stylesheet's own palette")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
