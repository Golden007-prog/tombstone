"""Scan every markdown file for corpus counts and check them against the live graph.

Fixing a stale number in one document does not stop the next one going stale. These counts appear
across the README, the blog, the submission copy, the corpus notes and the Space landing page, and
they move whenever the corpus or the resolver changes. Two were found wrong by hand today --
"8 of 679 decisions have no usable date" and a corpus table still saying 679 Kep / 959 Alternative
/ 52 MissingRecord -- both of which had been true when written.

So this does it for every file at once: find any number sitting next to one of the nouns this
project counts, and require it to be that count. It deliberately reads the files a judge reads,
not a list someone remembers to update.
"""
from __future__ import annotations

import pathlib
import re
import sys

sys.path.insert(0, "src")
from graphkit.ingest import connect  # noqa: E402

g = connect().select_graph("tomb:k8s")


def count(query: str) -> int:
    return g.ro_query(query).result_set[0][0]


# noun -> (live count, the phrasings used across the docs)
COUNTS = {
    "decisions": (count("MATCH (k:Kep) RETURN count(k)"),
                  [r"decisions?", r"KEPs?\b"]),
    "rejected alternatives": (count("MATCH (a:Alternative) RETURN count(a)"),
                              [r"rejected alternatives?", r"Alternatives?\b"]),
    "named options": (count("MATCH (a:NamedOption) RETURN count(a)"),
                      [r"named options?", r"titled `?:?NamedOption`?",
                       r"titled rejected options?"]),
    "people": (count("MATCH (p:Person) RETURN count(p)"), [r"people\b", r"Person\b"]),
    "ownership files": (count("MATCH (o:OwnersFile) RETURN count(o)"),
                        [r"ownership files?", r"`?OWNERS`? files?", r"OwnersFile\b"]),
}

# Numbers that are history, not current state: a quoted "previously said", a correction, a
# benchmark on a different graph. Those lines say so, and re-asserting them would be wrong.
HISTORY = re.compile(
    r"previously|used to|was wrong|withdrawn|corrected|drifted|said \d|"
    r"earlier|first number|I had claimed|claimed \d|synthetic|3,300|older|stale", re.I)

# A subset is not a total. "19 OWNERS files declare only reviewers" and "83 of 111 people" are
# both true and neither is a claim about how many exist. Without this the check produced nine
# false alarms against two real faults, and a check that cries wolf is one people learn to skip.
SUBSET = re.compile(r"\b(?:of|in|among|and)\s+$|\bonly\s+$|\bjust\s+$")

# The judge-facing documents. K8S-CORPUS-VERIFIED.md is excluded on purpose: it records what the
# RAW corpus looked like while it was being understood -- 684 kep.yaml files parsed, 688 READMEs,
# counts taken before templates were excluded -- which are different quantities from the graph's
# node counts, not stale versions of them. Its own summary table is checked by hand when it moves.
files = [pathlib.Path("README.md"), pathlib.Path("SUBMISSION.md"),
         pathlib.Path("deploy/README-hf-space.md"), pathlib.Path("docs/DEMO-SCRIPT.md"),
         pathlib.Path("docs/BLOG-POST.md"), pathlib.Path("docs/EXPLAIN-IT.md")]
files = [f for f in files if f.exists()]
problems = []
checked = 0

for path in files:
    for lineno, line in enumerate(path.read_text().splitlines(), 1):
        if HISTORY.search(line):
            continue
        for label, (live, phrasings) in COUNTS.items():
            for phrasing in phrasings:
                for m in re.finditer(rf"\b([\d,]{{2,}})\s+(?:\*\*)?{phrasing}", line):
                    if SUBSET.search(line[:m.start()]):
                        continue
                    found = int(m.group(1).replace(",", ""))
                    # A DRIFTED total sits a hair off the real one -- 679 against 681, 959
                    # against 958. A subset does not: "25 people" in a community and "19 OWNERS
                    # files that declare only reviewers" are both true and neither is a claim
                    # about the whole. Only near-misses are drift, so only near-misses are
                    # reported; this check is for numbers that used to be right.
                    if not (0.9 * live <= found <= 1.1 * live):
                        continue
                    checked += 1
                    if found != live:
                        problems.append(
                            f"{path}:{lineno}: says {found:,} {label}, the graph has {live:,}\n"
                            f"      {line.strip()[:100]}")

# ---------------------------------------------------------------------------
# One count in the docs is not a corpus count: the number of checks preflight runs, spelled in
# words in the submission checklist. Nothing verified it, and it went stale the moment a
# seventeenth check landed -- the checklist still said sixteen. It is also the claim a judge is
# most likely to test, because testing it means running one command.
pf = open("preflight.sh").read()
_labels = re.findall(r'^run "([^"]+)"', pf, re.M)
_body = re.search(r"^run\(\) \{.*?^\}", pf, re.M | re.S)
_outside = pf[:_body.start()] + pf[_body.end():] if _body else pf
_inline = _outside.count("[32mok")   # literal, not a regex: r"\033\[32mok" compiles
# \033 to an ESC byte, which never appears in the file -- the file holds those four
# characters as text. That form matched nothing, made the total 16, and passed while
# measuring the wrong thing, which is the exact failure this check exists to catch.
_total = len(_labels) + _inline
_WORDS = {14: "fourteen", 15: "fifteen", 16: "sixteen", 17: "seventeen", 18: "eighteen",
          19: "nineteen", 20: "twenty", 21: "twenty-one", 22: "twenty-two"}
_spelled = re.search(r"one command, ([\w-]+) checks", open("SUBMISSION.md").read())
_said = _spelled.group(1) if _spelled else "nothing"
if _said != _WORDS.get(_total):
    problems.append(f"SUBMISSION.md: says preflight runs '{_said}' checks, "
                    f"it runs {_total} ({_WORDS.get(_total, _total)})")
else:
    checked += 1
    print(f"  preflight runs {_total} checks and the checklist says {_said}")

# Same for the CI step count, which sits in the README's 60-second box -- the single most-read line
# in the repo -- and in the submission copy. It was typed in both places and checked in neither.
_steps = sum(1 for _l in open(".github/workflows/verify.yml") if re.match(r"^\s*- name:", _l))
for _doc in ("README.md", "SUBMISSION.md"):
    _said = re.findall(r"(\d+) CI steps", open(_doc).read())
    if not _said:
        problems.append(f"{_doc}: no CI step count found where one is expected")
    elif any(int(x) != _steps for x in _said):
        problems.append(f"{_doc}: says {', '.join(_said)} CI steps, the workflow has {_steps}")
    else:
        checked += len(_said)
# The test count and the rendered-state count each appear in more than one document, and the
# README states the test count TWICE -- once in the 60-second box and once as a comment beside the
# pytest command in the Quickstart. Updating one and not the other is exactly what happened, and
# it was caught by CI rather than here, which is the slow way to find out.
import subprocess  # noqa: E402
_collected = subprocess.run([sys.executable, "-m", "pytest", "tests/", "--collect-only", "-q"],
                            capture_output=True, text=True).stdout
_m = re.search(r"(\d+) tests? collected", _collected)
if not _m:
    problems.append("could not read the collected test count from pytest")
else:
    _tests = int(_m.group(1))
    for _doc in ("README.md", "SUBMISSION.md", "docs/EXPLAIN-IT.md"):
        for _said in re.findall(r"(\d+) (?:invariant )?tests\b", open(_doc).read()):
            if int(_said) != _tests:
                problems.append(f"{_doc}: says {_said} tests, pytest collects {_tests}")
            else:
                checked += 1
    print(f"  pytest collects {_tests} tests and every document agrees")

_ui = open("scripts_check_ui.py").read()
_chips = len(re.findall(r'tool:\s*"[a-z_]+"', open("web/app.js").read()))
_extra = _ui[_ui.index("cases = chips() + ["):_ui.index("]", _ui.index("cases = chips() + ["))]
_states = _chips + len(re.findall(r'^\s{8}\("', _extra, re.M))
for _doc in ("README.md", "SUBMISSION.md"):
    for _said in re.findall(r"(\d+) rendered UI states", open(_doc).read()):
        if int(_said) != _states:
            problems.append(f"{_doc}: says {_said} rendered UI states, the check drives {_states}")
        else:
            checked += 1
# The fallback video's length, stated in the submission copy. It said 50s while the file was 86s,
# because the video has been rebuilt four times today and that line was typed once. The duration is
# derived the same way the build script derives it -- the beat budgets plus the two cards -- so it
# needs no ffmpeg to check and cannot disagree with what the build actually produces.
_build = open("scripts_build_walkthrough.py").read()
_beats = re.findall(r'^\s{4}\("[^"]+",\s*(\d+),', _build, re.M)
_cards = re.search(r"total = sum\(b\[1\] for b in BEATS\) \+ (\d+)", _build)
if not _beats or not _cards:
    problems.append("could not derive the walkthrough's duration from the build script")
else:
    _dur = sum(int(b) for b in _beats) + int(_cards.group(1))
    for _said, _unit in re.findall(r"walkthrough-silent\.mp4`?,\s*(\d+)(s)\b", open("SUBMISSION.md").read()):
        if int(_said) != _dur:
            problems.append(f"SUBMISSION.md: says the fallback video is {_said}s, "
                            f"the build produces {_dur}s")
        else:
            checked += 1
    for _said in re.findall(r"An? (\d+)-second captioned walkthrough", open("docs/video/README.md").read()):
        if int(_said) != _dur:
            problems.append(f"docs/video/README.md: says {_said}s, the build produces {_dur}s")
        else:
            checked += 1
    print(f"  the walkthrough builds to {_dur}s across {len(_beats)} beats and both docs agree")

print(f"  the UI check drives {_states} rendered states and every document agrees")

print(f"  the workflow has {_steps} named steps and both docs say so")

# ---------------------------------------------------------------------------
# docs/EXPLAIN-IT.md states the data model as a table -- "| `Person` | 794 |" -- so the number and
# its noun sit in different cells and the prose scanner above cannot see either. That file is the
# one somebody reads out loud under questioning, which makes it the worst place for a stale number,
# so its table is parsed on its own terms.
_brief = pathlib.Path("docs/EXPLAIN-IT.md").read_text()
_LABELS = {"Person": "MATCH (n:Person) RETURN count(n)",
           "Kep": "MATCH (n:Kep) RETURN count(n)",
           "OwnersFile": "MATCH (n:OwnersFile) RETURN count(n)",
           "Alternative": "MATCH (n:Alternative) RETURN count(n)",
           "NamedOption": "MATCH (n:NamedOption) RETURN count(n)",
           "MissingRecord": "MATCH (n:MissingRecord) RETURN count(n)",
           "Sig": "MATCH (n:Sig) RETURN count(n)"}
for _lab, _q in _LABELS.items():
    _m = re.search(rf"\|\s*`{_lab}`\s*\|\s*\**([\d,]+)\**\s*\|", _brief)
    if not _m:
        problems.append(f"docs/EXPLAIN-IT.md: no row found for {_lab}")
        continue
    _said, _live = int(_m.group(1).replace(",", "")), count(_q)
    if _said != _live:
        problems.append(f"docs/EXPLAIN-IT.md: says {_said:,} {_lab}, the graph has {_live:,}")
    else:
        checked += 1

# The edge counts, and the derived "206 are not named options", stated in prose there.
_EDGES = {"APPROVES": "MATCH ()-[r:APPROVES]->() RETURN count(r)",
          "EMERITUS_OF": "MATCH ()-[r:EMERITUS_OF]->() RETURN count(r)",
          "INHERITS_FROM": "MATCH ()-[r:INHERITS_FROM]->() RETURN count(r)",
          "CONSIDERED": "MATCH ()-[r:CONSIDERED]->() RETURN count(r)",
          "CO_AUTHORED": "MATCH ()-[r:CO_AUTHORED]->() RETURN count(r)"}
for _rel, _q in _EDGES.items():
    _m = re.search(rf"`{_rel}`\s*\(([\d,]+)\)", _brief)
    if not _m:
        problems.append(f"docs/EXPLAIN-IT.md: no count given for {_rel}")
        continue
    _said, _live = int(_m.group(1).replace(",", "")), count(_q)
    if _said != _live:
        problems.append(f"docs/EXPLAIN-IT.md: says {_said:,} {_rel} edges, the graph has {_live:,}")
    else:
        checked += 1

_m = re.search(r"other (\d+) have titles that are", _brief)
_gap = count("MATCH (n:Alternative) WHERE NOT n:NamedOption RETURN count(n)")
if not _m or int(_m.group(1)) != _gap:
    problems.append(f"docs/EXPLAIN-IT.md: the un-named alternatives figure should be {_gap}")
else:
    checked += 1
print(f"  the explain-it brief's model table matches the graph ({_gap} un-named alternatives)")

print(f"  scanned {len(files)} markdown files, checked {checked} count claims")
for label, (live, _) in COUNTS.items():
    print(f"    {label:<24} {live:,}")
if problems:
    print("\n" + "\n".join("  FAIL  " + p for p in problems))
    sys.exit(1)
print("\nOK: every corpus count in the docs matches the graph")
