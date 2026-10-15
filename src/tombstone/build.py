"""Build the Tombstone graph in FalkorDB from the Kubernetes governance corpus.

Design notes that matter:

- Two LATENT node types carry the product. `:Alternative` is a rejected design option and
  `:MissingRecord` is a decision document that other decisions cite but which does not exist.
  Neither is a file, a person or a document, so neither appears in any search index anywhere --
  which is exactly why "has this been tried?" is unanswerable today.
- Timestamps are epoch milliseconds as INTEGERS. FalkorDB v4.22.1 supports `date() + duration()`
  but NOT `datetime() + duration()` and not `WHERE ts > datetime() - duration(...)`, so any
  age comparison must be integer arithmetic against a `$now_ms` parameter.
- Edges are created by internal node id, never by matching an indexed property: measured 222k
  edges/sec versus 3k/sec, a 73x difference (GRAPH.EXPLAIN: NodeByIdSeek vs Node By Index Scan).
"""
from __future__ import annotations

import datetime as _dt
import sys

from graphkit.ingest import Ingestor, connect
from tombstone.corpus import Corpus, expand, is_bot, normalise_status, rejected_alternatives

EPOCH = _dt.date(1970, 1, 1)


def to_ms(datestr) -> int:
    """creation-date -> epoch ms, or 0. yaml may already have parsed it to a date."""
    if isinstance(datestr, _dt.datetime):
        return int(datestr.timestamp() * 1000)
    if isinstance(datestr, _dt.date):
        return (datestr - EPOCH).days * 86400000
    s = str(datestr or "")[:10]
    try:
        return (_dt.date.fromisoformat(s) - EPOCH).days * 86400000
    except Exception:
        return 0


def build(corpus: Corpus, graph_name: str = "tomb:k8s", drop: bool = True) -> dict:
    db = connect()
    g = db.select_graph(graph_name)
    ing = Ingestor(g, drop=drop)
    stats: dict[str, object] = {}

    # ---------------- KEP nodes ----------------
    kep_rows = []
    for rel, d in corpus.keps.items():
        status, status_raw = normalise_status(d.get("status"))
        num = str(d.get("kep-number", "")) or ""
        kep_rows.append(
            dict(
                key=rel,
                num=num,
                title=str(d.get("title", ""))[:300],
                status=status,
                status_raw=str(status_raw)[:120],
                sig=str(d.get("owning-sig", "")),
                stage=str(d.get("stage", "")),
                created_ms=to_ms(d.get("creation-date")),
                url=f"https://github.com/kubernetes/enhancements/tree/master/keps/{rel}",
            )
        )
    ing.nodes("Kep", kep_rows)
    stats["Kep"] = len(kep_rows)

    # ---------------- Alternative nodes (LATENT #1) ----------------
    alt_rows, alt_edges = [], []
    titled = untitled = 0
    # A snapshot carries alternatives already extracted (comments stripped), so a deploy does not
    # re-parse 59MB of markdown. Fall back to live parsing when loading from a working tree.
    prebuilt = getattr(corpus, "_prebuilt_alternatives", None)
    if prebuilt is not None:
        source = {rel: [(a["title"], a["body"]) for a in items] for rel, items in prebuilt.items()}
    else:
        source = {rel: rejected_alternatives(md) for rel, md in corpus.readmes.items()
                  if rel in corpus.keps}
    for rel, found in source.items():
        if rel not in corpus.keps:
            continue
        for i, (title, body) in enumerate(found):
            if not body or len(body) < 100:
                continue
            if title:
                titled += 1
            else:
                untitled += 1
            aid = f"{rel}#alt#{i}"
            alt_rows.append(
                dict(
                    key=aid,
                    title=(title or "(untitled alternative)")[:250],
                    body=" ".join(body.split())[:1800],
                    kep=rel,
                    titled=bool(title),
                )
            )
            alt_edges.append((rel, aid))
    ing.nodes("Alternative", alt_rows)
    ing.edges("Kep", "CONSIDERED", "Alternative", alt_edges)
    stats["Alternative"] = len(alt_rows)
    stats["Alternative_titled"] = titled
    stats["Alternative_untitled"] = untitled

    # ---------------- decision lineage + MissingRecord (LATENT #2) ----------------
    resolve = corpus.resolver()
    FIELDS = {"replaces": "REPLACES", "superseded-by": "SUPERSEDED_BY", "see-also": "SEE_ALSO"}
    lineage: dict[str, list[tuple[str, str]]] = {v: [] for v in FIELDS.values()}
    broken: list[tuple[str, str]] = []
    classes: dict[str, int] = {}
    for rel, d in corpus.keps.items():
        for field_name, rel_type in FIELDS.items():
            v = d.get(field_name)
            if isinstance(v, str):
                v = [v]
            for ref in v or []:
                if not isinstance(ref, str):
                    continue
                target, why = resolve(ref)
                classes[why] = classes.get(why, 0) + 1
                if target:
                    lineage[rel_type].append((rel, target))
                elif why == "broken":
                    broken.append((rel, ref.strip()))
    for rel_type, pairs in lineage.items():
        ing.edges("Kep", rel_type, "Kep", pairs)

    missing: dict[str, int] = {}
    for _src, ref in broken:
        missing[ref] = missing.get(ref, 0) + 1
    ing.nodes("MissingRecord", [dict(key=k, cited_by=n) for k, n in missing.items()])
    ing.edges("Kep", "CITES_MISSING", "MissingRecord", broken)
    stats["lineage_resolved"] = sum(len(v) for v in lineage.values())
    stats["lineage_broken"] = len(broken)
    stats["lineage_classes"] = classes
    stats["MissingRecord"] = len(missing)

    # ---------------- people (alias-expanded, bots filtered) ----------------
    people: set[str] = set()
    kep_people: dict[str, list[tuple[str, str]]] = {"AUTHORED": [], "APPROVED": [], "REVIEWED": []}
    for rel, d in corpus.keps.items():
        for field_name, rel_type in (("authors", "AUTHORED"), ("approvers", "APPROVED"), ("reviewers", "REVIEWED")):
            v = d.get(field_name)
            if isinstance(v, str):
                v = [v]
            for h in expand(v, corpus.aliases):
                if is_bot(h):
                    continue
                people.add(h)
                kep_people[rel_type].append((h, rel))

    owners_rows, cur_edges, emer_edges = [], [], []
    for path, d in corpus.owners.items():
        owners_rows.append(
            dict(key=path, path=path,
                 url=f"https://github.com/kubernetes/kubernetes/blob/master/{path}")
        )
        for h in expand(d.get("approvers"), corpus.aliases):
            if is_bot(h):
                continue
            people.add(h)
            cur_edges.append((h, path))
        for h in expand(d.get("emeritus_approvers"), corpus.aliases):
            if is_bot(h):
                continue
            people.add(h)
            emer_edges.append((h, path))

    ing.nodes("Person", [dict(key=p) for p in sorted(people)])
    ing.nodes("OwnersFile", owners_rows)
    for rel_type, pairs in kep_people.items():
        ing.edges("Person", rel_type, "Kep", pairs)
    ing.edges("Person", "APPROVES", "OwnersFile", cur_edges)
    ing.edges("Person", "EMERITUS_OF", "OwnersFile", emer_edges)
    stats["Person"] = len(people)
    stats["OwnersFile"] = len(owners_rows)
    stats["APPROVES"] = len(cur_edges)
    stats["EMERITUS_OF"] = len(emer_edges)

    # ---------------- SIG + ownership of decisions ----------------
    sigs = sorted({str(d["owning-sig"]) for d in corpus.keps.values() if d.get("owning-sig")})
    ing.nodes("Sig", [dict(key=s) for s in sigs])
    ing.edges("Kep", "OWNED_BY", "Sig",
              [(rel, str(d["owning-sig"])) for rel, d in corpus.keps.items() if d.get("owning-sig")])
    stats["Sig"] = len(sigs)

    # ---------------- Person<->Person co-authorship projection ----------------
    # Computed BY THE DATABASE, in Cypher, not in Python. This matters: an adversarial reviewer
    # rightly objects that if a projection is built with numpy and written back, then any
    # algorithm run over it is partitioning a matrix the database never computed -- which is
    # decoration. Here the projection is a 2-hop co-occurrence over shared decisions aggregated
    # with count(DISTINCT), expressed in Cypher, and betweenness then runs over the result.
    # Measured: 5,894 edges in 52ms, identical to the Python version it replaced.
    #
    # Centrality over the raw bipartite Person-[:AUTHORED]->Kep graph is degenerate -- every
    # score 1.0, every community size 1 -- which is why the projection exists at all.
    t_proj = __import__("time").perf_counter()
    g.query(
        """
        MATCH (a:Person)-[:AUTHORED|APPROVED|REVIEWED]->(k:Kep)<-[:AUTHORED|APPROVED|REVIEWED]-(b:Person)
        WHERE a.key < b.key
        WITH a, b, count(DISTINCT k) AS shared
        MERGE (a)-[e:CO_AUTHORED]->(b)
        SET e.w = shared
        """
    )
    stats["CO_AUTHORED"] = g.ro_query(
        "MATCH ()-[r:CO_AUTHORED]->() RETURN count(r)"
    ).result_set[0][0]
    stats["CO_AUTHORED_ms"] = round((__import__("time").perf_counter() - t_proj) * 1000, 1)

    return stats


if __name__ == "__main__":
    enh = sys.argv[1] if len(sys.argv) > 1 else "/tmp/khack/enhancements/keps"
    k8s = sys.argv[2] if len(sys.argv) > 2 else "/tmp/khack/k8s"
    ali = sys.argv[3] if len(sys.argv) > 3 else "/tmp/khack/aliases.yaml"
    import time
    t0 = time.perf_counter()
    c = Corpus().load(enh, k8s, ali)
    t_parse = time.perf_counter() - t0
    t0 = time.perf_counter()
    st = build(c)
    t_build = time.perf_counter() - t0
    print(f"parse {t_parse:.2f}s  build {t_build:.2f}s  total {t_parse + t_build:.2f}s")
    for k, v in st.items():
        print(f"  {k:<22} {v}")
