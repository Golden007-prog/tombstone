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

# 1. the keyless path earns ANSWERED_FROM_MEMORY on a repeat
q = "verify_memory: which areas are held alone by one approver?"
first, second = a.ask_locally(q), a.ask_locally(q)
ok = first["shape"] == "ANSWERED_WITH_PATH" and second["shape"] == "ANSWERED_FROM_MEMORY"
fails += not ok
print(f"  {'PASS' if ok else 'FAIL'}  keyless repeat    {first['shape']} -> {second['shape']}")

# 2. the citation counts the README prints
for (tool, args), want in CITATIONS.items():
    probe = f"verify_memory: citations for {tool}"
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
