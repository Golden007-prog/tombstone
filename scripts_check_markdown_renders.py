"""Render the README through GitHub's own markdown API and check nothing silently broke.

Markdown tables fail quietly: one stray pipe inside a cell and GitHub renders the whole block as
a paragraph of text with pipes in it. Nothing errors, the file still looks fine in an editor, and
you find out when someone opens the repo. The page is mostly tables and was edited about twenty
times in a day. The count is derived below and printed, not stated here: this sentence said
"twelve" until the page rendered seventeen, which is a stale number inside the very script whose
job is catching stale rendering -- a comment is not exempt from the thing the file is about.

So this asks GitHub to render it and asserts that every table that should be a table is one, that
every image resolves, and that each `#anchor` used in the page matches a heading GitHub actually
produced -- using GitHub's renderer rather than a local approximation of it.
"""
from __future__ import annotations

import json
import os
import re
import sys
import urllib.error
import urllib.request

README = "README.md"
md = open(README).read()

req = urllib.request.Request(
    "https://api.github.com/markdown",
    data=json.dumps({"text": md, "mode": "gfm",
                     "context": "aviralgarg05/tombstone"}).encode(),
    headers={"content-type": "application/json", "accept": "application/vnd.github+json",
             "user-agent": "tombstone-markdown-check"})
token = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
if token:
    req.add_header("authorization", f"Bearer {token}")
try:
    html = urllib.request.urlopen(req, timeout=30).read().decode()
except urllib.error.HTTPError as e:
    # Rate limiting without a token is not a reason to fail a build.
    if e.code in (403, 429) and not token:
        print("  GitHub markdown API rate-limited and no token available; skipping")
        sys.exit(0)
    raise

fails = []

outside_fences = re.sub(r"```.*?```", "", md, flags=re.S)
expected_tables = len(re.findall(r"^\|[\s:|-]+\|\s*$", outside_fences, re.M))
got_tables = html.count("<table")
ok = expected_tables == got_tables
print(f"  {'PASS' if ok else 'FAIL'}  tables: {expected_tables} written, {got_tables} rendered")
if not ok:
    fails.append("a markdown table did not render as a table")

images_md = len(re.findall(r"!\[[^\]]*\]\(", md))
images_html = len(re.findall(r"<img", html))
ok = images_html >= images_md
print(f"  {'PASS' if ok else 'FAIL'}  images: {images_md} written, {images_html} rendered")
if not ok:
    fails.append("an image did not render")

# Every in-page link must point at a heading GitHub actually emitted.
heading_ids = set(re.findall(r'id="user-content-([^"]+)"', html))
if heading_ids:
    for anchor in sorted(set(re.findall(r"\]\(#([a-z0-9-]+)\)", md))):
        if anchor not in heading_ids:
            print(f"  FAIL  anchor #{anchor} matches no heading GitHub produced")
            fails.append(f"#{anchor}")
    print(f"  PASS  {len(heading_ids)} heading anchors, every in-page link resolves")
else:
    print("  note  this API response carries no heading ids; anchors not checkable here")

print(f"\n{'FAILED' if fails else 'OK'}: the README renders "
      f"{'with problems' if fails else 'cleanly'} on GitHub")

# Internal anchors. A link to a heading that does not exist scrolls nowhere and looks like a
# broken page, and nothing here checked them: I wrote one pointing at
# "#the-correction-i-made..." when the heading begins "A correction I made", and preflight passed.
# GitHub's slug rules, near enough: lowercase, strip inline code and emphasis and punctuation,
# spaces to hyphens.
import re as _re

def _slug(h: str) -> str:
    h = _re.sub(r"`|\*\*|\*|_", "", h.strip().lower())
    return _re.sub(r"[^\w \-]", "", h).replace(" ", "-")


_anchor_problems = []
for _doc in ("README.md", "SUBMISSION.md", "docs/EXPLAIN-IT.md", "docs/BLOG-POST.md"):
    try:
        _t = open(_doc).read()
    except FileNotFoundError:
        continue
    _heads = {_slug(h) for h in _re.findall(r"^#{2,4} (.+)$", _t, _re.M)}
    for _l in sorted(set(_re.findall(r"\]\(#([a-z0-9\-]+)\)", _t))):
        if _l not in _heads:
            _anchor_problems.append(f"{_doc}: link to #{_l} matches no heading")
# Relative file links too. Same failure as a bad anchor and easier to cause: three helpers came
# out of graphkit tonight and a dead method out of tools.py, any of which a document could have
# been pointing at. None was, but nothing would have said so.
import pathlib as _pathlib

_rel_total = 0
for _doc in ("README.md", "SUBMISSION.md", "docs/EXPLAIN-IT.md", "docs/BLOG-POST.md",
             "docs/video/README.md", "deploy/README-hf-space.md", "docs/GROUND-TRUTH.md"):
    _p = _pathlib.Path(_doc)
    if not _p.exists():
        continue
    for _l in _re.findall(r"\]\(([^)#][^)]*)\)", _p.read_text()):
        if _l.startswith(("http://", "https://", "mailto:", "#")):
            continue
        _rel_total += 1
        if not (_p.parent / _l.split("#")[0]).resolve().exists():
            _anchor_problems.append(f"{_doc}: links to {_l}, which does not exist")

if _anchor_problems:
    print()
    for _p2 in _anchor_problems:
        print(f"  FAIL  {_p2}")
    raise SystemExit(1)
print(f"  every internal anchor points at a heading that exists, and all {_rel_total} "
      f"relative links resolve")

sys.exit(1 if fails else 0)
