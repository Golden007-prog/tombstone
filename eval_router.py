"""A held-out eval for the keyless router. Not the cases it was tuned on.

`tests/test_invariants.py` already locks ten routing cases and five refusals, but those are the
cases the router was built against -- passing them says it did not regress, not that it works on
language nobody wrote for it. The hosted demo has no API key, so this router IS the ask box for
every judge who types something, and nothing measured whether it survives a phrasing it has never
seen.

So: twenty-six questions written from what each tool is FOR, phrased the way a Kubernetes
contributor would actually type them, deliberately without reading `PHRASES` in `route.py` first --
otherwise this measures how well I can copy a lookup table. Plus ten things that are not questions
about this graph at all, which must be refused rather than scored into the nearest tool.

An open set is the hard part. Picking the best of thirteen options is easy; knowing that none of
the thirteen is right is what a bare similarity threshold cannot do, which is why the
out-of-domain bucket exists.

Run: PYTHONPATH=src python eval_router.py
"""
from __future__ import annotations

import sys

sys.path.insert(0, "src")
from tombstone.agent import Agent  # noqa: E402

# (question, the tool a reasonable person would expect). Written from the tool's purpose, not from
# the router's phrase list.
HELD_OUT = [
    # who_owns
    ("who is responsible for pkg/scheduler these days", "who_owns"),
    ("i need a reviewer for staging/src/k8s.io/apiserver, who should i ping", "who_owns"),
    ("which humans can approve a change under pkg/auth", "who_owns"),
    # sole_approver_risk
    ("where do we have a single point of failure in review", "sole_approver_risk"),
    ("show me the areas that depend on one person", "sole_approver_risk"),
    ("what has a bus factor of one", "sole_approver_risk"),
    # ownership_dilution
    ("which parts of the tree have no dedicated owner left", "ownership_dilution"),
    ("where did all the approvers leave", "ownership_dilution"),
    # has_this_been_tried
    ("did we already reject putting this behind a feature gate", "has_this_been_tried"),
    ("was storing this in etcd directly ever considered", "has_this_been_tried"),
    ("has someone proposed using a webhook for this before", "has_this_been_tried"),
    # stepped_back_bridges
    ("who was the biggest loss when they stopped reviewing", "stepped_back_bridges"),
    ("which departure hurt the project most structurally", "stepped_back_bridges"),
    # hollowing_communities
    ("which team is quietly losing all its people", "hollowing_communities"),
    ("are any contributor clusters dying out", "hollowing_communities"),
    # stale_knowledge
    ("what decisions here are out of date", "stale_knowledge"),
    ("which old proposals are still being referenced", "stale_knowledge"),
    # broken_lineage
    ("are there references to KEPs that were never written", "broken_lineage"),
    ("what do we cite that does not exist", "broken_lineage"),
    # successor_for
    ("if lavalamp is gone who picks up their areas", "successor_for"),
    ("who already shares ownership with spiffxp", "successor_for"),
    # what_if_they_go
    ("what breaks if deads2k and liggitt both stop approving", "what_if_they_go"),
    ("simulate losing jpbetz and smarterclayton", "what_if_they_go"),
    # stepped_back_but_still_listed
    ("whose ownership records contradict themselves", "stepped_back_but_still_listed"),
    # draft_owners_patch
    ("can you write the OWNERS change to fix that", "draft_owners_patch"),
    ("generate a patch for the inconsistent ownership files", "draft_owners_patch"),
]

# Not questions about this graph. The router must say so rather than pick a nearest neighbour.
OUT_OF_DOMAIN = [
    "what is the capital of France",
    "summarise the kubernetes release notes for 1.31",
    "write a dockerfile for a python service",
    "explain how etcd raft works",
    "how do i install kubectl on macos",
    "what time is the standup",
    "translate this error message into spanish",
    "give me a haiku about yaml",
    "should i use postgres or mysql",
    "fix my failing unit test",
]


def main() -> int:
    router = Agent(graph_name="tomb:k8s").router()

    right, wrong, refused = [], [], []
    for question, expected in HELD_OUT:
        got = router.route(question) or {}
        tool = got.get("tool")
        if tool == expected:
            right.append((question, expected, got.get("score")))
        elif tool in (None, "", "__out_of_domain__"):
            # A refusal is not a dead end any more. When the router declines a near-tie it shows
            # the candidates it could not choose between, and the UI offers them as buttons -- so
            # a refusal whose `near` list contains the right tool is one click from the answer.
            # That distinction matters: "declined and offered it" is a different product than
            # "declined and shrugged".
            offered = [n.get("tool") for n in (got.get("near") or [])]
            refused.append((question, expected, expected in offered,
                            offered.index(expected) + 1 if expected in offered else 0))
        else:
            wrong.append((question, expected, tool, got.get("score")))

    held, kept = [], []
    for question in OUT_OF_DOMAIN:
        got = router.route(question) or {}
        tool = got.get("tool")
        (held if tool in (None, "", "__out_of_domain__") else kept).append((question, tool))

    n = len(HELD_OUT)
    reach = len(right) + sum(1 for *_x, ok, _rank in refused if ok)
    print(f"Held-out routing: {len(right)}/{n} to the expected tool, "
          f"{len(wrong)} to a different tool, {len(refused)} declined.")
    print(f"Reachable:        {reach}/{n} either answered directly or offered the right tool "
          f"among the candidates it declined between.")
    print(f"Out of domain:    {len(held)}/{len(OUT_OF_DOMAIN)} correctly refused.")

    if wrong:
        print("\nRouted somewhere else — each of these is a judge typing something and getting "
              "an answer to a question they did not ask:")
        for q, exp, got, sc in wrong:
            print(f"  {q!r}\n      expected {exp}, got {got} ({sc})")
    recoverable = sum(1 for *_x, ok, _rank in refused if ok)
    if refused:
        print(f"\nRefused a question this graph can answer. {recoverable} of {len(refused)} "
              f"offered the right tool among the candidates, so they are one click away:")
        for q, exp, ok, rank in refused:
            where = f"offered, ranked {rank}" if ok else "NOT offered"
            print(f"  {q!r}\n      expected {exp} — {where}")
    if kept:
        print("\nAnswered something out of domain — the failure that matters most:")
        for q, got in kept:
            print(f"  {q!r} -> {got}")

    # The README prints these numbers in a table. Nothing checked that it agreed with this
    # script, which is how every other number in this repo has gone stale -- three times in two
    # days. Assert it here, where the numbers are actually produced.
    import re as _re
    # Flattened for the same reason as the other prose checks: these phrases wrap, and a
    # line break moving between "the eight declines" and "are margin failures" would
    # retire the check on a reformat rather than on a real change.
    readme = _re.sub(r"\s*\n>?\s*", " ", open("README.md").read())
    start = readme.find("I measured that router on language it had never seen")
    if start < 0:
        print("\nFAIL: the README no longer has the section that quotes these numbers.")
        return 1
    table = readme[start:readme.find("\n## ", start + 10)]
    stated = {
        "answered, correct tool": len(right),
        "routed to a \\*different\\* tool": len(wrong),
        "declined": len(refused),
        "of those, the right tool was among the candidates offered": recoverable,
        "reachable — answered, or one click away": reach,
        "not a question about this graph, correctly refused": len(held),
    }
    drift = []
    for label, actual in stated.items():
        row = _re.search(rf"\|\s*{label}\s*\|\s*\*?\*?(\d+)(?: of (\d+))?\*?\*?\s*\|", table)
        if not row:
            drift.append(f"README has no row for {label!r}")
            continue
        if int(row.group(1)) != actual:
            drift.append(f"README says {row.group(1)} for {label!r}; this run measured {actual}")
    # The table rows above are checked; the PROSE under them was not, and it had drifted. It
    # said the right tool ranked first in five of the eight declines when it is four, and said
    # the two unreachable questions were named in a table that only counts them. Both are the
    # sentence a reader actually takes away, sitting under a table nobody disagrees with.
    _margin = _top1 = 0
    for _q, _exp in HELD_OUT:
        _g = router.route(_q) or {}
        if _g.get("tool") not in (None, "", "__out_of_domain__"):
            continue
        _near = _g.get("near") or []
        _sc = [x.get("score") for x in _near if x.get("score") is not None]
        if len(_sc) >= 2 and (_sc[0] - _sc[1]) < 0.015:
            _margin += 1
        if _near and _near[0].get("tool") == _exp:
            _top1 += 1
    _WORDS = {0: "zero", 1: "one", 2: "two", 3: "three", 4: "four", 5: "five", 6: "six",
              7: "seven", 8: "eight", 9: "nine", 10: "ten"}
    _m = _re.search(r"(\w+) of the eight declines are \*margin\* failures", readme)
    if not _m:
        drift.append("README no longer states how many declines are margin failures")
    elif _m.group(1).lower() != _WORDS.get(_margin):
        drift.append(f"README says {_m.group(1)} declines are margin failures; measured {_margin}")
    _m2 = _re.search(r"in (\w+) of them the right tool is the one it ranked first", readme)
    if not _m2:
        drift.append("README no longer says in how many the right tool ranked first")
    elif _m2.group(1).lower() != _WORDS.get(_top1):
        drift.append(f"README says the right tool ranked first in {_m2.group(1)} declines; "
                     f"measured {_top1}")

    if drift:
        print("\nThe README disagrees with this eval:")
        for d in drift:
            print("  -", d)

    # The bar: anything out of domain that gets answered is a correctness failure, so that half
    # must be perfect. Routing a real question to the wrong tool is worse than refusing it, since
    # a refusal says so and a wrong tool looks like an answer.
    ok = (not kept and not drift and len(wrong) <= 3 and len(right) >= int(0.70 * n))
    print("\n" + ("PASS" if ok else "FAIL") + f": {len(right)}/{n} held-out, "
          f"{len(held)}/{len(OUT_OF_DOMAIN)} refusals.")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
