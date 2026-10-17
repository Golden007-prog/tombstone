"""Assert that the demo script narrates what the app actually shows.

The timing checker proved the script could be SPOKEN in three minutes. Nothing proved it was
TRUE. Two beats had gone stale against the live graph without anything failing: one named a person
and a KEP that the four-hop answer does not mention any more, and one said the top of the
centrality ranking was someone who is actually third. Both would have been discovered while
editing the recording, at which point the fix is another take.

So the factual claims in the narration are checked against live tool output, the same way every
number in the README is. This is the cheapest possible insurance against the most expensive
failure in the submission: a video that has to be re-shot.
"""
from __future__ import annotations

import re
import sys

sys.path.insert(0, "src")
from tombstone.agent import Agent, render  # noqa: E402

SCRIPT = "docs/DEMO-SCRIPT.md"
OWNERS = "staging/src/k8s.io/apiserver/pkg/endpoints/metrics/OWNERS"

script = open(SCRIPT).read()
README = open("README.md").read()
# Flattened too, because the script is a 100-column markdown blockquote and a claim that wraps is
# a claim no \b-anchored regex can see: "left far\n> fewer" defeated a check that was looking for
# "left far fewer", and this repository has lost three regexes to wrapped prose already. Match
# phrasing against `flat`, never against `script`; numbers and whole words are fine in either.
_flat = __import__("re").sub(r"\s*\n>?\s*", " ", script)
agent = Agent(graph_name="tomb:k8s")
fails = []


def check(label: str, ok: bool, detail: str = "") -> None:
    print(f"  {'PASS' if ok else 'FAIL'}  {label}{(' — ' + detail) if detail else ''}")
    if not ok:
        fails.append(label)


# Beat 3 — the four-hop answer. The narration names a person and an alternative title; both must
# still be what the tool returns, or the voiceover describes a screen nobody is looking at.
four_hop = render(agent.dispatch("who_owns", {"path": OWNERS, "depth": 4}))
for token in ("logicalhan", "Doing nothing is a viable alternative"):
    check(f"beat 3 narrates {token!r}",
          token in script and token.lower() in four_hop.lower())

# Beat 4 — "has this been tried" must still surface KEP-6061.
vec = list(agent.embedder().embed(["has anyone tried moving this into the kubelet?"]))[0].tolist()
tried = agent.tools.has_this_been_tried(vec, max_dist=0.45)
check("beat 4 narrates KEP-6061", "6061" in script and "6061" in render(tried))

# Beat 5 — what the beat now claims, after the ranking it used to narrate turned out to depend on
# sampling. Exact Brandes over the tool's OWN population (21 people: emeritus >= 3, zero live
# APPROVES) puts lavalamp first at 4238.6 with 31 areas and logicalhan second at 2315.5 with 5 --
# so under exactness the most-departed person IS the most connective and the old contrast
# evaporates. An earlier disclosure in README claimed the finding survived; it had ranked over
# everyone emeritus anywhere, including dchen1107, who holds 42 live APPROVES edges and whom this
# query never returns. The beat now claims the capability and the limitation, and these check both.
bridges = agent.dispatch("stepped_back_bridges", {"min_areas": 3})
rows = bridges.rows
check("beat 5: the ranking is real and non-empty", bool(rows), f"{len(rows)} rows")
check("beat 5 says it is sampled, and the query actually samples",
      bool(re.search(r"\bthis one is sampled\b", _flat))
      and "samplingSeed" in bridges.cypher and "samplingSize" not in bridges.cypher,
      "samplingSeed pinned, samplingSize left at FalkorDB's default of 32")
check("beat 5 says exactness changes the order, and the page carries the measurement",
      bool(re.search(r"exactly and the order changes", _flat))
      and "4238.6" in README and "2315.5" in README,
      "README's Honest limits states the exact figures a judge can re-derive")

# Beat 6 — the drafting action: three candidates, two drafted, one refused.
drafted = agent.dispatch("draft_owners_patch", {})
patches = sum(1 for r in drafted.rows if r[3] == "patch")
# Matched on the claim, not on one phrasing of it. Tightening the beat for its word budget
# changed "Three people are recorded" to "Three are recorded" and this went red -- the narration
# still said three and the graph still found three, so the only thing wrong was the literal string
# this was looking for.
_says_three = re.search(r"\bThree\b[^.\n]{0,40}\brecorded\b", script)
check("beat 6: three candidates", bool(_says_three) and len(drafted.rows) == 3,
      f"{len(drafted.rows)} candidates")
check("beat 6: two drafted, one refused", patches == 2 and len(drafted.rows) - patches == 1,
      f"{patches} drafted, {len(drafted.rows) - patches} refused")

# Beat 6 also names the vendored case: emeritus in twenty files, approver in one.
em = agent.g.ro_query(
    "MATCH (p:Person {key:'stewart-yu'})-[:EMERITUS_OF]->(o) RETURN count(o)").result_set[0][0]
check("beat 6 says 'emeritus in twenty files'", "twenty files" in script and em == 20,
      f"actually {em}")

# Beat 7 — the memory beat. This is the one that broke silently: on a FRESH instance a judge has
# an empty memory, and the recall chip used to ask about an area no earlier beat touched, so the
# beat about remembering showed "nothing like this has been asked". Worse, chip clicks were not
# recorded at all -- only typed questions were -- so even a matching question would have missed.
# This replays the demo on a cleared memory and requires the recall beat to find something.
agent.g.query("MATCH (a:Answer) DETACH DELETE a")
OWNERS_PATH = OWNERS
for tool, args, question in (
    ("who_owns", {"path": OWNERS_PATH, "depth": 4}, "who really owns the apiserver metrics endpoint"),
    ("draft_owners_patch", {}, "draft the fix for the ownership records that contradict themselves"),
):
    agent._remember(question, tool, agent.dispatch(tool, args))

recalled = agent.dispatch("recall", {"question": "who actually owns the apiserver metrics endpoint"})
check("beat 7: recall finds the earlier question after the demo's own beats",
      recalled.shape == "ANSWERED_WITH_PATH" and bool(recalled.rows),
      f"{recalled.shape}, {len(recalled.rows)} "
      f"{'row' if len(recalled.rows) == 1 else 'rows'}")

print(f"\n{'FAILED' if fails else 'OK'}: the demo script "
      f"{'does not match' if fails else 'matches'} what the app returns")

# Every chip the script tells a presenter to click must exist, by its exact label. The directions
# used to be descriptive -- "the whose-departure-cost-most chip" -- which survives a rename and
# leaves somebody hunting through fourteen buttons while recording. A label is quoted now, so a
# rename breaks this instead of the recording.
import re as _re

_script = open("docs/DEMO-SCRIPT.md").read()
_js = open("web/app.js").read()
if "const CHIPS = [" not in _js:
    raise SystemExit(
        "web/app.js no longer contains `const CHIPS = [`. This parser is "
        "reading the wrong thing, and every check below it would be "
        "measuring a chip set that is not the one the UI ships.")
_i = _js.index("const CHIPS = [")
_d = 0
for _n, _c in enumerate(_js[_i:], _i):
    if _c == "[":
        _d += 1
    elif _c == "]":
        _d -= 1
        if _d == 0:
            _block = _js[_i:_n + 1]
            break
def _unesc(raw: str) -> str:
    """Only unescape when there IS an escape.

    `.encode().decode("unicode_escape")` turns a literal "…" into "â¦": encode gives three UTF-8
    bytes and unicode_escape reads each as latin-1. The chip labels mix both forms, so this check
    reported a chip as missing when the only thing wrong was how it had read the file.
    """
    if "\\" not in raw:
        return raw
    return raw.encode("latin-1", "backslashreplace").decode("unicode_escape")


_labels = [_unesc(m.group(1))
           for m in _re.finditer(r'label:\s*"((?:[^"\\]|\\.)*)"', _block)]
for _m in _re.finditer(r'\*\[Click [^]]*?"([^"]+)"', _script):
    _want = _m.group(1)
    check(f'the script tells you to click "{_want[:42]}" and that chip exists',
          any(_want == lab for lab in _labels),
          "no chip with that label" if not any(_want == lab for lab in _labels) else "")

# Same idea for the commands. The checklist above the beats tells you to RUN things, and a
# checklist that names a command which does not work is how the quickstart broke once already:
# it said `python3.13`, which is `command not found` on most machines. A chip label is checked
# against the chip list, so a command should be checked against the file it invokes -- including
# its flag, since `./run.sh --forget` silently starting a server would be worse than an error.
import os as _os

for _m in _re.finditer(r"`\./([\w.-]+\.sh)((?:\s+--[\w-]+)*)`", _script):
    _cmd, _flags = _m.group(1), _m.group(2).split()
    check(f"the script tells you to run ./{_cmd} and it is executable",
          _os.access(_cmd, _os.X_OK),
          "missing or not executable" if not _os.access(_cmd, _os.X_OK) else "")
    _body = open(_cmd).read() if _os.path.exists(_cmd) else ""
    for _flag in _flags:
        check(f"./{_cmd} handles {_flag}", f'"{_flag}"' in _body or f"'{_flag}'" in _body,
              "the flag appears nowhere in the script, so it would be ignored"
              if f'"{_flag}"' not in _body and f"'{_flag}'" not in _body else "")

sys.exit(1 if fails else 0)
