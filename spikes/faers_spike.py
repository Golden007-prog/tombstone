"""Can we detect prescribing cascades in real FAERS data? Pull, shape, and look for paths."""
import json, urllib.request, urllib.parse, time, collections, sys

BASE = "https://api.fda.gov/drug/event.json"
def fetch(search, limit=100, skip=0):
    q = urllib.parse.urlencode({'search': search, 'limit': limit, 'skip': skip})
    for attempt in range(3):
        try:
            with urllib.request.urlopen(f"{BASE}?{q}", timeout=30) as r:
                return json.loads(r.read())
        except Exception as e:
            if attempt == 2: raise
            time.sleep(2)

# Pull reports for a well-known cascade starter: amlodipine (CCB) -> peripheral oedema -> furosemide (diuretic)
SEEDS = ["amlodipine", "donepezil", "risperidone", "hydrochlorothiazide"]
reports = []
for s in SEEDS:
    for skip in (0, 100):
        try:
            d = fetch(f'patient.drug.medicinalproduct:"{s}"', limit=100, skip=skip)
            reports.extend(d.get('results', []))
            print(f"  {s} skip={skip}: +{len(d.get('results',[]))} (total matching {d['meta']['results']['total']:,})", flush=True)
        except Exception as e:
            print(f"  {s} skip={skip}: ERR {str(e)[:60]}")
        time.sleep(0.4)

print(f"\npulled {len(reports)} real FAERS reports")

def norm(s):
    return (s or '').strip().upper().rstrip('.').split('(')[0].strip()

# Shape: which (drug, reaction) pairs co-occur, and which drugs co-occur with each other
drug_reaction = collections.Counter()
drug_pairs = collections.Counter()
drug_indication = collections.Counter()
reaction_count = collections.Counter()
drug_count = collections.Counter()

for r in reports:
    p = r.get('patient', {}) or {}
    drugs = [norm(d.get('medicinalproduct')) for d in (p.get('drug') or [])]
    drugs = [d for d in drugs if d]
    rxns  = [norm(x.get('reactionmeddrapt')) for x in (p.get('reaction') or [])]
    rxns  = [x for x in rxns if x]
    for d in set(drugs): drug_count[d]+=1
    for x in set(rxns): reaction_count[x]+=1
    for d in set(drugs):
        for x in set(rxns): drug_reaction[(d,x)] += 1
    ds = sorted(set(drugs))
    for i in range(len(ds)):
        for j in range(i+1, len(ds)):
            drug_pairs[(ds[i], ds[j])] += 1
    for d in (p.get('drug') or []):
        dn, ind = norm(d.get('medicinalproduct')), norm(d.get('drugindication'))
        if dn and ind: drug_indication[(dn, ind)] += 1

print(f"\ndistinct drugs: {len(drug_count)}   distinct reactions: {len(reaction_count)}")
print(f"drug-reaction edges: {len(drug_reaction)}   drug-codrug edges: {len(drug_pairs)}   drug-indication edges: {len(drug_indication)}")

print("\n--- top drug->reaction edges ---")
for (d,x),n in drug_reaction.most_common(8): print(f"  {n:>4}  {d[:28]:<28} -> {x[:40]}")

print("\n--- THE CASCADE SIGNAL: a reaction that is ALSO an indication for another drug ---")
# cascade = drug A causes reaction R, and R is the documented indication for drug B
inds = collections.Counter()
for (d,ind),n in drug_indication.items(): inds[ind]+=n
cascades = []
for (dA, rxn), nA in drug_reaction.items():
    if rxn in inds:           # the adverse event of A is the treatment reason for something
        for (dB, ind), nB in drug_indication.items():
            if ind == rxn and dB != dA:
                cascades.append((nA, nB, dA, rxn, dB))
cascades.sort(reverse=True)
print(f"  found {len(cascades)} candidate 2-hop cascade paths (A -causes-> R <-treats- B)")
for nA,nB,dA,rxn,dB in cascades[:12]:
    print(f"   {dA[:22]:<22} --causes({nA:>3})--> {rxn[:26]:<26} <--treats({nB:>3})-- {dB[:22]}")

print("\n--- PROOF-BY-ABSENCE candidate: drug pairs that NEVER co-occur ---")
top = [d for d,_ in drug_count.most_common(12)]
absent = [(a,b) for i,a in enumerate(top) for b in top[i+1:] if drug_pairs[(min(a,b),max(a,b))]==0]
print(f"  of {len(top)*(len(top)-1)//2} top-drug pairs, {len(absent)} have ZERO co-prescription reports:")
for a,b in absent[:6]: print(f"   {a[:26]:<26} <-X-> {b[:26]}")

json.dump({'reports': len(reports),
           'drug_reaction': [[k[0],k[1],v] for k,v in drug_reaction.most_common(4000)],
           'drug_pairs': [[k[0],k[1],v] for k,v in drug_pairs.most_common(4000)],
           'drug_indication': [[k[0],k[1],v] for k,v in drug_indication.most_common(4000)]},
          open(f"{__import__('os').path.dirname(__file__)}/faers_sample.json","w"))
print(f"\nsaved faers_sample.json")
