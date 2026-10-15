"""Re-check the README's memory claims against a live run.

The memory section sat in the README for most of this project's life while the feature silently
did nothing on the keyless path -- the hosted configuration. Prose was not enough, so these are
the claims as assertions:

  1. a repeat question on the KEYLESS path comes back ANSWERED_FROM_MEMORY,
  2. the tools the README names cite the number of nodes it says they do,
  3. one query crosses from memory into facts,
  4. recall survives rewording.

`hollowing_communities` is label propagation and is documented as non-deterministic, so its count
is checked here deliberately: CI rebuilds the graph from the snapshot on every run, and if that
number is not actually stable this is where it will say so rather than the README quietly being
wrong.
"""
import sys
import time

sys.path.insert(0, "src")
from graphkit.ingest import connect          # noqa: E402
from tombstone.agent import Agent            # noqa: E402

GRAPH = "tomb:k8s"
CITATIONS = {                    # tool -> citations the README states
    ("sole_approver_risk", ()): 42,
    ("hollowing_communities", (("min_size", 5),)): 22,
    ("draft_owners_patch", ()): 6,
}

fails = 0
a = Agent(graph_name=GRAPH)

# 1. the keyless path earns ANSWERED_FROM_MEMORY on a repeat.
#
# The question carries a timestamp so each run starts genuinely unasked. Without that, the second
# time this script ever ran the FIRST ask already came back remembered -- memory persists across
# runs, which is the whole point of it -- and the check reported a failure for the feature
# working correctly. The invariant is the fresh -> remembered transition, so the probe has to be
# fresh.
#
# The probe also has to be unique WITHOUT depending on noisy text routing correctly. Prefixing a
# real question with "verify_memory:" and a bracketed nanosecond count perturbs the embedding
# enough to move it: the clean sentence routes to sole_approver_risk outright, the decorated one
# landed 0.014 from who_owns and was declined as a near-tie. That is the router behaving
# correctly on a string no human would type, failing a check about something else entirely. So
# the probe names its tool, and the routing of the UNDECORATED question is asserted separately
# just below -- each check measuring the one thing it is about.
q = f"verify_memory: which areas are held alone by one approver? [{time.time_ns()}]"
first = a.ask_locally(q, force="sole_approver_risk")
second = a.ask_locally(q, force="sole_approver_risk")
ok = first["shape"] == "ANSWERED_WITH_PATH" and second["shape"] == "ANSWERED_FROM_MEMORY"
fails += not ok
print(f"  {'PASS' if ok else 'FAIL'}  keyless repeat    {first['shape']} -> {second['shape']}")

# ...and the question itself, undecorated, still routes where it should with no help.
routed = a.router().route("which areas are held alone by one approver?")
ok_route = routed.get("tool") == "sole_approver_risk"
fails += not ok_route
print(f"  {'PASS' if ok_route else 'FAIL'}  keyless routing   "
      f"{routed.get('tool')} (expected sole_approver_risk)")

# 2. the citation counts the README prints
for (tool, args), want in CITATIONS.items():
    probe = f"verify_memory: citations for {tool} [{time.time_ns()}]"
    ans = a.dispatch(tool, dict(args))
    a._remember(probe, tool, ans)
    rec = a.memory.recall_exact(probe, ans.tool or tool)
    got = rec[5] if rec else 0
    ok = got == want
    fails += not ok
    print(f"  {'PASS' if ok else 'FAIL'}  {tool:<24} claimed={want:<4} actual={got}")

# 3. one query that starts in memory and ends in facts
rows = connect().select_graph(GRAPH).ro_query("""
MATCH (ans:Answer)-[:CITED]->(p:Person)-[:EMERITUS_OF]->(f:OwnersFile)
RETURN ans.question, p.key, count(DISTINCT f) AS areas_they_left
ORDER BY areas_they_left DESC LIMIT 1
""").result_set
ok = bool(rows)
fails += not ok
print(f"  {'PASS' if ok else 'FAIL'}  memory -> facts   "
      f"{(rows[0][1] + ' left ' + str(rows[0][2]) + ' areas') if rows else 'no crossing found'}")

# 4. recall survives rewording
a.ask_locally("who owns pkg/controller/podgc/OWNERS?")
found = a.dispatch("recall", {"question": "who currently owns the podgc controller"})
ok = found.shape == "ANSWERED_WITH_PATH" and bool(found.rows)
fails += not ok
print(f"  {'PASS' if ok else 'FAIL'}  reworded recall   {found.shape}")

total = 3 + len(CITATIONS)
print(f"\n{total - fails}/{total} memory claims verified")
sys.exit(1 if fails else 0)
