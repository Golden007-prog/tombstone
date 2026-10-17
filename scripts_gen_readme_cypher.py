"""Emit the README's Cypher catalogue straight from tools.py, so it cannot drift from what runs."""
import sys, hashlib
sys.path.insert(0, "src")
from tombstone import tools as T

ORDER = [
    ("has_this_been_tried", "HAS_THIS_BEEN_TRIED",
     "Has this idea been proposed and rejected before — and is anyone who made that call still here?",
     "Vector KNN seeds the search, then the graph supplies what no embedding holds: which decision "
     "recorded it, who decided, and whether any of them still approve anything. A vector store alone "
     "returns the k nearest rows and can never return *nothing*."),
    ("has_this_been_tried", "HAS_THIS_BEEN_TRIED_BY_NAME",
     "\u2026and when the question names something a 384-dimension vector cannot keep whole",
     "The other index, over the 206 options the ANN index deliberately excludes. It runs only when "
     "the question contains a name this engine's tokeniser would split, and it is bounded the way "
     "the vector path is bounded by distance: a name matching more than three of those 206 bodies "
     "is not a name, so nothing is reported. The two scopes are disjoint labels, which is what "
     "lets one answer say which index found each row."),
    ("ownership_dilution", "OWNERSHIP_DILUTION",
     "Which areas lost every DEDICATED approver, and which broader group inherits them now?",
     "Kubernetes OWNERS inherit, so finding who actually covers a directory means walking UP the "
     "tree until you hit live approvers — a variable-length traversal. One area falls back two "
     "levels because the directory in between is also dead."),
    ("departed_bridges", "DEPARTED_BRIDGES",
     "Whose departure cost the most CONNECTIVE knowledge — not just the most files?",
     "Betweenness centrality is a whole-graph property. No traversal, no SQL join and no embedding "
     "can compute it. Composed with an ownership traversal in the SAME query."),
    ("successor_for", "SUCCESSOR_FOR",
     "Who already co-owns the areas a departed person left behind?",
     "A co-ownership overlap across two relationship types. In SQL this is two self-joins whose "
     "result still cannot be returned as a path."),
    ("broken_lineage", "BROKEN_LINEAGE",
     "Which cited decision records do not exist?",
     "Inbound edges to a node that stands for something MISSING. Finding it requires resolving "
     "references across 681 decisions and counting arrivals at the gap."),
    ("who_owns", "WHO_OWNS_DEPTH1",
     "Who owns this area? (depth 1 — what any database serves)",
     "A single join. Included deliberately as the control arm of the depth contrast."),
    ("draft_owners_patch", "STEPPED_BACK_BUT_STILL_LISTED",
     "Whose ownership record is lopsided — and can it be safely patched?",
     "The query behind the one ACTION this agent takes. It needs a whole-repository view of one "
     "person's ROLE in 585 separate files: recorded as stepped back in many, still named an "
     "active approver in one. grep finds every file containing the handle; it cannot tell "
     "approver from emeritus from reviewer, and cannot rank by the lopsidedness. The vendored-"
     "tree exclusion is in the query because the strongest-looking candidate in this corpus is "
     "a vendored file that must not be patched."),
    ("who_owns", "WHO_OWNS_DEPTH4",
     "Who owns this area? (depth 4 — what the graph serves)",
     "Four hops: area → the owner who stepped back → decisions they shaped → alternatives "
     "they personally rejected → the SIGs those reached. Returns the reason depth 1 was silent."),
]

print("## The Cypher this product depends on\n")
print("Required by Rule 10. These are generated from `src/tombstone/tools.py` by")
print("`python scripts_gen_readme_cypher.py`, so they are the queries that actually run — not a retelling.")
print("Every one is hand-written and parameterised. **The model never composes a query**; it picks a")
print("tool name and fills its arguments, and no model output is ever concatenated into Cypher.\n")
for tool, attr, question, why in ORDER:
    q = getattr(T.Tools, attr).strip()
    sha = hashlib.sha256(" ".join(q.split()).encode()).hexdigest()[:12]
    print(f"### `{tool}` — {question}")
    print(f"\n*Why a graph:* {why}\n")
    print(f"```cypher\n{q}\n```")
    print(f"`query_sha` = `{sha}` — stamped on every answer this query produces.\n")
