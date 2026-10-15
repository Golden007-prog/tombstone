"""Assert that the output blocks printed in the README are what the app actually returns.

The README shows sample output in fenced blocks: a counterfactual naming the one area that would
be stranded, two routing scores to three decimals, and two ownership-dilution examples naming
people and how many levels approval falls back. Nothing checked any of them.

That is the same class of claim that went stale in the demo script without anything failing --
a beat there named a person and a KEP the app had stopped returning. Printed output is worse than
prose when it drifts, because a reader takes it as a transcript.
"""
from __future__ import annotations

import re
import sys

sys.path.insert(0, "src")
from tombstone.agent import Agent  # noqa: E402

readme = open("README.md").read()
agent = Agent(graph_name="tomb:k8s")
fails = []


def check(label: str, ok: bool, detail: str = "") -> None:
    print(f"  {'PASS' if ok else 'FAIL'}  {label}{(' — ' + detail) if detail else ''}")
    if not ok:
        fails.append(label)


# 1. the counterfactual block
cohort = ["deads2k", "liggitt", "jpbetz", "smarterclayton", "enj", "serathius"]
row = agent.dispatch("what_if_they_go", {"handles": cohort}).rows[0]
stranded, baseline = row[1], row[2]
check("counterfactual strands exactly the area the README prints",
      stranded == ["staging/src/k8s.io/kms/OWNERS"], str(stranded))
check("counterfactual baseline is 0 as printed", baseline == 0, str(baseline))

# 2. the routing scores, to the three decimals the README shows
router = agent.router()
for question, printed in (("which areas have exactly one approver?", 0.990),
                          ("draft the fix for the ownership problem", 0.874)):
    assert f"{printed:.3f}" in readme, f"README no longer prints {printed}"
    got = router.route(question)["score"]
    check(f"routing score for {question[:34]!r}", abs(got - printed) < 0.0005, f"{got:.3f}")

# 3. the two ownership-dilution examples
rows = {r[0]: r for r in agent.dispatch("ownership_dilution", {}).rows}
metrics = rows.get("staging/src/k8s.io/apiserver/pkg/endpoints/metrics/OWNERS")
check("dilution: metrics lost logicalhan and falls back one level",
      bool(metrics) and metrics[1] == ["logicalhan"] and int(metrics[4]) == 1,
      str(metrics[1]) if metrics else "row missing")
windows = rows.get("cluster/gce/windows/OWNERS")
check("dilution: cluster/gce/windows lost five people, falls back two levels",
      bool(windows) and len(windows[1]) == 5 and int(windows[4]) == 2,
      f"{len(windows[1])} people, {windows[4]} levels" if windows else "row missing")

# 4. the drafting summary line
drafted = agent.dispatch("draft_owners_patch", {}).rows
patches = sum(1 for r in drafted if r[3] == "patch")
printed = re.search(r"(\d+) OWNERS patches drafted from the graph, (\d+) candidate", readme)
check("the drafting block's counts match a live run",
      bool(printed) and int(printed.group(1)) == patches
      and int(printed.group(2)) == len(drafted) - patches,
      f"{patches} drafted, {len(drafted) - patches} refused")

print(f"\n{'FAILED' if fails else 'OK'}: the README's printed output "
      f"{'does not match' if fails else 'matches'} the app")
sys.exit(1 if fails else 0)
