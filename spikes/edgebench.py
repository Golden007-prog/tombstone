import time
from falkordb import FalkorDB
db = FalkorDB(host='localhost', port=6380)

def fresh(name, n=20000, batch=1000, index=True):
    g = db.select_graph(name)
    try: g.delete()
    except Exception: pass
    g = db.select_graph(name)
    for i in range(0, n, batch):
        g.query("UNWIND $r AS x CREATE (:N{id:x})", params={'r': list(range(i, i+batch))})
    if index: g.query("CREATE INDEX FOR (n:N) ON (n.id)")
    return g

N, E, B = 20000, 20000, 1000
pairs = [(j % N, (j*7919+13) % N) for j in range(E)]

SKIP_AB=True
# A. baseline: MATCH two nodes by indexed property, CREATE
g = fresh('e_a')
t0=time.perf_counter()
for i in range(0, E, B):
    rows=[{'a':a,'b':b} for a,b in pairs[i:i+B]]
    g.query("UNWIND $r AS x MATCH (a:N{id:x.a}),(b:N{id:x.b}) CREATE (a)-[:L]->(b)", params={'r':rows})
print(f"A. MATCH by indexed prop + CREATE      {E/(time.perf_counter()-t0):9,.0f} edges/sec")

# B. no index (to show the index actually matters)
g = fresh('e_b', index=False)
t0=time.perf_counter()
for i in range(0, 4000, B):
    rows=[{'a':a,'b':b} for a,b in pairs[i:i+B]]
    g.query("UNWIND $r AS x MATCH (a:N{id:x.a}),(b:N{id:x.b}) CREATE (a)-[:L]->(b)", params={'r':rows})
print(f"B. NO index (4k edges only)            {4000/(time.perf_counter()-t0):9,.0f} edges/sec")

# C. internal-ID lookup via WHERE id(n) IN  — avoids property index entirely
g = fresh('e_c')
idmap = {}
for off in range(0, N, 5000):
    for r in g.ro_query("MATCH (n:N) RETURN n.id, id(n) ORDER BY n.id SKIP $o LIMIT 5000", params={'o': off}).result_set:
        idmap[r[0]] = r[1]
print(f"   (idmap built via pagination: {len(idmap)} entries - naive single query returns only 10000 due to RESULTSET_SIZE)")
t0=time.perf_counter()
for i in range(0, E, B):
    rows=[{'a':idmap[a],'b':idmap[b]} for a,b in pairs[i:i+B]]
    g.query("UNWIND $r AS x MATCH (a),(b) WHERE id(a)=x.a AND id(b)=x.b CREATE (a)-[:L]->(b)", params={'r':rows})
print(f"C. internal id() lookup + CREATE       {E/(time.perf_counter()-t0):9,.0f} edges/sec")

# D. bigger batches
g = fresh('e_d')
t0=time.perf_counter()
BB=10000
for i in range(0, E, BB):
    rows=[{'a':a,'b':b} for a,b in pairs[i:i+BB]]
    g.query("UNWIND $r AS x MATCH (a:N{id:x.a}),(b:N{id:x.b}) CREATE (a)-[:L]->(b)", params={'r':rows})
print(f"D. batch=10000 instead of 1000         {E/(time.perf_counter()-t0):9,.0f} edges/sec")

# E. nodes+edges in ONE pass with MERGE (realistic ingest from triples)
g = db.select_graph('e_e')
try: g.delete()
except Exception: pass
g = db.select_graph('e_e')
g.query("CREATE INDEX FOR (n:N) ON (n.id)")
t0=time.perf_counter()
for i in range(0, E, B):
    rows=[{'a':a,'b':b} for a,b in pairs[i:i+B]]
    g.query("UNWIND $r AS x MERGE (a:N{id:x.a}) MERGE (b:N{id:x.b}) MERGE (a)-[:L]->(b)", params={'r':rows})
print(f"E. MERGE nodes+edge, one pass          {E/(time.perf_counter()-t0):9,.0f} edges/sec")

# F. multiple concurrent writer clients
from concurrent.futures import ThreadPoolExecutor
g = fresh('e_f')
def w(shard, nshard):
    d=FalkorDB(host='localhost',port=6380); gg=d.select_graph('e_f')
    my=[p for k,p in enumerate(pairs) if k % nshard == shard]
    for i in range(0,len(my),B):
        rows=[{'a':a,'b':b} for a,b in my[i:i+B]]
        gg.query("UNWIND $r AS x MATCH (a:N{id:x.a}),(b:N{id:x.b}) CREATE (a)-[:L]->(b)", params={'r':rows})
for nw in (4, 8):
    g = fresh('e_f')
    t0=time.perf_counter()
    with ThreadPoolExecutor(max_workers=nw) as ex:
        list(ex.map(lambda s: w(s,nw), range(nw)))
    print(f"F. {nw} concurrent writer clients        {E/(time.perf_counter()-t0):9,.0f} edges/sec")
