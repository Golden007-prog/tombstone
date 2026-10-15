"""Re-check the blog post's factual claims against the live graph.

The README's numbers are checked by verify_claims.py and the printed output by another script.
The blog was never covered, and it is the artifact that goes out under a byline to an audience
that cannot run anything -- so a stale number there is both the most embarrassing and the least
correctable. It had four wrong when it was read end to end, one of them a figure the README had
retracted hours earlier.

These are the specific claims the post makes. The corpus-wide counts are covered separately by
scripts_check_doc_counts.py, which reads the blog among other files.
"""
from __future__ import annotations

import sys

sys.path.insert(0, "src")
from graphkit.ingest import connect       # noqa: E402
from tombstone.snapshot import load       # noqa: E402

g = connect().select_graph("tomb:k8s")
corpus = load()


def q(cypher: str) -> int:
    return g.ro_query(cypher).result_set[0][0]


owners_with_emeritus = sum(1 for d in corpus.owners.values() if (d or {}).get("emeritus_approvers"))
total_owners = len(corpus.owners)

CLAIMS = {
    "OWNERS files parsed": (total_owners, 585),
    "declare emeritus approvers": (owners_with_emeritus, 138),
    "...as a percentage": (round(owners_with_emeritus / total_owners * 100, 1), 23.6),
    "emeritus entries": (q("MATCH ()-[r:EMERITUS_OF]->() RETURN count(r)"), 298),
    "distinct emeritus people": (
        q("MATCH (p:Person)-[:EMERITUS_OF]->() RETURN count(DISTINCT p)"), 111),
    "of those, hold no approval anywhere": (q(
        "MATCH (p:Person)-[:EMERITUS_OF]->() OPTIONAL MATCH (p)-[a:APPROVES]->() "
        "WITH p, count(a) AS n WHERE n = 0 RETURN count(DISTINCT p)"), 83),
    "titled rejected options": (q("MATCH (n:NamedOption) RETURN count(n)"), 752),
    "internal pointers that go nowhere": (
        q("MATCH ()-[r:CITES_MISSING]->() RETURN count(r)"), 55),
    "decisions claiming descent from apply.md": (q(
        "MATCH (m:MissingRecord)<-[:CITES_MISSING]-(k:Kep) "
        "WITH m, count(DISTINCT k) AS n ORDER BY n DESC LIMIT 1 RETURN n"), 4),
}

blog = open("docs/BLOG-POST.md").read()
fails = 0
for label, (live, claimed) in CLAIMS.items():
    printed = str(claimed) in blog
    ok = live == claimed and printed
    fails += not ok
    note = "" if printed else "  (the post no longer prints this)"
    print(f"  {'PASS' if ok else 'FAIL'}  {label:<38} post={claimed:<7} live={live}{note}")

print(f"\n{len(CLAIMS) - fails}/{len(CLAIMS)} blog claims verified")
# The post states two counts of its own: how many FalkorDB lessons it carries, and how many CI
# steps run. Both were typed. The second was already stale -- it said twenty-seven while thirty
# run -- which is the same way five other numbers in this repo went wrong in two days.
import re as _re

_WORDS = {8: "Eight", 9: "Nine", 10: "Ten", 11: "Eleven", 12: "Twelve"}
_n_lessons = len(_re.findall(r"^### \d+\.", blog, _re.M))
_said = _re.search(r"^## (\w+) things FalkorDB taught me", blog, _re.M)
_ok = bool(_said) and _said.group(1) == _WORDS.get(_n_lessons)
print(f"  {'PASS' if _ok else 'FAIL'}  the post says it has {_said.group(1) if _said else '?'} "
      f"FalkorDB lessons and carries {_n_lessons}")
fails += not _ok

_NUMWORDS = {27: "Twenty-seven", 28: "Twenty-eight", 29: "Twenty-nine", 30: "Thirty",
             31: "Thirty-one", 32: "Thirty-two"}
_steps = sum(1 for _l in open(".github/workflows/verify.yml") if _re.match(r"^\s*- name:", _l))
_said_ci = _re.search(r"(\w+(?:-\w+)?) CI steps\.", blog)
_ok_ci = bool(_said_ci) and _said_ci.group(1) == _NUMWORDS.get(_steps)
print(f"  {'PASS' if _ok_ci else 'FAIL'}  the post says {_said_ci.group(1) if _said_ci else '?'} "
      f"CI steps and the workflow has {_steps}")
fails += not _ok_ci

sys.exit(1 if fails else 0)
