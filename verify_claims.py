"""Re-check every factual claim in the README against the live graph.

Run: PYTHONPATH=src python verify_claims.py
A judge should be able to falsify any number in this repo in one command.
"""
import sys
sys.path.insert(0, "src")
from graphkit.ingest import connect

g = connect().select_graph("tomb:k8s")
one = lambda q, p=None: g.ro_query(q, params=p or {}).result_set[0][0]

CLAIMS = [
    ("decisions (:Kep)", "MATCH (k:Kep) RETURN count(k)", 679),
    ("rejected alternatives", "MATCH (a:Alternative) RETURN count(a)", 959),
    ("titled named options", "MATCH (a:NamedOption) RETURN count(a)", 753),
    ("missing decision records", "MATCH (m:MissingRecord) RETURN count(m)", 52),
    ("citations of missing records", "MATCH ()-[r:CITES_MISSING]->() RETURN count(r)", 63),
    ("people", "MATCH (p:Person) RETURN count(p)", 794),
    ("ownership files", "MATCH (o:OwnersFile) RETURN count(o)", 585),
    ("APPROVES edges", "MATCH ()-[r:APPROVES]->() RETURN count(r)", 2584),
    ("EMERITUS_OF edges", "MATCH ()-[r:EMERITUS_OF]->() RETURN count(r)", 298),
    ("CO_AUTHORED edges", "MATCH ()-[r:CO_AUTHORED]->() RETURN count(r)", 5870),
    ("lavalamp emeritus files", "MATCH (:Person{key:'lavalamp'})-[:EMERITUS_OF]->(f) RETURN count(f)", 31),
    ("'0006-apply.md' cited by",
     "MATCH (k:Kep)-[:CITES_MISSING]->(:MissingRecord{key:'/keps/sig-api-machinery/0006-apply.md'}) "
     "RETURN count(k)", 4),
    ("areas with zero current approvers",
     "MATCH (d:Person)-[:EMERITUS_OF]->(f:OwnersFile) "
     "OPTIONAL MATCH (c:Person)-[:APPROVES]->(f) "
     "WITH f, count(DISTINCT c) AS n WHERE n = 0 RETURN count(f)", 7),
    ("departed with no current role",
     "MATCH (p:Person)-[:EMERITUS_OF]->() OPTIONAL MATCH (p)-[c:APPROVES]->() "
     "WITH p, count(c) AS n WHERE n = 0 RETURN count(DISTINCT p)", 83),
    ("total departed people",
     "MATCH (p:Person)-[:EMERITUS_OF]->() RETURN count(DISTINCT p)", 111),
]

fails = 0
for name, q, want in CLAIMS:
    got = one(q)
    ok = got == want
    fails += not ok
    print(f"  {'PASS' if ok else 'FAIL'}  {name:<34} claimed={want:<6} actual={got}")
print(f"\n{len(CLAIMS) - fails}/{len(CLAIMS)} claims verified")
sys.exit(1 if fails else 0)
