import os, sys, time, yaml, re, collections
sys.path.insert(0, "/Users/aviralgarg/graph hack/src")
from graphkit.ingest import connect, Ingestor

ENH='/tmp/khack/enhancements/keps'; K8S='/tmp/khack/k8s'
t_all=time.perf_counter()

# ---- parse KEPs
t0=time.perf_counter()
keps={}
for dp,dn,fn in os.walk(ENH):
    if 'kep.yaml' in fn:
        try: d=yaml.safe_load(open(os.path.join(dp,'kep.yaml'),encoding='utf-8',errors='replace'))
        except Exception: continue
        if isinstance(d,dict): keps[os.path.relpath(dp,ENH)]=d
print(f"parse {len(keps)} KEPs: {time.perf_counter()-t0:.2f}s")

# ---- parse OWNERS
t0=time.perf_counter()
owners={}
for dp,dn,fn in os.walk(K8S):
    if '/.git' in dp: continue
    if 'OWNERS' in fn:
        p=os.path.join(dp,'OWNERS')
        try: d=yaml.safe_load(open(p,encoding='utf-8',errors='replace'))
        except Exception: continue
        if isinstance(d,dict): owners[os.path.relpath(p,K8S)]=d
print(f"parse {len(owners)} OWNERS: {time.perf_counter()-t0:.2f}s")

db=connect(); g=db.select_graph('k8s_test')
ing=Ingestor(g, drop=True)

# ---- nodes
t0=time.perf_counter()
kep_rows=[]
for rel,d in keps.items():
    st=str(d.get('status','')).strip().strip('"').split('#')[0].strip().lower()
    kep_rows.append(dict(key=rel, title=str(d.get('title',''))[:200], status=st,
                         sig=str(d.get('owning-sig','')), num=str(d.get('kep-number','')),
                         created=str(d.get('creation-date',''))[:10]))
ing.nodes('Kep', kep_rows)

people=set(); sigs=set()
for rel,d in keps.items():
    if d.get('owning-sig'): sigs.add(str(d['owning-sig']))
    for f in ('authors','approvers','reviewers','editor'):
        v=d.get(f)
        if isinstance(v,str): v=[v]
        for p in (v or []):
            if isinstance(p,str) and p.strip() and p.strip().lower() not in ('tbd','n/a','none',''):
                people.add(p.strip().lstrip('@').lower())
for rel,d in owners.items():
    for f in ('approvers','reviewers','emeritus_approvers'):
        for p in (d.get(f) or []):
            if isinstance(p,str) and p.strip(): people.add(p.strip().lstrip('@').lower())

ing.nodes('Person', [dict(key=p) for p in sorted(people)])
ing.nodes('Sig', [dict(key=s) for s in sorted(sigs)])
ing.nodes('OwnersFile', [dict(key=k, path=k) for k in sorted(owners)])
print(f"nodes created: {time.perf_counter()-t0:.2f}s")

# ---- edges: KEP lineage (the transitive-closure substrate)
t0=time.perf_counter()
dirs=set(keps); bynum={str(d.get('kep-number')):rel for rel,d in keps.items() if d.get('kep-number') is not None}
PLACE={'n/a','na','tbd','none','-','','null','todo'}
def resolve(s):
    s=s.strip()
    if s.lower().strip('.,;') in PLACE: return None,'placeholder'
    if s.startswith('http'): return None,'external'
    if s.startswith('[') and '](' in s: return None,'external'
    t2=re.sub(r'^/?keps/','',s).strip('/')
    if t2 in dirs: return t2,'ok'
    m=re.search(r'(\d{3,4})',t2)
    if m and m.group(1) in bynum: return bynum[m.group(1)],'ok'
    return None,'broken'

lineage=[]; broken=[]; cat=collections.Counter()
REL={'replaces':'REPLACES','superseded-by':'SUPERSEDED_BY','see-also':'SEE_ALSO'}
for rel,d in keps.items():
    for field,rtype in REL.items():
        v=d.get(field)
        if isinstance(v,str): v=[v]
        for t in (v or []):
            if not isinstance(t,str): continue
            tgt,why=resolve(t)
            cat[why]+=1
            if tgt: lineage.append((rel,tgt,rtype))
            elif why=='broken': broken.append((rel,field,t.strip()))

for rtype in set(REL.values()):
    pairs=[(a,b) for a,b,r in lineage if r==rtype]
    n,sk=ing.edges('Kep', rtype, 'Kep', pairs)
print(f"lineage edges: {time.perf_counter()-t0:.2f}s  resolved={len(lineage)}  broken={len(broken)}  {dict(cat)}")

# ---- the LATENT NODE: a broken lineage target as a first-class node
t0=time.perf_counter()
miss=collections.Counter(t for _,_,t in broken)
ing.nodes('MissingRecord', [dict(key=t, cited_by=n) for t,n in miss.items()])
ing.edges('Kep','CITES_MISSING','MissingRecord', [(src,t) for src,_,t in broken])
print(f"MissingRecord nodes: {len(miss)} in {time.perf_counter()-t0:.2f}s")

# ---- ownership edges
t0=time.perf_counter()
cur=[]; emer=[]
for k,d in owners.items():
    for p in (d.get('approvers') or []):
        if isinstance(p,str) and p.strip(): cur.append((p.strip().lstrip('@').lower(), k))
    for p in (d.get('emeritus_approvers') or []):
        if isinstance(p,str) and p.strip(): emer.append((p.strip().lstrip('@').lower(), k))
ing.edges('Person','APPROVES','OwnersFile',cur)
ing.edges('Person','WAS_APPROVER','OwnersFile',emer)
kp=[]
for rel,d in keps.items():
    for f in ('authors','approvers','reviewers'):
        v=d.get(f)
        if isinstance(v,str): v=[v]
        for p in (v or []):
            if isinstance(p,str) and p.strip().lower() not in ('tbd','n/a','none',''):
                kp.append((p.strip().lstrip('@').lower(), rel))
ing.edges('Person','WORKED_ON','Kep',kp)
ing.edges('Kep','OWNED_BY','Sig',[(rel,str(d['owning-sig'])) for rel,d in keps.items() if d.get('owning-sig')])
print(f"ownership edges: {time.perf_counter()-t0:.2f}s")

print(f"\nTOTAL INGEST: {time.perf_counter()-t_all:.2f}s")
print("\ngraph contents:")
for k,v in sorted(ing.stats().items()): print(f"   {k:<28} {v}")
