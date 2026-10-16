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
def _flat(text: str) -> str:
    """One long line, so a pattern cannot miss because the sentence wrapped.

    Three checks written today matched nothing for exactly this reason: markdown wraps prose, and
    inside a blockquote the break becomes "\n> ", so "made it 83, because" is split and a
    literal-space pattern finds nothing. A check that silently matches nothing is the failure
    mode this file exists to prevent, so the text is flattened before these scans rather than
    each pattern being taught about newlines one at a time.
    """
    return re.sub(r"\s*\n>?\s*", " ", text)


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
    # "synthetic", "stale", "older" and "earlier" were too broad: this project uses all four in
    # LIVE claims -- "Nothing synthetic" sits directly after the corpus counts in both of
    # SUBMISSION.md's descriptions, and "43 decisions are stale-and-still-cited" is a current
    # finding. Each of those lines was being skipped wholesale, so the figures on them were
    # checked nowhere in that file. An exclusion keyed on a word rather than on a retraction
    # swallows every sentence that happens to use the word.
    r"previously|used to|was wrong|withdrawn|corrected|drifted|said \d|"
    r"first number|I had claimed|claimed \d|3,300|no longer says", re.I)

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
         pathlib.Path("docs/BLOG-POST.md"), pathlib.Path("docs/EXPLAIN-IT.md"),
         # Linked from the README, so it is judge-facing whether or not it was written to be.
         # It carries no corpus counts today -- its numbers are about checks and measurements --
         # but a document outside this list is a document where the next one can go stale, and
         # the corpus record two files over proved that is not hypothetical.
         pathlib.Path("docs/GROUND-TRUTH.md")]
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
# Every tracked document, not just the submission checklist. This check was written against
# SUBMISSION.md alone, so docs/EXPLAIN-IT.md -- the file whose entire job is being right when a
# judge asks, under Rule 12 -- could claim any number of checks and nothing noticed. Scanning
# whatever is tracked means a document added later is covered without remembering to list it.
# _WORDS only spans 14-22, which is enough to RENDER the right answer but not to RECOGNISE a
# wrong one: a doc claiming "thirty-one checks" parsed as not-a-number and was skipped in silence.
# So the parse side gets every spelled number up to sixty, built rather than typed.
_UNITS = ["zero", "one", "two", "three", "four", "five", "six", "seven", "eight", "nine", "ten",
          "eleven", "twelve", "thirteen", "fourteen", "fifteen", "sixteen", "seventeen",
          "eighteen", "nineteen"]
_TENS = {20: "twenty", 30: "thirty", 40: "forty", 50: "fifty", 60: "sixty"}
_SPELLED = {w: i for i, w in enumerate(_UNITS)}
for _t, _tw in _TENS.items():
    _SPELLED[_tw] = _t
    for _u in range(1, 10):
        _SPELLED[f"{_tw}-{_UNITS[_u]}"] = _t + _u
import subprocess as _subp
_docs = [d for d in _subp.run(["git", "ls-files", "*.md"], capture_output=True,
                              text=True).stdout.split() if pathlib.Path(d).exists()]
_claims = 0
for _doc in _docs:
    for _tok in re.findall(r"([\w-]+) checks\b", _flat(open(_doc).read())):
        _n = int(_tok) if _tok.isdigit() else _SPELLED.get(_tok)
        if _n is None:          # "the checks that need no database" -- not a count at all
            continue
        _claims += 1
        if _n != _total:
            problems.append(f"{_doc}: says preflight runs '{_tok}' checks, it runs {_total} "
                            f"({_WORDS.get(_total, _total)})")
if not _claims:
    problems.append("no document states how many checks preflight runs; one is expected")
else:
    checked += _claims
    print(f"  preflight runs {_total} checks, stated {_claims}x across {len(_docs)} documents")

# Same for the CI step count, which sits in the README's 60-second box -- the single most-read line
# in the repo -- and in the submission copy. It was typed in both places and checked in neither.
_steps = sum(1 for _l in open(".github/workflows/verify.yml") if re.match(r"^\s*- name:", _l))
# Also widened to every tracked document: docs/EXPLAIN-IT.md and docs/GROUND-TRUTH.md both state
# this number and neither was being read, so the same figure was guarded in two files and loose
# in two others.
_seen_steps = 0
for _doc in _docs:
    _said = re.findall(r"(\d+) CI steps", _flat(open(_doc).read()))
    _seen_steps += len(_said)
    if any(int(x) != _steps for x in _said):
        problems.append(f"{_doc}: says {', '.join(_said)} CI steps, the workflow has {_steps}")
if not _seen_steps:
    problems.append("no document states the CI step count; one is expected")

# And the EXECUTION count, which is not the same number. supported-pythons is a matrix job over
# two Pythons, so 31 named steps produce 33 runs. The docs said 31 and meant definitions, which
# understates -- the safe direction, and still a figure nobody could check.
_runs = 0
_job, _per = None, {}
for _ln in open(".github/workflows/verify.yml"):
    _m = re.match(r"^  ([a-z_-]+):$", _ln)
    if _m:
        _job = _m.group(1)
        _per.setdefault(_job, 0)
    if re.match(r"^\s*- name:", _ln) and _job:
        _per[_job] += 1
_matrix = len(re.findall(r'python: \[([^\]]*)\]', open(".github/workflows/verify.yml").read()))
_pys = re.search(r'python: \[([^\]]*)\]', open(".github/workflows/verify.yml").read())
_n_py = len([x for x in _pys.group(1).split(",")]) if _pys else 1
_runs = sum(n * (_n_py if j == "supported-pythons" else 1) for j, n in _per.items())
for _doc in _docs:
    for _said in re.findall(r"\((\d+) runs", _flat(open(_doc).read())) + \
                 re.findall(r"(\d+) runs because", _flat(open(_doc).read())):
        if int(_said) != _runs:
            problems.append(f"{_doc}: says {_said} CI runs; the workflow produces {_runs}")
        else:
            checked += 1
else:
    checked += _seen_steps
    print(f"  the workflow has {_steps} steps, stated {_seen_steps}x across the documents")

# What the deploy actually ships. FINISH.md tells you so you know what to expect while watching
# it upload, and it said 57 files / 1.4 MB for what is now 90 files / 3.1 MB -- the repo grew and
# the sentence did not. Computed the way deploy_hf.sh builds its upload, `git archive HEAD` plus
# the Space README swapped in, so this cannot drift from what that script does without the script
# changing too.
import os as _os
import shutil as _sh
import tempfile as _tf
_stage = _tf.mkdtemp(prefix="deploycount-")
try:
    _tar = _subp.run(["git", "archive", "HEAD"], capture_output=True)
    _subp.run(["tar", "-x", "-C", _stage], input=_tar.stdout, capture_output=True)
    _sh.copy("deploy/README-hf-space.md", _os.path.join(_stage, "README.md"))
    _n_files, _bytes = 0, 0
    for _root, _dirs, _names in _os.walk(_stage):
        for _nm in _names:
            _n_files += 1
            _bytes += _os.path.getsize(_os.path.join(_root, _nm))
    _mb = _bytes / 1_000_000
    _said = re.search(r"uploads (\d+) files / ([\d.]+) MB", open("FINISH.md").read())
    if not _said:
        problems.append("FINISH.md no longer says what the deploy uploads")
    else:
        _sf, _sm = int(_said.group(1)), float(_said.group(2))
        if _sf != _n_files:
            problems.append(f"FINISH.md says the deploy uploads {_sf} files; it uploads {_n_files}")
        elif abs(_sm - _mb) > 0.15:
            problems.append(f"FINISH.md says {_sm} MB; the staged upload is {_mb:.1f} MB")
        else:
            checked += 1
            print(f"  the deploy uploads {_n_files} files / {_mb:.1f} MB and FINISH.md says so")
finally:
    _sh.rmtree(_stage, ignore_errors=True)

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
        # A rival's test count is not a claim about this one. Flattening the prose made
        # "185\ntests to 128" -- lineage's figure beside ours in the competitor analysis --
        # match as though it described this repository. It also exposed that the "124" beside it
        # was stale, which the line break had been hiding from every check in the file.
        _body = re.sub(r"[^.]*\b(?:tests to|to this graph's|relationships to)\b[^.]*\.", " ",
                       _flat(open(_doc).read()))
        # The comparison is excluded above so a rival's count is not read as ours -- but OUR
        # number is the second half of "185 tests to 128", and excluding the sentence removed the
        # only check on it. Verified by setting it to 999: nothing failed. So the trailing figure
        # is checked explicitly, which is the half of that sentence this repository is
        # accountable for.
        for _said in (re.findall(r"(\d+) (?:invariant )?tests\b", _body)
                      + re.findall(r"\btests to (\d+)", _flat(open(_doc).read()))):
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
    for _said in re.findall(r"(\d+) rendered UI states", _flat(open(_doc).read())):
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
    # Rule 8: the main work must begin after the event starts, and the README offers a command so a
# judge can check it rather than take my word. That command carried epoch 1760466660, which is
# 2025-10-15 00:01 IST -- a year early. It printed 0, and 0 meant nothing: every commit in this
# repository trivially postdates 2025. A verification command that cannot fail is worse than no
# command, because it invites someone to rely on it.
import datetime as _dt
import subprocess as _sp

_IST = _dt.timezone(_dt.timedelta(hours=5, minutes=30))
_START = int(_dt.datetime(2026, 10, 15, 0, 1, tzinfo=_IST).timestamp())
_m = re.search(r"awk '\$1 < (\d+)'", open("README.md").read())
if not _m:
    problems.append("README no longer carries the Rule 8 verification command")
elif int(_m.group(1)) != _START:
    problems.append(
        f"README's Rule 8 command uses epoch {_m.group(1)} "
        f"({_dt.datetime.fromtimestamp(int(_m.group(1)), _IST):%Y-%m-%d %H:%M} IST); the window "
        f"opens at {_START} ({_dt.datetime.fromtimestamp(_START, _IST):%Y-%m-%d %H:%M} IST)")
else:
    _early = _sp.run(["git", "log", "--format=%at"], capture_output=True, text=True).stdout.split()
    _n_early = sum(1 for _t in _early if int(_t) < _START)
    if _n_early:
        problems.append(f"{_n_early} commits predate the hackathon window — Rule 8")
    else:
        checked += 1
        print(f"  all {len(_early)} commits fall inside the hackathon window (Rule 8)")

# CI's quickstart job is titled "exactly as the README writes it", and it was not: CI created a
# venv first while the README told you to, and neither tested what run.sh does from a bare clone.
# Both are two lines now, and the commands must match -- a step that claims to run the documented
# path and runs something easier proves only that the easier thing works.
_qs = re.search(r"```bash\n(git clone[^\n]*\n\./run\.sh[^\n]*)\n```", open("README.md").read())
_ci_q = open(".github/workflows/verify.yml").read()
if not _qs:
    problems.append("the README's quickstart is no longer 'git clone ...' then './run.sh'")
elif re.search(r"^\s*python3[\d.]* -m venv \.venv", _ci_q, re.M):
    problems.append("CI's quickstart still builds a venv by hand; the README says ./run.sh does it")
else:
    checked += 1
    print("  CI runs the quickstart the README documents (clone, then ./run.sh)")

# The "check me" commands are the README's credibility bullet, and they are the next thing a
# judge pastes after ./run.sh. They said bare `python` for most of this project's life and
# returned ModuleNotFoundError on a clean clone, because run.sh builds .venv and nothing activates
# it. CI runs them verbatim now; this keeps the two spellings identical.
_rm = open("README.md").read()
_ciq = open(".github/workflows/verify.yml").read()
for _cmd in ("PYTHONPATH=src ./.venv/bin/python -m pytest tests/ -q",
             "PYTHONPATH=src ./.venv/bin/python verify_claims.py"):
    if _cmd not in _rm:
        problems.append(f"the README no longer documents: {_cmd}")
    elif _cmd not in _ciq:
        problems.append(f"CI does not run the documented command: {_cmd}")
    else:
        checked += 1
if re.search(r"PYTHONPATH=src python[3]? ", _rm):
    problems.append("the README still documents a bare `python`, which has no dependencies "
                    "after ./run.sh builds the venv")
# bench_vs_networkx is the one documented script that needs something requirements.txt does not
# install. The script handles it well -- it names the install command and explains why -- but a
# reader should know before they paste, not after.
if "bench_vs_networkx.py" in _rm and not re.search(
        r"bench_vs_networkx\.py`[^\n]{0,120}networkx scipy", _rm):
    problems.append("the README runs bench_vs_networkx.py without saying it needs "
                    "`pip install networkx scipy` first")
else:
    checked += 1
print("  the README's check-me commands are the ones CI runs")

# The 60-second box used to say "every benchmark re-run by N CI steps". Two of the three run in
# CI; spikes/tenancy_bench.py builds a thousand graphs and does not. A false claim in the most-read
# line of the repository, and the kind that sounds like diligence.
_ciq2 = open(".github/workflows/verify.yml").read()
_benches = {p.name for p in pathlib.Path(".").glob("bench_*.py")} | {
    p.name for p in pathlib.Path("spikes").glob("*bench*.py")}
_in_ci = {b for b in _benches if b in _ciq2}
_m_b = re.search(r"\*\*(\w+) of\s*\n?>?\s*the (\w+) benchmarks\*\*", open("README.md").read())
_WORD = {1: "one", 2: "two", 3: "three", 4: "four", 5: "five", 6: "six", 7: "seven",
         8: "eight", 9: "nine", 10: "ten"}   # five was missing, so the check failed on a
                                             # pair of numbers that actually agreed
if not _m_b:
    problems.append("the 60-second box no longer states how many benchmarks CI re-runs")
elif (_m_b.group(1), _m_b.group(2)) != (_WORD.get(len(_in_ci)), _WORD.get(len(_benches))):
    problems.append(f"the box says '{_m_b.group(1)} of the {_m_b.group(2)} benchmarks'; "
                    f"{len(_in_ci)} of {len(_benches)} run in CI")
else:
    checked += 1
    print(f"  {len(_in_ci)} of {len(_benches)} benchmarks run in CI, and the box says so")

# The tool count, spelled in words wherever the prose names it. The README said the model picks
# "which of eleven tools" while the catalogue has thirteen and the principles table two hundred
# lines above said thirteen. Found by sweeping sentences that assert something absolute, not by
# any check -- the number-scanner looks for digits and this one was a word.
_tools = len(re.findall(r'^\s{4}"(\w+)":', open("src/tombstone/tools.py").read(), re.M))
_WORDS_T = {11: "eleven", 12: "twelve", 13: "thirteen", 14: "fourteen", 15: "fifteen"}
for _doc in ("README.md", "SUBMISSION.md", "docs/EXPLAIN-IT.md"):
    _txt = _flat(open(_doc).read())
    for _w in re.findall(r"\b(eleven|twelve|thirteen|fourteen|fifteen)\s+(?:tools|queries|chips)\b",
                         _txt):
        if _w != _WORDS_T.get(_tools):
            problems.append(f"{_doc}: says '{_w} tools', the catalogue has {_tools} "
                            f"({_WORDS_T.get(_tools)})")
        else:
            checked += 1
print(f"  the catalogue has {_tools} tools and every document that spells it agrees")

print(f"  the walkthrough builds to {_dur}s across {len(_beats)} beats and both docs agree")

print(f"  the UI check drives {_states} rendered states and every document agrees")


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

_gap = count("MATCH (n:Alternative) WHERE NOT n:NamedOption RETURN count(n)")
# Case-insensitive: the sentence was reworded to START with "The other 206 are", and a
# case-sensitive pattern then reported the figure as missing from a page that states it.
_m = (re.search(r"the\s+other (\d+) are", _brief, re.I)
      or re.search(r"other (\d+) have titles", _brief, re.I))
if not _m or int(_m.group(1)) != _gap:
    problems.append(f"docs/EXPLAIN-IT.md: the un-named alternatives figure should be {_gap}")
else:
    checked += 1

# How many of those are real text rather than artefacts. The page used to call all 206 artefacts,
# which was comfortable and wrong, so the number that corrects it is itself derived.
#
# Both of these count TITLE length, which measures the extractor and not the corpus -- and the
# extractor has since been fixed, so the honest substance floor is the third query: the build
# refuses to make a node under 100 characters of body, and the embedding is over the body alone.
_substantive = count("MATCH (n:Alternative) WHERE NOT n:NamedOption AND size(trim(n.title)) >= 60 "
                     "RETURN count(n)")
_markers = count("MATCH (n:Alternative) WHERE NOT n:NamedOption "
                 "AND size(trim(n.title)) <= 6 RETURN count(n)")
_thin = count("MATCH (n:Alternative) WHERE NOT n:NamedOption AND size(n.body) < 100 "
              "RETURN count(n)")
_vectored = count("MATCH (n:Alternative) WHERE NOT n:NamedOption AND n.emb IS NOT NULL "
                  "RETURN count(n)")
if _thin:
    problems.append(f"{_thin} excluded alternatives hold under 100 characters of body, which the "
                    f"build is supposed to refuse")
else:
    checked += 1
# The docs now say every one of them is embedded. If that stops being true the pages become
# wrong in the direction that flatters the product, which is the direction worth gating.
if _vectored != _gap:
    problems.append(f"the docs say all {_gap} excluded alternatives carry a vector; "
                    f"{_vectored} do")
else:
    checked += 1
# Every tracked document, not the two that happened to state it when this was written. A
# "what I would do next" answer in SUBMISSION.md now calls these "the 163 rejections the search
# cannot see", which is the same figure in a form neither pattern below would have matched --
# so if the number moved, EXPLAIN-IT would fail and the submission copy would quietly keep the
# old one. Its phrasing is recognised too.
for _doc in _docs:
    _t = _flat(open(_doc).read())
    for _said in (re.findall(r"\*\*(\d+) are 60", _t) + re.findall(r"\*\*(\d+) are 60\+", _t)
                  # \s and an optional ">" because the sentence wraps inside a blockquote,
                  # so the phrase is split by "\n> " in the file and a literal-space pattern
                  # matched nothing -- the same wrapped-prose miss as the demo-timing check.
                  ):
        if int(_said) != _substantive:
            problems.append(f"{_doc}: says {_said} substantive excluded alternatives, "
                            f"the graph has {_substantive}")
        else:
            checked += 1
    # "0 list markers now" and the older "**19 are list markers**" are the same claim in two
    # shapes, and the fix that made it zero is what moved it. Both forms are recognised so the
    # figure cannot drift back in either phrasing.
    for _said in (re.findall(r"\*\*(\d+) are list\s+markers\*\*", _t)
                  + re.findall(r"\*\*(\d+) list\s+markers\s+now", _t)):
        if int(_said) != _markers:
            problems.append(f"{_doc}: says {_said} list markers, the graph has {_markers}")
        else:
            checked += 1
    # The label fix is only real if the labels are still readable: a cap on length, and nothing
    # cut mid-word. Stated in the README as a pair, so both are derived here.
    # "the N rejections the search cannot see" names the whole excluded set, not the subset with
    # a usable label. It was checked against the substantive count, which was the same number
    # when both were written and is not any more -- so the phrase moved to the figure it means.
    for _said in re.findall(r"(\d+) rejections the search cannot see", _t):
        if int(_said) != _gap:
            problems.append(f"{_doc}: says {_said} rejections the search cannot see, "
                            f"the graph excludes {_gap}")
        else:
            checked += 1
    for _said in re.findall(r"(\d+) of the 206 carry a 60-plus character label", _t):
        if int(_said) != _substantive:
            problems.append(f"{_doc}: says {_said} carry a 60-plus character label, "
                            f"the graph has {_substantive}")
        else:
            checked += 1
# The container's memory floor cannot be derived without Docker and a built image, so the
# MEASUREMENT stays dated -- but the AGREEMENT between the places that state it is derivable, and
# that is where it went wrong. One number was stated three ways: 387 MB in the README, "about
# 400 MB" in the Space README, and 450.1MiB from scripts_verify_deploy.sh, the only thing that
# measures it. Two of the three were undated constants nobody re-derived.
_base = re.search(r"^BASELINE_MB = (\d+)", open("bench_memory_growth.py").read(), re.M)
if not _base:
    problems.append("bench_memory_growth.py no longer states a BASELINE_MB to check against")
else:
    _want = int(_base.group(1))
    _ceil = re.search(r"^SERIAL_CEILING_MB=(\d+)", open("scripts_verify_deploy.sh").read(), re.M)
    if _ceil and _want >= int(_ceil.group(1)):
        problems.append(f"BASELINE_MB is {_want}, at or above the {_ceil.group(1)}MB ceiling the "
                        f"deploy check asserts, so the projection starts out of room")
    else:
        checked += 1
    for _doc, _pat in (("README.md", r"(\d+) MiB serial peak"),
                       ("deploy/README-hf-space.md", r"peaks at about (\d+) MiB in serial use")):
        _t = _flat(open(_doc).read())
        _found = re.findall(_pat, _t)
        if not _found:
            problems.append(f"{_doc}: no longer states the serial peak, so nothing pins it to "
                            f"bench_memory_growth.py's BASELINE_MB of {_want}")
        elif any(int(x) != _want for x in _found):
            problems.append(f"{_doc}: says a {_found[0]} MiB serial peak; "
                            f"BASELINE_MB is {_want}")
        else:
            checked += 1
    print(f"  the {_want} MiB serial peak is stated the same way in both documents and in the "
          f"benchmark that projects from it")

_longest = count("MATCH (n:Alternative) WHERE NOT n:NamedOption RETURN max(size(n.title))")
if _longest > 161:
    problems.append(f"an excluded alternative carries a {_longest}-character label; "
                    f"derive_label caps them at 160 plus an ellipsis")
else:
    checked += 1
print(f"  {_gap} alternatives are outside the haystack; all of them embedded, "
      f"{_substantive} with a 60-plus character label and {_markers} list markers, "
      f"longest {_longest} characters, and the docs say so")

# The "hardest problem" answer in SUBMISSION.md restates the alias correction -- "88 of 111
# departed owners" and "made it 83". The subset rule above deliberately skips 111, because
# conflating a subset denominator with the 794 Person total is a false alarm it was written to
# avoid, so neither figure was checked anywhere in that file. 88 is the SUPERSEDED number and
# must stay wrong; 83 and 111 are live and must not drift.
_emeritus_total = count("MATCH (p:Person)-[:EMERITUS_OF]->() RETURN count(DISTINCT p)")
_emeritus_only = count("MATCH (p:Person)-[:EMERITUS_OF]->() WHERE NOT (p)-[:APPROVES]->() "
                       "RETURN count(DISTINCT p)")
for _doc in _docs:
    _t = _flat(open(_doc).read())
    for _said in re.findall(r"made it (\d+), because", _t):
        if int(_said) != _emeritus_only:
            problems.append(f"{_doc}: says the alias fix made it {_said}; the graph gives "
                            f"{_emeritus_only}")
        else:
            checked += 1
    for _said in re.findall(r"\d+ of (\d+) departed owners", _t):
        if int(_said) != _emeritus_total:
            problems.append(f"{_doc}: says {_said} departed owners; the graph has "
                            f"{_emeritus_total}")
        else:
            checked += 1

# "N of M nouns" -- the SUBSET rule skips a number preceded by "of", which is right for the N and
# exactly wrong for the M. In "206 of 959 alternatives", 959 is a TOTAL and it was wrong by one;
# the scanner had been stepping over it since the rule was added. Totals stated as denominators
# are checked here on their own terms.
for _path in files:
    for _lineno, _line in enumerate(_path.read_text().split("\n"), 1):
        if HISTORY.search(_line):
            continue
        for _label, (_live, _phrasings) in COUNTS.items():
            for _ph in _phrasings:
                # re.I, because the phrasings are written capitalised ("Alternatives") and the
                # prose is not. Without it this rule matched nothing at all and passed -- which
                # the negative test caught, and nothing else would have.
                for _m in re.finditer(rf"\b[\d,]+ of ([\d,]+)\s+(?:\*\*)?{_ph}", _line, re.I):
                    _den = int(_m.group(1).replace(",", ""))
                    if not (0.9 * _live <= _den <= 1.1 * _live):
                        continue
                    checked += 1
                    if _den != _live:
                        problems.append(
                            f"{_path}:{_lineno}: says 'of {_den:,} {_label}', the graph has "
                            f"{_live:,}\n      {_line.strip()[:100]}")

print(f"  scanned {len(files)} markdown files, checked {checked} count claims")

# An aggregate floor. Every individual figure check here is driven by a regex against prose, and
# a regex that stops matching reports nothing rather than failing -- so a rewording could retire
# a dozen of these at once and this script would still print OK. Most of them have no "if not
# found" guard of their own; the counter is what makes a systemic miss visible, and a counter
# that is printed and never asserted is decoration.
_FLOOR = 45
if checked < _FLOOR:
    problems.append(f"only {checked} figures matched across {len(files)} documents, below the "
                    f"floor of {_FLOOR} -- the documents were reworded past these checks rather "
                    f"than the figures being right")
for label, (live, _) in COUNTS.items():
    print(f"    {label:<24} {live:,}")
if problems:
    print("\n" + "\n".join("  FAIL  " + p for p in problems))
    sys.exit(1)
print("\nOK: every corpus count in the docs matches the graph")
