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
    ("decisions (:Kep)", "MATCH (k:Kep) RETURN count(k)", 681),
    ("rejected alternatives", "MATCH (a:Alternative) RETURN count(a)", 958),
    ("titled named options", "MATCH (a:NamedOption) RETURN count(a)", 752),
    ("missing decision records", "MATCH (m:MissingRecord) RETURN count(m)", 47),
    ("citations of missing records", "MATCH ()-[r:CITES_MISSING]->() RETURN count(r)", 55),
    ("people", "MATCH (p:Person) RETURN count(p)", 794),
    ("ownership files", "MATCH (o:OwnersFile) RETURN count(o)", 585),
    ("APPROVES edges", "MATCH ()-[r:APPROVES]->() RETURN count(r)", 2584),
    ("EMERITUS_OF edges", "MATCH ()-[r:EMERITUS_OF]->() RETURN count(r)", 298),
    ("CO_AUTHORED edges", "MATCH ()-[r:CO_AUTHORED]->() RETURN count(r)", 5879),
    ("lavalamp emeritus files", "MATCH (:Person{key:'lavalamp'})-[:EMERITUS_OF]->(f) RETURN count(f)", 31),
    ("'0006-apply.md' cited by",
     "MATCH (k:Kep)-[:CITES_MISSING]->(:MissingRecord{key:'/keps/sig-api-machinery/0006-apply.md'}) "
     "RETURN count(k)", 4),
    ("areas that lost every dedicated approver",
     "MATCH (d:Person)-[:EMERITUS_OF]->(f:OwnersFile) "
     "OPTIONAL MATCH (c:Person)-[:APPROVES]->(f) "
     "WITH f, count(DISTINCT c) AS n WHERE n = 0 RETURN count(f)", 7),
    ("OWNERS inheritance edges", "MATCH ()-[r:INHERITS_FROM]->() RETURN count(r)", 584),
    ("OWNERS files that sever inheritance",
     "MATCH (o:OwnersFile) WHERE o.severs_inheritance = true RETURN count(o)", 57),
    ("areas genuinely unowned after walking the tree",
     "MATCH (d:Person)-[:EMERITUS_OF]->(f:OwnersFile) "
     "OPTIONAL MATCH (own:Person)-[:APPROVES]->(f) "
     "WITH f, count(DISTINCT own) AS n WHERE n = 0 "
     "OPTIONAL MATCH (f)-[:INHERITS_FROM*1..8]->(a:OwnersFile)<-[:APPROVES]-(:Person) "
     "WITH f, count(a) AS covered WHERE covered = 0 RETURN count(f)", 0),
    ("departed with no current role",
     "MATCH (p:Person)-[:EMERITUS_OF]->() OPTIONAL MATCH (p)-[c:APPROVES]->() "
     "WITH p, count(c) AS n WHERE n = 0 RETURN count(DISTINCT p)", 83),
    ("total departed people",
     "MATCH (p:Person)-[:EMERITUS_OF]->() RETURN count(DISTINCT p)", 111),
    ("stale decisions still cited",
     "MATCH (o:Kep)-[:SEE_ALSO|REPLACES]->(k:Kep) "
     "WHERE k.status IN ['provisional','implementable'] AND k.created_ms > 0 "
     "AND (1760000000000 - k.created_ms) > 94672800000 "
     "RETURN count(DISTINCT k)", 38),
    ("...with an author who no longer hold approval authority",
     "MATCH (o:Kep)-[:SEE_ALSO|REPLACES]->(k:Kep) "
     "WHERE k.status IN ['provisional','implementable'] AND k.created_ms > 0 "
     "AND (1760000000000 - k.created_ms) > 94672800000 "
     "WITH DISTINCT k "
     "MATCH (au:Person)-[:AUTHORED|APPROVED]->(k) "
     "OPTIONAL MATCH (au)-[lr:APPROVES]->() "
     "OPTIONAL MATCH (au)-[em:EMERITUS_OF]->() "
     "WITH k, au, count(lr) AS live, count(em) AS gone "
     "WITH k, sum(live) AS lives, sum(CASE WHEN gone > 0 AND live = 0 THEN 1 ELSE 0 END) AS stepped "
     "WHERE lives = 0 AND stepped > 0 RETURN count(k)", 2),
    ("KEP authors appearing in no OWNERS file",
     "MATCH (p:Person)-[:AUTHORED|APPROVED]->(:Kep) "
     "OPTIONAL MATCH (p)-[a:APPROVES]->() OPTIONAL MATCH (p)-[e:EMERITUS_OF]->() "
     "WITH p, count(a) AS na, count(e) AS ne WHERE na = 0 AND ne = 0 "
     "RETURN count(DISTINCT p)", 428),
]

fails = 0
for name, q, want in CLAIMS:
    got = one(q)
    ok = got == want
    fails += not ok
    print(f"  {'PASS' if ok else 'FAIL'}  {name:<34} claimed={want:<6} actual={got}")
print(f"\n{len(CLAIMS) - fails}/{len(CLAIMS)} claims verified")
sys.exit(1 if fails else 0)
