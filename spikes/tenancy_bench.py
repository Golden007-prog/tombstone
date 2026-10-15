"""Measure FalkorDB's multi-tenancy claim: latency + memory as tenant-graph count grows,
under a concurrent read/write mix, plus a cross-tenant isolation proof."""
import time, statistics, json, sys
from concurrent.futures import ThreadPoolExecutor
from falkordb import FalkorDB

HOST, PORT = 'localhost', 6380
PREFIX = 'tb'
def conn(): return FalkorDB(host=HOST, port=PORT)
db = conn()

# clean slate
for g in db.list_graphs():
    if g.startswith(PREFIX):
        try: db.select_graph(g).delete()
        except Exception: pass

NODES_PER_TENANT = 200
def seed(tid):
    g = db.select_graph(f'{PREFIX}:{tid}')
    g.query("UNWIND range(0,$n) AS i CREATE (:Fact {id:i, tenant:$t, body:'fact ' + toString(i)})",
            params={'n': NODES_PER_TENANT-1, 't': tid})
    g.query("MATCH (a:Fact),(b:Fact) WHERE a.id=b.id-1 CREATE (a)-[:NEXT]->(b)")
    return g

def mem_mb():
    info = db.connection.execute_command('INFO','memory')
    if isinstance(info, dict):
        v = info.get('used_memory') or info.get(b'used_memory')
        return float(v)/1048576
    if isinstance(info, bytes): info = info.decode()
    for line in str(info).split('\n'):
        if line.startswith('used_memory:'): return int(line.split(':')[1])/1048576
    return float('nan')

CHECKPOINTS = [1, 10, 50, 100, 250, 500, 1000]
rows = []
created = 0
base_mem = mem_mb()
t_create_total = 0.0

for cp in CHECKPOINTS:
    t0 = time.perf_counter()
    while created < cp:
        seed(created); created += 1
    t_create_total += time.perf_counter() - t0

    # read latency on a RANDOM tenant at this scale (2-hop traversal)
    lat = []
    for i in range(60):
        tid = (i * 37) % created
        g = db.select_graph(f'{PREFIX}:{tid}')
        s = time.perf_counter()
        g.ro_query("MATCH (a:Fact{id:0})-[:NEXT*1..2]->(b) RETURN count(b)")
        lat.append((time.perf_counter()-s)*1000)
    lat.sort()
    # write latency
    wlat = []
    for i in range(40):
        tid = (i * 17) % created
        g = db.select_graph(f'{PREFIX}:{tid}')
        s = time.perf_counter()
        g.query("CREATE (:Fact {id:$i, tenant:$t, body:'new'})", params={'i': 9000+i, 't': tid})
        wlat.append((time.perf_counter()-s)*1000)
    wlat.sort()
    # graph selection overhead (does picking among N graphs cost anything?)
    s = time.perf_counter()
    for i in range(200): db.select_graph(f'{PREFIX}:{i % created}')
    sel_us = (time.perf_counter()-s)/200*1e6

    m = mem_mb()
    rows.append(dict(tenants=created, read_p50=statistics.median(lat), read_p99=lat[int(len(lat)*0.99)],
                     write_p50=statistics.median(wlat), write_p99=wlat[int(len(wlat)*0.99)],
                     mem_mb=round(m,1), mem_per_tenant_kb=round((m-base_mem)*1024/created,1),
                     select_us=round(sel_us,1)))
    print(f"tenants={created:>5}  read p50={rows[-1]['read_p50']:6.2f}ms p99={rows[-1]['read_p99']:7.2f}ms  "
          f"write p50={rows[-1]['write_p50']:6.2f}ms  mem={m:7.1f}MB ({rows[-1]['mem_per_tenant_kb']:6.1f}KB/tenant)  "
          f"select={sel_us:5.1f}us", flush=True)

print(f"\ntotal time to create {created} tenant graphs ({NODES_PER_TENANT} nodes each): {t_create_total:.2f}s "
      f"= {created/t_create_total:,.0f} tenants/sec")

# ---- concurrent mixed workload ACROSS tenants at full scale ----
print(f"\n=== concurrent mixed read/write across {created} tenants ===")
def mixed(worker, n, nt):
    d = conn(); lat_r=[]; lat_w=[]
    for i in range(n):
        tid = (worker*101 + i*7) % nt
        g = d.select_graph(f'{PREFIX}:{tid}')
        if i % 4 == 3:
            s=time.perf_counter(); g.query("CREATE (:Fact{id:$i,tenant:$t})",params={'i':50000+i,'t':tid}); lat_w.append((time.perf_counter()-s)*1000)
        else:
            s=time.perf_counter(); g.ro_query("MATCH (a:Fact{id:0})-[:NEXT*1..2]->(b) RETURN count(b)"); lat_r.append((time.perf_counter()-s)*1000)
    return lat_r, lat_w

for workers in (1, 8, 32, 64):
    per = max(480//workers, 20)
    t0=time.perf_counter()
    with ThreadPoolExecutor(max_workers=workers) as ex:
        out = list(ex.map(lambda w: mixed(w, per, created), range(workers)))
    el = time.perf_counter()-t0
    R=sorted(x for r,_ in out for x in r); W=sorted(x for _,w in out for x in w)
    tot=len(R)+len(W)
    print(f"  x{workers:>2}: {tot:>4} ops in {el:5.2f}s = {tot/el:7,.0f} ops/s | "
          f"read p50 {statistics.median(R):5.2f} p99 {R[int(len(R)*.99)]:6.2f}ms | "
          f"write p50 {statistics.median(W):5.2f} p99 {W[int(len(W)*.99)]:6.2f}ms")

# ---- cross-tenant isolation PROOF ----
print("\n=== cross-tenant isolation proof ===")
g0 = db.select_graph(f'{PREFIX}:0')
g1 = db.select_graph(f'{PREFIX}:1')
g0.query("CREATE (:Secret {text:'TENANT-0-ONLY-SECRET'})")
r_own = g0.ro_query("MATCH (s:Secret) RETURN s.text").result_set
r_other = g1.ro_query("MATCH (s:Secret) RETURN s.text").result_set
print(f"  tenant 0 queries its own Secret  -> {r_own}")
print(f"  tenant 1 runs the SAME Cypher    -> {r_other}   <-- {'ISOLATED (0 rows)' if not r_other else 'LEAK!'}")
labels_1 = [r[0] for r in g1.ro_query("CALL db.labels()").result_set]
print(f"  tenant 1 db.labels() -> {labels_1}  <-- 'Secret' {'absent' if 'Secret' not in labels_1 else 'PRESENT = LEAK'}")
print(f"  => isolation is physical (separate graph keyspaces), not a WHERE-clause filter.")

json.dump(rows, open('/private/tmp/claude-501/-Users-aviralgarg-graph-hack/fc30c4d5-48b3-421d-a907-6b8c81f1ecb3/scratchpad/tenancy_results.json','w'), indent=1)
print("\nresults -> tenancy_results.json")
