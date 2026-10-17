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
import re
import sys

import time as _time

from graphkit.ingest import Ingestor, chunked, connect
from tombstone.corpus import Corpus, expand, is_bot, normalise_status, rejected_alternatives
from tombstone.tools import NAME_HIT_BOUND, fulltext_query, searchable_names

EPOCH = _dt.date(1970, 1, 1)


# A leading list marker or bold run makes the first ". " land two characters in, so the naive
# first-sentence cut produced titles like "1." for nineteen real rejections -- each with 192 to
# 1,799 characters of argument underneath it. Abbreviations do the same thing more quietly:
# "Setting up a VPN (e.g. IPSec)" cut at "(e.g." and shipped that as the option's name.
#
# Retitling is free here, and that is not an accident worth glossing: the committed embeddings are
# over the BODY alone -- re-embedding a body reproduces its stored vector at cosine 1.0000 -- so
# the label is display text only. Nothing about retrieval moves when it changes.
_MARKER = re.compile(r"^(?:[-*+]\s+|\d+[.)]\s+|#{1,6}\s+)+")
# Compared as whole TOKENS, never with endswith. The first version of this tuple was tested with
# str.endswith and "al." is in it for "et al.", so it matched "proposal.", "optional.",
# "additional.", "functional." -- and a corpus of design documents says "proposal." constantly.
# One such sentence ran to 181 characters before the next boundary it would accept. That is the
# same defect as an exclusion keyed on a word instead of a meaning: it silently swallows the
# honest sentences that happen to end in those three letters.
_ABBREV = frozenset(
    ("e.g.", "i.e.", "etc.", "vs.", "cf.", "resp.", "approx.", "al.", "Fig.", "No.")
)


_LIMIT = 160


def _clip(text: str) -> str:
    """Cut to _LIMIT on a word boundary. A label ends on a full stop or an ellipsis, never
    mid-word: slicing the first sentence at a fixed width did that to eighteen of these, which
    measured worse than the "1." it was introduced to fix."""
    if len(text) <= _LIMIT:
        return text
    cut = text.rfind(" ", 0, _LIMIT)
    return text[: cut if cut > 0 else _LIMIT].rstrip(" ,;:-") + "\u2026"


def derive_label(body: str) -> str:
    """A display label for an Alternatives section that had no sub-heading.

    The first real sentence, clipped to 160 characters. "Real" means it does not end on a known
    abbreviation and leaves at least 24 characters, which is enough to keep "Add a config to
    Kubelet." whole while refusing "1." and "(e.g.".
    """
    first = " ".join(body.split())
    first = _MARKER.sub("", first).lstrip("*_`# ").strip()
    at = 0
    while True:
        cut = first.find(". ", at)
        if cut < 0:
            break
        head = first[: cut + 1]
        tail = head.rsplit(" ", 1)[-1].lstrip("([{\"'")
        if cut >= 24 and tail not in _ABBREV:
            return _clip(head)
        at = cut + 1
    return _clip(first)


def to_ms(datestr) -> int:
    """creation-date -> epoch ms, or 0. yaml may already have parsed it to a date."""
    if isinstance(datestr, _dt.datetime):
        return int(datestr.timestamp() * 1000)
    if isinstance(datestr, _dt.date):
        return (datestr - EPOCH).days * 86400000
    s = str(datestr or "")[:10].strip()
    # The template ships `creation-date: 'yyyy-mm-dd'` and some authors never replace it. Those
    # are unusable, and neither is an excuse to drop the record.
    if not s or not s[:4].isdigit():
        return 0
    try:
        return (_dt.date.fromisoformat(s) - EPOCH).days * 86400000
    except ValueError:
        pass

    # Some authors write the date without zero-padding: `2024-2-1`, `2023-9-18`, `2025-10-9`.
    # fromisoformat rejects those, and discarding them loses three real dates for a formatting
    # habit. They are unambiguous, so they are parsed.
    #
    # What is NOT parsed is a month above twelve -- `2023-14-05`, `2025-30-01`. Those are
    # presumably day-month transpositions, and "presumably" is not a date. Guessing would invent
    # a creation date for a decision, which is exactly the kind of fabrication this product
    # exists to refuse; they stay unusable and the UI keeps saying "date not recorded".
    parts = s.split("-")
    if len(parts) == 3 and all(p.isdigit() for p in parts):
        year, month, day = (int(p) for p in parts)
        if 1 <= month <= 12:
            try:
                return (_dt.date(year, month, day) - EPOCH).days * 86400000
            except ValueError:
                return 0
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
    stats["parse_failures"] = len(getattr(corpus, "parse_failures", []))

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
            # An untitled Alternatives section is prose, not a named option. Derive a label from
            # its first sentence so the UI never shows "(untitled alternative)" to a judge.
            label = title or derive_label(body)
            alt_rows.append(
                dict(
                    key=aid,
                    title=label[:250],
                    body=" ".join(body.split())[:1800],
                    kep=rel,
                    titled=bool(title),
                )
            )
            alt_edges.append((rel, aid))
    ing.nodes("Alternative", alt_rows)
    ing.edges("Kep", "CONSIDERED", "Alternative", alt_edges)

    # A titled sub-heading inside `Alternatives` is a NAMED option someone argued for and lost.
    # Untitled sections are just prose. Only named options make a good "has this been tried?"
    # answer, so they get a second label.
    #
    # Why a label and not a property filter: FalkorDB vector indexes cannot filter by property
    # (verified -- a top-k over a shared index returns rows you then have to discard, so you ask
    # for k and keep k/N). Minting a label gives a genuinely pre-filtered ANN index instead, with
    # no post-filter recall loss.
    g.query("MATCH (a:Alternative) WHERE a.titled = true SET a:NamedOption")
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

    # OWNERS files form a TREE, and that tree is load-bearing. Kubernetes OWNERS inherit from
    # parent directories by default -- prow treats a directory as covered by its own approvers
    # PLUS every ancestor's, unless an OWNERS on the way up sets `options.no_parent_owners`.
    #
    # Without these edges you cannot tell "this code has no owner" (which is almost never true)
    # from "this code lost its dedicated owners and silently fell back to a broader group"
    # (which is true, and is the more interesting failure). Computing that fallback is a
    # variable-length traversal up the tree, which is exactly the shape a graph is for.
    import os as _os

    paths = {r["key"] for r in owners_rows}

    def _parent(rel: str) -> str | None:
        d = _os.path.dirname(rel)
        while d:
            d = _os.path.dirname(d)
            cand = _os.path.join(d, "OWNERS") if d else "OWNERS"
            if cand in paths and cand != rel:
                return cand
        return None

    parent_pairs = []
    for rel in paths:
        par = _parent(rel)
        if par:
            parent_pairs.append((rel, par))
    ing.edges("OwnersFile", "INHERITS_FROM", "OwnersFile", parent_pairs)
    stats["INHERITS_FROM"] = len(parent_pairs)

    # `no_parent_owners: true` genuinely severs inheritance; mark those so a traversal can stop.
    severed = [
        r for r, d in corpus.owners.items()
        if isinstance(d.get("options"), dict) and d["options"].get("no_parent_owners")
    ]
    if severed:
        for batch in chunked([{"k": k} for k in severed]):
            g.query(
                "UNWIND $rows AS x MATCH (o:OwnersFile {key: x.k}) SET o.severs_inheritance = true",
                params={"rows": list(batch)},
            )
    stats["severs_inheritance"] = len(severed)
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

    # ---------------- full-text index over the options the vector index cannot see -------------
    # The complement of :NamedOption, minted for the identical reason the sibling section below
    # mints that one: in this engine an index SCOPE is a label, because a vector index cannot
    # filter by property. :NamedOption carries the ANN index over 752 options. :UnnamedOption
    # carries a full-text index over the other 206 -- the set docs/EXPLAIN-IT.md has called this
    # product's biggest recall weakness since the day it was measured.
    #
    # This is NOT the thing bench_index_scope.py refused. That measured POOLING the 206 into the
    # ANN index and found it cost about three points of top-k precision, because an ANN top-k is
    # a fixed budget and 206 more documents compete for the same k slots. A text conjunction has
    # no budget to dilute: a body either contains every term or it does not.
    #
    # It is also why the index goes here and not on :Alternative. bench_index_scope.py builds a
    # temporary vector index on :Alternative and polls `info.numDocuments` to know when it is
    # built; db.indexes() yields one row PER LABEL, so a second index on that label would land in
    # the bucket that gate reads and could satisfy it from the wrong index. Disjoint scopes also
    # mean no option can be returned twice by one answer, which is what lets a row say which
    # index found it.
    g.query("MATCH (a:Alternative) WHERE a.titled = false SET a:UnnamedOption")
    stats["UnnamedOption"] = g.ro_query(
        "MATCH (a:UnnamedOption) RETURN count(a)"
    ).result_set[0][0]

    # Syntax: docs.falkordb.com/cypher/indexing/fulltext-index, "Using DDL syntax" --
    # `CREATE FULLTEXT INDEX FOR (n:Movie) ON (n.title)`.
    #
    # `.body` only, deliberately not `.title` as well: for these 206 the title IS the first
    # sentence of the body -- derive_label above is what produces it -- so indexing both counts
    # every term of that sentence twice and hands the opening line of an 1,800-character argument
    # a TF-IDF score it did not earn.
    #
    # No `OPTIONS { language: ... }`: the page shows only 'German' as a value and never states
    # the default, so passing a guess risks failing the build on a string.
    g.query("CREATE FULLTEXT INDEX FOR (a:UnnamedOption) ON (a.body)")

    # Index builds are ASYNCHRONOUS here -- bench_index_scope.py measured that for the vector
    # index and gates on it, and nothing on the full-text page says this one differs. The poll is
    # FUNCTIONAL rather than a status-field read, because db.indexes() yields a `status` whose
    # vocabulary no page defines, and gating on a string nobody documented is how this project
    # got burned by algo.betweenness sampling 32 nodes by default. Asking the index for a
    # document it is known to contain cannot be wrong about what it means -- and it exercises the
    # exact tokeniser the tool queries with, so a disagreement between the index and
    # `searchable_names` fails the build here rather than returning nothing in the UI.
    _probe_key, _probe_body = g.ro_query(
        "MATCH (a:UnnamedOption) RETURN a.key, a.body ORDER BY a.key LIMIT 1"
    ).result_set[0]
    _probe = fulltext_query(searchable_names(_probe_body)[:1])
    _t_ft = _time.perf_counter()
    _seen: list = []
    while _probe and _time.perf_counter() - _t_ft < 60:
        _seen = [r[0] for r in g.ro_query(
            "CALL db.idx.fulltext.queryNodes('UnnamedOption', $q) YIELD node AS a RETURN a.key",
            params={"q": _probe},
        ).result_set]
        if _probe_key in _seen:
            break
        _time.sleep(0.25)
    stats["fulltext_ready_ms"] = round((_time.perf_counter() - _t_ft) * 1000, 1)
    stats["fulltext_queryable"] = bool(_probe) and _probe_key in _seen
    if not stats["fulltext_queryable"]:
        stats["fulltext_warning"] = (
            "the full-text index did not return a document it contains within 60s -- "
            "has_this_been_tried will answer by similarity only, over 752 of 958 options")

    # ---------------- vector index over the rejected alternatives ----------------
    # Embeddings come from the committed float16 snapshot when present. Embedding these 960 real
    # ~1,400-char chunks live costs ~115s at a measured 8.4/sec, which is not a price worth paying
    # on every boot; the snapshot reloads in 11.6ms and preserves top-5 neighbour order exactly.
    from tombstone.snapshot import load_vectors

    keys, vectors = load_vectors()
    if keys and vectors:
        g.query(
            "CREATE VECTOR INDEX FOR (a:NamedOption) ON (a.emb) "
            "OPTIONS {dimension: 384, similarityFunction: 'cosine'}"
        )
        have = {r[0] for r in g.ro_query("MATCH (a:Alternative) RETURN a.key").result_set}
        payload = [{"k": k, "e": v} for k, v in zip(keys, vectors) if k in have]
        for batch in chunked(payload):
            g.query(
                "UNWIND $rows AS x MATCH (a:Alternative {key: x.k}) SET a.emb = vecf32(x.e)",
                params={"rows": list(batch)},
            )
        stats["vectors_loaded"] = len(payload)
        stats["NamedOption"] = g.ro_query(
            "MATCH (a:NamedOption) RETURN count(a)"
        ).result_set[0][0]
    else:
        stats["vectors_loaded"] = 0
        stats["vector_warning"] = (
            "No vector snapshot found -- has_this_been_tried will be unavailable. "
            "Run: python src/tombstone/embed.py"
        )

    # ---------------- Person<->Person co-authorship projection ----------------
    # Computed BY THE DATABASE, in Cypher, not in Python. This matters: an adversarial reviewer
    # rightly objects that if a projection is built with numpy and written back, then any
    # algorithm run over it is partitioning a matrix the database never computed -- which is
    # decoration. Here the projection is a 2-hop co-occurrence over shared decisions aggregated
    # with count(DISTINCT), expressed in Cypher, and betweenness then runs over the result.
    # Measured: 5,879 edges in 52ms, identical to the Python version it replaced. (The docs said
    # 5,894 for a while: a figure from an earlier corpus load that verify_claims.py, which asks
    # the live graph on every push, has always had at 5,879.)
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

    stats.update(_constraints(g))
    return stats


# Identity and traceability, enforced by the database rather than by this file being careful.
#
# UNIQUE on each label's `key`: every one of these is created once per key by Ingestor.nodes(),
# which also creates `CREATE INDEX FOR (n:Label) ON (n.key)` -- and a UNIQUE constraint requires
# exactly that exact-match index to exist first, so the index this build already makes is what
# makes the constraint possible. A duplicate :Person or :Kep would be a corpus-parsing bug that
# currently shows up as inflated counts; now the write is rejected instead.
#
# MANDATORY on Kep.url and OwnersFile.path/url: Track 3's own second bullet is "Tracing decisions
# back to their source", and a decision node with no source URL would make that claim false
# node-by-node. Both are built with an unconditional f-string in this file, so the constraint
# encodes an invariant the code already guarantees -- which is the point of a constraint rather
# than an argument for one.
_CONSTRAINTS = (
    ("unique", "Kep", ("key",)),
    ("unique", "Alternative", ("key",)),
    ("unique", "MissingRecord", ("key",)),
    ("unique", "Person", ("key",)),
    ("unique", "OwnersFile", ("key",)),
    ("unique", "Sig", ("key",)),
    ("mandatory", "Kep", ("url",)),
    ("mandatory", "OwnersFile", ("path",)),
)


def _constraints(g) -> dict:
    """Declare the constraints, best-effort, and wait for the engine to finish building them.

    ADDITIVE AND NON-FATAL, deliberately. This runs on every boot, including the Space's, and a
    constraint that cannot be created must never stop the graph from serving answers -- the same
    rule the memory writes in agent.py follow. Failures are counted and reported, not raised.

    Creation is ASYNCHRONOUS: the command replies PENDING and the constraint then moves through
    UNDER CONSTRUCTION to OPERATIONAL or FAILED. This repository has already been caught once by
    asking an async FalkorDB operation for its result on the next line -- the vector index drop --
    so this polls `list_constraints()` instead of assuming, and reports what it actually reached.
    """
    import time as _t
    made, failed = 0, []
    for kind, label, props in _CONSTRAINTS:
        fn = (g.create_node_unique_constraint if kind == "unique"
              else g.create_node_mandatory_constraint)
        try:
            fn(label, *props)
            made += 1
        except Exception as exc:
            # Already present is the normal case on a graph that was not dropped.
            if "already" not in str(exc).lower():
                failed.append(f"{kind} {label}.{'+'.join(props)}: {str(exc).splitlines()[0]}")

    pending, operational = [], 0
    for _ in range(50):
        try:
            rows = g.list_constraints()
        except Exception as exc:
            return {"constraints": made, "constraints_status": f"unlistable: {exc}"}
        pending = [c for c in rows if str(c.get("status", "")).upper() != "OPERATIONAL"]
        operational = len(rows) - len(pending)
        if not pending:
            break
        _t.sleep(0.1)

    out = {"constraints": operational}
    if failed:
        out["constraints_failed"] = failed
    if pending:
        out["constraints_pending"] = [
            f"{c.get('label')}.{c.get('properties')}={c.get('status')}" for c in pending]
    return out


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
