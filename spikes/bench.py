import time, threading, statistics, sys
from concurrent.futures import ThreadPoolExecutor
from falkordb import FalkorDB

HOST, PORT = 'localhost', 6380

def newdb(): return FalkorDB(host=HOST, port=PORT)

db = newdb()
g = db.select_graph('bench')
try: g.delete()
except Exception: pass
g = db.select_graph('bench')

print("FalkorDB client -> 6380 OK:", g.query('RETURN 1 AS x').result_set)

# ---------- 1. Bulk ingest throughput (batched UNWIND) ----------
N, BATCH = 20000, 1000
t0 = time.perf_counter()
for i in range(0, N, BATCH):
    rows = [{'id': j, 'name': f'n{j}', 'grp': j % 50} for j in range(i, i+BATCH)]
    g.query("UNWIND $rows AS r CREATE (:Node {id:r.id, name:r.name, grp:r.grp})", params={'rows': rows})
t_ingest = time.perf_counter() - t0
print(f"\n[ingest] {N} nodes in {t_ingest:.2f}s = {N/t_ingest:,.0f} nodes/sec (UNWIND batches of {BATCH})")

g.query("CREATE INDEX FOR (n:Node) ON (n.id)")
E = 40000
t0 = time.perf_counter()
for i in range(0, E, BATCH):
    rows = [{'a': j % N, 'b': (j*7919+13) % N} for j in range(i, i+BATCH)]
    g.query("UNWIND $rows AS r MATCH (a:Node{id:r.a}),(b:Node{id:r.b}) CREATE (a)-[:LINK]->(b)", params={'rows': rows})
t_edges = time.perf_counter() - t0
print(f"[ingest] {E} edges in {t_edges:.2f}s = {E/t_edges:,.0f} edges/sec")

# ---------- 2. Concurrent READ throughput ----------
def read_worker(n, q, params_fn):
    d = newdb(); gg = d.select_graph('bench'); lat = []
    for i in range(n):
        s = time.perf_counter(); gg.ro_query(q, params=params_fn(i)); lat.append((time.perf_counter()-s)*1000)
    return lat

Q2HOP = "MATCH (a:Node{id:$id})-[:LINK*1..2]->(b) RETURN count(DISTINCT b) AS c"
for workers in (1, 4, 8, 16, 32):
    per = max(400 // workers, 25)
    t0 = time.perf_counter()
    with ThreadPoolExecutor(max_workers=workers) as ex:
        allat = [l for f in [ex.submit(read_worker, per, Q2HOP, lambda i, w=w: {'id': (i*31+w*7) % N}) for w in range(workers)] for l in f.result()]
    el = time.perf_counter() - t0
    allat.sort()
    print(f"[read  x{workers:>2}] {len(allat):>4} q in {el:5.2f}s = {len(allat)/el:7,.0f} q/s | p50 {statistics.median(allat):6.2f}ms p99 {allat[int(len(allat)*0.99)]:7.2f}ms")

# ---------- 3. Concurrent WRITE throughput (the T2 question) ----------
def write_worker(w, n):
    d = newdb(); gg = d.select_graph('bench'); lat = []
    for i in range(n):
        s = time.perf_counter()
        gg.query("MERGE (m:Mem{k:$k}) SET m.v=$v, m.w=$w",
                 params={'k': f'w{w}-i{i}', 'v': f'val{i}', 'w': w})
        lat.append((time.perf_counter()-s)*1000)
    return lat
g.query("CREATE INDEX FOR (m:Mem) ON (m.k)")
for workers in (1, 4, 8, 16, 32):
    per = max(300 // workers, 20)
    t0 = time.perf_counter()
    with ThreadPoolExecutor(max_workers=workers) as ex:
        allat = [l for f in [ex.submit(write_worker, w, per) for w in range(workers)] for l in f.result()]
    el = time.perf_counter() - t0
    allat.sort()
    print(f"[write x{workers:>2}] {len(allat):>4} w in {el:5.2f}s = {len(allat)/el:7,.0f} w/s | p50 {statistics.median(allat):6.2f}ms p99 {allat[int(len(allat)*0.99)]:7.2f}ms")

# ---------- 4. Multigraph (per-tenant) isolation + cost ----------
t0 = time.perf_counter()
for t in range(200):
    gt = db.select_graph(f'tenant_{t}')
    gt.query("CREATE (:Seed{t:$t})", params={'t': t})
t_mg = time.perf_counter() - t0
print(f"\n[multigraph] created 200 isolated tenant graphs in {t_mg:.2f}s = {200/t_mg:,.0f} graphs/sec")
print(f"[multigraph] GRAPH.LIST count = {len(db.list_graphs())}")

# ---------- 5. Algorithm timing at scale ----------
for name, q in [
    ("pageRank",        "CALL algo.pageRank('Node','LINK') YIELD node,score RETURN count(node)"),
    ("WCC",             "CALL algo.WCC({nodeLabels:['Node'],relationshipTypes:['LINK']}) YIELD node RETURN count(node)"),
    ("labelPropagation","CALL algo.labelPropagation({nodeLabels:['Node'],relationshipTypes:['LINK']}) YIELD node RETURN count(node)"),
    ("betweenness",     "CALL algo.betweenness({nodeLabels:['Node'],relationshipTypes:['LINK']}) YIELD node RETURN count(node)"),
]:
    try:
        t0=time.perf_counter(); r=g.ro_query(q); el=(time.perf_counter()-t0)*1000
        print(f"[algo] {name:<17} {el:9.1f}ms over {N} nodes / {E} edges -> {r.result_set[0][0]}")
    except Exception as e:
        print(f"[algo] {name:<17} FAILED: {str(e)[:90]}")

print("\n[mem]", db.connection.execute_command('GRAPH.MEMORY','USAGE','bench'))
