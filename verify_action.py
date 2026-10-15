"""Re-check the README's claims about the ONE action, against a live run of it.

verify_claims.py checks graph counts. This checks the drafting layer's own output, because the
README states how many patches it drafts and how many candidates it refuses, and those numbers
come from the corpus cross-check rather than from Cypher.
"""
import sys

sys.path.insert(0, "src")
from tombstone.agent import Agent  # noqa: E402

CLAIMED = {"candidates": 3, "drafted": 2, "refused": 1, "refusal_kinds": {"via_alias"}}

a = Agent(graph_name="tomb:k8s")
ans = a.dispatch("draft_owners_patch", {})
if ans.shape != "ANSWERED_WITH_PATH":
    sys.exit(f"the action did not run: {ans.shape} — {ans.note}")

drafted = [r for r in ans.rows if r[3] == "patch"]
refused = [r for r in ans.rows if r[3] != "patch"]
got = {"candidates": len(ans.rows), "drafted": len(drafted),
       "refused": len(refused), "refusal_kinds": {r[3] for r in refused}}

fails = 0
for key, want in CLAIMED.items():
    ok = got[key] == want
    fails += not ok
    print(f"  {'PASS' if ok else 'FAIL'}  {key:<14} claimed={want}  actual={got[key]}")

# every refusal must carry a reason, and no patch may invent a handle
for person, path, _n, kind, why, _d, proposed in ans.rows:
    if kind != "patch":
        if not why.strip():
            print(f"  FAIL  refusal for {path} carried no reason"); fails += 1
        continue
    import yaml
    original = {h for v in a.corpus().owners[path].values() if isinstance(v, list) for h in v}
    after = {h for v in (yaml.safe_load(proposed) or {}).values() if isinstance(v, list) for h in v}
    if not after <= original:
        print(f"  FAIL  {path} invented {after - original}"); fails += 1

print(f"\n{len(CLAIMED) - fails}/{len(CLAIMED)} action claims verified"
      if fails <= len(CLAIMED) else "")
sys.exit(1 if fails else 0)
