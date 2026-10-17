"""The README's data-model block lists everything the live graph has.

Rule 10 asks for the graph data model. The README's block is that deliverable, and an end-to-end
audit on 17 Oct found it missing two labels (`:UnnamedOption`, added that morning with the
full-text index; `:Answer`, the memory feature's own node), two relationship types (`INHERITS_FROM`
and `CITED`) and four of the eight indexes. `INHERITS_FROM` is the one that mattered: it is the
OWNERS tree, and `who_owns` at depth 4, `ownership_dilution` and every "who would inherit this"
answer in the README walk it. The Rule 10 deliverable omitted the edge the headline traversal uses.

It drifted for a structural reason worth naming: the sibling table in `docs/EXPLAIN-IT.md` is
re-derived from the live graph by `./preflight.sh`, and this block was prose nobody re-derived. One
copy checked, one copy not, is this repository's most frequent defect, and it does not stop being
that just because the unchecked copy is the one a judge is required to read.

So this checks the direction that matters: anything the GRAPH has, the BLOCK must name. The reverse
is deliberately not an error -- the block names `(:Answer)` and its two indexes, which do not exist
until the first question is answered, and a graph seeded one second ago legitimately lacks them.

    PYTHONPATH=src python3 scripts_check_data_model.py
    PYTHONPATH=src python3 scripts_check_data_model.py --self-test

Needs a live FalkorDB, so it runs in `./preflight.sh` and in CI's database-backed job, not in the
push gate.
"""
from __future__ import annotations

import pathlib
import re
import sys

README = pathlib.Path("README.md")


def block() -> str:
    """The fenced block under '## The graph data model'. Its absence is a failure, not a skip:
    a checker that silently finds nothing to check is how the last two audits passed over
    an empty set."""
    text = README.read_text(encoding="utf-8")
    # Between the fences, not up to the first one. The first version of this captured the prose
    # ABOVE the opening fence and reported all 33 declarations missing -- a checker so broken it
    # failed loudly, which is the only reason it was not mistaken for a real finding. Its own
    # --self-test caught it: "the mutation changed nothing, so this case proves nothing".
    m = re.search(r"^## The graph data model\s*\n.*?^```\s*\n(.*?)^```\s*$", text, re.S | re.M)
    if not m:
        sys.exit("FAIL  cannot find the fenced data-model block under '## The graph data model' "
                 "in README.md -- fix this checker rather than deleting it")
    return m.group(1)


def live() -> tuple[set[str], set[str], set[str]]:
    from graphkit.ingest import connect
    g = connect().select_graph("tomb:k8s")
    labels = {r[0] for r in g.ro_query("CALL db.labels()").result_set}
    rels = {r[0] for r in g.ro_query("CALL db.relationshipTypes()").result_set}
    # One row per label, each carrying every indexed property on it.
    indexes = set()
    for row in g.ro_query("CALL db.indexes()").result_set:
        label, props = row[0], row[1]
        for p in props:
            indexes.add(f"{label}.{p}")
    return labels, rels, indexes


def check(body: str, labels: set[str], rels: set[str], indexes: set[str]) -> list[str]:
    problems = []
    for label in sorted(labels):
        # `:Label` or `(:Label` -- the block writes both, and a bare word is not enough: "Person"
        # appears in prose, `:Person` is a declaration.
        if not re.search(rf"[(:]:?{re.escape(label)}\b", body):
            problems.append(f"the live graph has a (:{label}) and the block does not name it")
    for rel in sorted(rels):
        if f":{rel}" not in body:
            problems.append(f"the live graph has a [:{rel}] and the block does not name it")
    for idx in sorted(indexes):
        label, prop = idx.split(".", 1)
        # An index is named by its label AND its property appearing together in one line, because
        # `(a:NamedOption) ON (a.emb)` and `(:Answer).emb` are both legitimate spellings and
        # matching them separately would pass on any block that happens to mention both somewhere.
        if not any(re.search(rf"{re.escape(label)}\b.*\b{re.escape(prop)}\b", line)
                   for line in body.splitlines()):
            problems.append(f"the live graph indexes {idx} and the block does not list it")
    return problems


def main() -> int:
    body = block()
    labels, rels, indexes = live()
    problems = check(body, labels, rels, indexes)
    if problems:
        for p in problems:
            print(f"  FAIL  {p}")
        print("        Rule 10 asks for the data model; this block IS that deliverable.")
        return 1
    print(f"  ok    the README's data-model block names all {len(labels)} labels, "
          f"{len(rels)} relationship types and {len(indexes)} indexes the live graph has")
    return 0


def self_test() -> int:
    """Prove it can fail. Each case is the real block with one declaration removed."""
    body = block()
    labels, rels, indexes = live()
    cases = [
        ("a label", re.sub(r":UnnamedOption", ":Redacted", body)),
        ("a relationship type", body.replace(":INHERITS_FROM", ":REDACTED")),
        ("an index", re.sub(r"FOR \(a:UnnamedOption\) ON \(a\.body\)", "FOR (x:Y) ON (x.z)", body)),
    ]
    bad = []
    for what, mutated in cases:
        if mutated == body:
            bad.append(f"{what}: the mutation changed nothing, so this case proves nothing")
        elif not check(mutated, labels, rels, indexes):
            bad.append(f"{what}: removed from the block and the check still passed")
    if check(body, labels, rels, indexes):
        bad.append("false positive: the real block does not pass")
    for b in bad:
        print(f"  FAIL  {b}")
    if bad:
        return 1
    print(f"  ok    all {len(cases)} removals caught, and the real block passes")
    return 0


if __name__ == "__main__":
    raise SystemExit(self_test() if "--self-test" in sys.argv else main())
