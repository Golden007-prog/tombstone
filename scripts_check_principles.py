"""Assert that the principles table describes this product, not a product like it.

The README has a table mapping what the organisers said they were looking for to where it is in
this build. Nothing checked a single row of it, and when I audited the twelve rows by hand three
were wrong: one claimed tenant isolation a single-tenant app does not do, one implied every answer
draws a reasoning path when three of fourteen do, and one described name resolution as happening
"with no query run" when the resolution query is exactly what the criterion asks for.

A mapping table is the worst surface to leave unchecked, because the pull when writing one is to
find a row for every criterion, and every individual word can be true while the row as a whole
rounds up. So the numbers are parsed back OUT of the table and asserted against the code: if the
tool count changes, or a chip is added, or a splice creeps into a query constant, this fails rather
than the table quietly becoming a description of something else.
"""
from __future__ import annotations

import re
import sys

sys.path.insert(0, "src")
from tombstone import tools as tools_mod  # noqa: E402
from tombstone.agent import Agent  # noqa: E402

readme = open("README.md").read()
tools_src = open("src/tombstone/tools.py").read()
appjs = open("web/app.js").read()
fails: list[str] = []

# Arguments come from the chips themselves rather than being retyped here. A hand-written copy
# drifted immediately the first time: it said idea="..." where the tool takes idea_text, the tool
# correctly answered "No idea text supplied", and the checker recorded that as a tool with no query
# to check. Reading the real chips means this also proves every chip's arguments still dispatch.
def chip_args() -> dict[str, dict]:
    src = open("web/app.js").read()
    if "const CHIPS = [" not in src:
        raise SystemExit(
            "web/app.js no longer contains `const CHIPS = [`. This parser is "
            "reading the wrong thing, and every check below it would be "
            "measuring a chip set that is not the one the UI ships.")
    i = src.index("const CHIPS = [")
    d = 0
    for n, ch in enumerate(src[i:], i):
        if ch == "[":
            d += 1
        elif ch == "]":
            d -= 1
            if d == 0:
                block = src[i:n + 1]
                break
    out: dict[str, dict] = {}
    for m in re.finditer(r'tool:\s*"(\w+)",\s*args:\s*\{([^}]*)\}', block):
        tool, raw = m.group(1), m.group(2)
        args: dict = {}
        for k, v in re.findall(r'(\w+)\s*:\s*("(?:[^"\\]|\\.)*"|[\d.]+|\[[^\]]*\])', raw):
            if v.startswith('"'):
                # Unescape only when there IS an escape. `.encode().decode("unicode_escape")`
                # turns a literal "…" into "â¦" -- encode gives three UTF-8 bytes and
                # unicode_escape reads each as latin-1. The same line in the demo-facts check
                # reported a chip as missing for exactly that reason. No chip argument carries a
                # non-ASCII character today, so this one is latent rather than wrong, which is
                # the only interesting thing about it: the bug was found elsewhere and this copy
                # would have waited for the first argument with an em dash in it.
                raw_v = v[1:-1]
                args[k] = (raw_v if "\\" not in raw_v else
                           raw_v.encode("latin-1", "backslashreplace").decode("unicode_escape"))
            elif v.startswith("["):
                args[k] = [x.strip().strip('"') for x in v[1:-1].split(",") if x.strip()]
            else:
                args[k] = float(v) if "." in v else int(v)
        out.setdefault(tool, args)
    # Counted against `label:`, which every chip has, rather than against another copy of the
    # same `tool:` pattern -- two runs of one regex agree with each other even when the regex has
    # stopped matching the file.
    if len(re.findall(r'tool:\s*"(\w+)"', block)) != len(re.findall(r"\blabel:", block)):
        raise SystemExit("chip_args(): app.js has chips whose tool this parser cannot read -- "
                         "every check below would be measuring a smaller set than the UI ships")
    return out


SAMPLE_ARGS = chip_args()


def check(label: str, ok: bool, detail: str = "") -> None:
    print(f"  {'PASS' if ok else 'FAIL'}  {label}{(' — ' + detail) if detail else ''}")
    if not ok:
        fails.append(label)


# The table itself. Slice to the next heading rather than between two markers -- a pair of markers
# is one reordering away from slicing backwards, which is how the Cypher-drift check once passed
# on an empty string.
start = readme.find("The organisers published what they are looking for")
assert start > 0, "principles table heading not found in README"
table = readme[start:readme.find("\n## ", start + 10)]
rows = [r for r in table.split("\n") if r.startswith("|") and set(r) - set("|-: ")]
check("the table still has its twelve criteria rows", len(rows) == 13, f"{len(rows) - 1} + header")

body = "\n".join(rows)

# ---------------------------------------------------------------- row: no model writes a query
n_claimed = re.search(r"\*\*?(\d+) tools\*\*?|\b(\d+) tools\b", body)
n_claimed = int(next(g for g in n_claimed.groups() if g)) if n_claimed else -1
registry = Agent(graph_name="tomb:k8s").tools if hasattr(Agent, "tools") else None
n_real = len(re.findall(r'^\s{4}"(\w+)":', tools_src, re.M))
check("the tool count in the table is the tool count in the code",
      n_claimed == n_real, f"table says {n_claimed}, code has {n_real}")

# Every query a hand-written constant. Cypher cannot parameterize a variable-length bound, so a
# depth argument is precisely where a template creeps in -- who_owns answers that by holding two
# separate constants and clamping to one of them.
consts = dict(re.findall(r'^\s{4}([A-Z][A-Z0-9_]*)\s*=\s*"""(.*?)"""', tools_src, re.M | re.S))
# Not "does the constant contain braces" -- Cypher map literals are braces, and that regex failed
# six innocent constants the first time it ran. The claim is that the query the tool RETURNS was
# written by hand, so test exactly that: the text it reports must appear verbatim in the source.
# A query assembled from pieces, or templated, cannot.
sources = "".join(open(f"src/tombstone/{m}.py").read()
                  for m in ("tools", "agent", "memory", "counterfactual"))
check("no query constant is an f-string",
      not re.search(r'^\s{4}[A-Z][A-Z0-9_]*\s*=\s*f"""', tools_src, re.M))
check("no query constant is passed through .format() or %",
      not re.search(r"\b[A-Z][A-Z0-9_]{4,}\s*(\.format\(|%\s)", sources))
check("who_owns holds one constant per depth rather than templating the bound",
      {"WHO_OWNS_DEPTH1", "WHO_OWNS_DEPTH4"} <= set(consts),
      ", ".join(sorted(k for k in consts if k.startswith("WHO_OWNS"))))

# ---------------------------------------------------------------- row: resolve names first
a = Agent(graph_name="tomb:k8s")
unk = a.dispatch("who_owns", {"path": "sig-nonexistent/OWNERS", "depth": 4})
check("an unknown path stops at UNKNOWN_ENTITY", unk.shape == "UNKNOWN_ENTITY", unk.shape)
check("and the traversal never ran -- the cypher field is empty",
      not (unk.cypher or "").strip(), repr((unk.cypher or "")[:40]))
# The row now says a query DOES run, and that it is the resolution query. Assert the resolver is
# a query rather than a Python-side lookup, or the row goes back to being wrong the other way.
check("name resolution is a query against the graph, not an in-process set",
      bool(re.search(r'def resolve_person.*?MATCH \(p:Person', tools_src, re.S))
      and bool(re.search(r'def resolve_path.*?MATCH \(o:OwnersFile', tools_src, re.S)))

# Every answering tool's query, as reported to the user, found verbatim in the source.
answered = 0
skipped: list[str] = []
for name in sorted(re.findall(r'^\s{4}"(\w+)":', tools_src, re.M)):
    try:
        ans = a.dispatch(name, SAMPLE_ARGS.get(name, {}))
    except Exception as e:  # a tool that cannot run here is not evidence either way
        check(f"{name}: dispatched", False, str(e)[:60])
        continue
    cyp = (ans.cypher or "").strip()
    if not cyp:
        # Say which tool was skipped and why. A silent `continue` here would let a tool that
        # stopped producing a query at all pass as "nothing to check".
        print(f"  SKIP  {name} reported no query to check ({ans.shape})")
        skipped.append(f"{name} ({ans.shape})")
        continue
    answered += 1
    check(f"{name}'s query appears verbatim in the source, so it was not assembled",
          cyp.split("\n")[1][:60] in sources if "\n" in cyp else cyp[:60] in sources,
          cyp.split("\n")[0][:50])
check("most tools actually produced a query to check", answered >= 9, f"{answered} returned cypher")
if skipped:
    print(f"  note  {len(skipped)} tool(s) reported no query here: {', '.join(skipped)}")

# ---------------------------------------------------------------- row: the four answer shapes
for shape in ("ANSWERED_WITH_PATH", "ANSWERED_FROM_MEMORY", "NOT_IN_GRAPH", "UNKNOWN_ENTITY"):
    check(f"shape {shape} is named in the table and exists in the code",
          shape in readme and shape in open("src/tombstone/tools.py").read() + open("src/tombstone/agent.py").read())

# ---------------------------------------------------------------- row: the drawn path, 3 of N
m = re.search(r"appears on (\d+) of (\d+) questions", body)
check("the table states the drawn-path count as 'N of M questions'", bool(m), m.group(0) if m else "absent")
if m:
    drawn_claimed, total_claimed = int(m.group(1)), int(m.group(2))
    i = appjs.index("const CHIPS = [")
    depth = 0
    for n, ch in enumerate(appjs[i:], i):
        if ch == "[":
            depth += 1
        elif ch == "]":
            depth -= 1
            if depth == 0:
                chips_src = appjs[i:n + 1]
                break
    chips = re.findall(r"\{\s*label:(.*?)(?=\n  \{|\n\]|$)", chips_src, re.S)
    total = len(re.findall(r"\blabel:", chips_src))
    # A chip draws a path when it carries a graph: focus for the path view to anchor on.
    drawn = [c for c in chips if re.search(r"\bgraph:\s*\{", c)]
    check("the total question count in the table is the number of chips",
          total_claimed == total, f"table says {total_claimed}, app has {total}")
    check("the drawn-path count in the table is the number of chips that draw one",
          drawn_claimed == len(drawn), f"table says {drawn_claimed}, app draws {len(drawn)}")
    named = re.findall(r'tool:\s*"(\w+)"', "".join(drawn))
    check("and they are the questions the table names",
          set(named) == {"who_owns", "successor_for", "what_if_they_go"},
          ", ".join(sorted(set(named))))

# ---------------------------------------------------------------- row: built-in algorithms
claimed_algos = set(re.findall(r"algo\.(\w+)", body))
called_algos = set(re.findall(r"algo\.(\w+)", tools_src + open("src/tombstone/agent.py").read()
                              + open("src/tombstone/counterfactual.py").read()))
check("every algorithm the table names is actually called",
      claimed_algos <= called_algos, f"claimed {sorted(claimed_algos)}, called {sorted(called_algos)}")
if "a vector index" in body or "vector index" in body:
    queried = set(re.findall(r"db\.idx\.vector\.queryNodes\('(\w+)'",
                             tools_src + open("src/tombstone/memory.py").read()))
    check("the vector index is queried, not merely created", len(queried) >= 1, ", ".join(sorted(queried)))
if "GRAPH.COPY" in body:
    check("GRAPH.COPY is executed, not only described",
          "execute_command(\"GRAPH.COPY\"" in open("src/tombstone/counterfactual.py").read())

# ---------------------------------------------------------------- the two rows that say "partly"
hedged = [r for r in rows if "**Partly" in r or "partly" in r]
check("the rows that overstated still carry their hedge", len(hedged) == 2, f"{len(hedged)} hedged rows")
# Tenancy says Partly because the app is single-tenant. If a graph switch ever lands, the hedge is
# wrong in the other direction and the row should be rewritten, so assert the premise.
server_src = open("src/tombstone/server.py").read()
check("the tenancy hedge's premise holds -- no request can switch graphs",
      not re.search(r"graph_name\s*=\s*(c\.|body|req|request|payload)", server_src))

# ---------------------------------------------------------------------------
# The Track 03 "Key focus" table. Its numbers come straight out of the graph, and one of its rows
# is an admission -- docs only, no tickets and no chats. An admission needs checking too: if a
# ticket or chat label ever lands in the graph, that row becomes false by being too modest, and a
# judge reading it would be misled about what they are looking at.
start2 = readme.find('Track 03\'s own "Key focus"')
assert start2 > 0, "Track 03 table not found"
track = readme[start2:readme.find("\n## ", start2 + 10)]

for quoted in ("Knowledge from docs, tickets, and chats in one graph",
               "Who owns what, and who knows what",
               "Tracing decisions back to their source",
               "Keeping knowledge current as things change",
               "Answers with clear sources"):
    check(f'the track bullet "{quoted[:38]}..." is quoted verbatim', quoted in track)

g = a.tools.g


def scalar(q: str) -> int:
    rs = g.query(q).result_set
    return int(rs[0][0]) if rs else 0


labels = {r[0] for r in g.query("CALL db.labels()").result_set}
check("no ticket or chat data is in the graph, as the first row admits",
      not {l for l in labels if re.search(r"ticket|chat|message|issue|slack|email", l, re.I)},
      ", ".join(sorted(labels)))

for pattern, query, label in (
    (r"\*\*(\d+) of (\d+)\*\* decision records carry their source URL",
     None, "source-url coverage"),
    (r"\*\*(\d+) of the \d+ people\*\* carry expertise edges",
     "MATCH (p:Person)-[:AUTHORED|APPROVED|REVIEWED]->(:Kep) RETURN count(DISTINCT p)",
     "people with expertise edges"),
    (r"\*\*(\d+) people are listed as emeritus somewhere and hold no current approval",
     "MATCH (p:Person)-[:EMERITUS_OF]->(:OwnersFile) WHERE NOT (p)-[:APPROVES]->() "
     "RETURN count(DISTINCT p)", "emeritus-only people"),
    (r"(\d+) `REPLACES`/`SUPERSEDED_BY` edges",
     "MATCH ()-[r:REPLACES|SUPERSEDED_BY]->() RETURN count(r)", "superseding edges"),
    (r"\*\*(\d+) records cited by name that do not exist\*\*",
     "MATCH (m:MissingRecord) RETURN count(m)", "missing records"),
):
    m2 = re.search(pattern, track)
    if not m2:
        check(f"the table states {label}", False, "pattern not found")
        continue
    if query is None:                      # "N of M" -- both halves, and they must be equal
        have, total = int(m2.group(1)), int(m2.group(2))
        live_have = scalar("MATCH (k:Kep) WHERE k.url IS NOT NULL AND k.url <> '' RETURN count(k)")
        live_total = scalar("MATCH (k:Kep) RETURN count(k)")
        check("every decision record carries a source URL, as claimed",
              (have, total) == (live_have, live_total) and live_have == live_total,
              f"table says {have} of {total}, graph has {live_have} of {live_total}")
    else:
        live = scalar(query)
        check(f"{label} in the table matches the graph", int(m2.group(1)) == live,
              f"table says {m2.group(1)}, graph has {live}")

print()
if fails:
    print(f"{len(fails)} row(s) in the principles table do not describe this build:")
    for f in fails:
        print(f"  - {f}")
    sys.exit(1)
print("Every checkable statement in the principles table matches the code.")
