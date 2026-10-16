"""Re-check every factual claim in the README against the live graph.

Run: PYTHONPATH=src python verify_claims.py
A judge should be able to falsify any number in this repo in one command.
"""
import datetime
import os
import sys
import time

sys.path.insert(0, "src")

# Claims about age must be checked against a real clock, or they quietly stop being falsifiable.
# AS_OF lets a judge pin the same instant the README used; unset, it is simply now.
AS_OF_MS = int(os.environ.get("AS_OF_MS") or time.time() * 1000)
THREE_YEARS_MS = 3 * 31_557_600_000
from graphkit.ingest import connect

g = connect().select_graph("tomb:k8s")
def one(q, p=None):
    return g.ro_query(q, params={"now": AS_OF_MS, "age": THREE_YEARS_MS, **(p or {})}).result_set[0][0]

CLAIMS = [
    ("decisions (:Kep)", "MATCH (k:Kep) RETURN count(k)", 681),
    # Named-person claims the README makes in PROSE. Every number inside a fenced block was
    # already checked; these were not, and that is where the one factual error about a person
    # lived -- the README had lavalamp top of the betweenness ranking when he is third.
    ("pkg/controller live approvers (podgc falls back to these)",
     "MATCH (:OwnersFile {path:'pkg/controller/OWNERS'})<-[:APPROVES]-(p:Person) "
     "RETURN count(DISTINCT p)", 10),
    ("podgc's own current approvers — the point is that it is zero",
     "MATCH (:OwnersFile {path:'pkg/controller/podgc/OWNERS'})<-[:APPROVES]-(p:Person) "
     "RETURN count(DISTINCT p)", 0),
    ("podgc owners who stepped back",
     "MATCH (:OwnersFile {path:'pkg/controller/podgc/OWNERS'})<-[:EMERITUS_OF]-(p:Person) "
     "RETURN count(DISTINCT p)", 2),
    ("vishh: areas left behind",
     "MATCH (p:Person {key:'vishh'})-[:EMERITUS_OF]->(o) RETURN count(o)", 14),
    ("apelisse: areas held alone",
     "MATCH (o:OwnersFile)<-[:APPROVES]-(p:Person) "
     "WITH o, collect(DISTINCT p.key) AS ap WHERE size(ap) = 1 AND ap[0] = 'apelisse' "
     "RETURN count(o)", 6),
    ("rejected alternatives", "MATCH (a:Alternative) RETURN count(a)", 958),
    ("titled named options", "MATCH (a:NamedOption) RETURN count(a)", 752),
    ("missing decision records", "MATCH (m:MissingRecord) RETURN count(m)", 47),
    ("citations of missing records", "MATCH ()-[r:CITES_MISSING]->() RETURN count(r)", 55),
    ("people", "MATCH (p:Person) RETURN count(p)", 794),
    ("ownership files", "MATCH (o:OwnersFile) RETURN count(o)", 585),
    ("APPROVES edges", "MATCH ()-[r:APPROVES]->() RETURN count(r)", 2584),
    ("EMERITUS_OF edges", "MATCH ()-[r:EMERITUS_OF]->() RETURN count(r)", 298),
    ("CO_AUTHORED edges", "MATCH ()-[r:CO_AUTHORED]->() RETURN count(r)", 5879),
    ("lavalamp emeritus files", "MATCH (:Person{key:'lavalamp'})-[:EMERITUS_OF]->(f) RETURN count(f)", 31),
    ("'0006-apply.md' cited by",
     "MATCH (k:Kep)-[:CITES_MISSING]->(:MissingRecord{key:'/keps/sig-api-machinery/0006-apply.md'}) "
     "RETURN count(k)", 4),
    ("areas that lost every dedicated approver",
     "MATCH (d:Person)-[:EMERITUS_OF]->(f:OwnersFile) "
     "OPTIONAL MATCH (c:Person)-[:APPROVES]->(f) "
     "WITH f, count(DISTINCT c) AS n WHERE n = 0 RETURN count(f)", 7),
    ("OWNERS inheritance edges", "MATCH ()-[r:INHERITS_FROM]->() RETURN count(r)", 584),
    # The data-model table in docs/EXPLAIN-IT.md is what a judge gets walked through under Rule
    # 12, and two of its figures were checked nowhere: the Sig count, and the seeded totals the
    # table's own rows are supposed to add up to. A superseded working record still says 23 Sigs,
    # which is what an unchecked number looks like from the outside -- you cannot tell which one
    # is live without running something.
    ("special-interest groups (:Sig)", "MATCH (s:Sig) RETURN count(s)", 22),
    # Rule 6 compliance, asserted rather than described. The README says a Person carries only a
    # handle and that no person-to-SIG edge exists; both are checkable, and the second was wrong
    # in the prose before it was checked -- that paragraph claimed affiliations were ingested.
    ("edges between a person and a SIG — the rules forbid personal data, so there are none",
     "MATCH (:Person)-[r]-(:Sig) RETURN count(r)", 0),
    # The Track 3 table answers "who owns what, and who knows what" with this pair, and nothing
    # checked either half. The gap between 729 and the 585 ownership files IS the answer to that
    # question, so it is the last figure on the page that should go unverified.
    ("people carrying expertise edges to a decision",
     "MATCH (p:Person)-[:AUTHORED|APPROVED|REVIEWED]->(:Kep) RETURN count(DISTINCT p)", 729),
    ("seeded nodes, before the agent writes any memory",
     "MATCH (n) WHERE NOT n:Answer RETURN count(n)", 3087),
    ("seeded edges, before the agent writes any memory",
     "MATCH (a)-[r]->(b) WHERE NOT a:Answer AND NOT b:Answer RETURN count(r)", 15735),
    ("OWNERS files that sever inheritance",
     "MATCH (o:OwnersFile) WHERE o.severs_inheritance = true RETURN count(o)", 57),
    ("areas genuinely unowned after walking the tree",
     "MATCH (d:Person)-[:EMERITUS_OF]->(f:OwnersFile) "
     "OPTIONAL MATCH (own:Person)-[:APPROVES]->(f) "
     "WITH f, count(DISTINCT own) AS n WHERE n = 0 "
     "OPTIONAL MATCH (f)-[:INHERITS_FROM*1..8]->(a:OwnersFile)<-[:APPROVES]-(:Person) "
     "WITH f, count(a) AS covered WHERE covered = 0 RETURN count(f)", 0),
    ("departed with no current role",
     "MATCH (p:Person)-[:EMERITUS_OF]->() OPTIONAL MATCH (p)-[c:APPROVES]->() "
     "WITH p, count(c) AS n WHERE n = 0 RETURN count(DISTINCT p)", 83),
    ("total departed people",
     "MATCH (p:Person)-[:EMERITUS_OF]->() RETURN count(DISTINCT p)", 111),
    ("stale decisions still cited",
     "MATCH (o:Kep)-[:SEE_ALSO|REPLACES]->(k:Kep) "
     "WHERE k.status IN ['provisional','implementable'] AND k.created_ms > 0 "
     "AND ($now - k.created_ms) > $age "
     "RETURN count(DISTINCT k)", 43),
    ("...with an author who no longer hold approval authority",
     "MATCH (o:Kep)-[:SEE_ALSO|REPLACES]->(k:Kep) "
     "WHERE k.status IN ['provisional','implementable'] AND k.created_ms > 0 "
     "AND ($now - k.created_ms) > $age "
     "WITH DISTINCT k "
     "MATCH (au:Person)-[:AUTHORED|APPROVED]->(k) "
     "OPTIONAL MATCH (au)-[lr:APPROVES]->() "
     "OPTIONAL MATCH (au)-[em:EMERITUS_OF]->() "
     "WITH k, au, count(lr) AS live, count(em) AS gone "
     "WITH k, sum(live) AS lives, sum(CASE WHEN gone > 0 AND live = 0 THEN 1 ELSE 0 END) AS stepped "
     "WHERE lives = 0 AND stepped > 0 RETURN count(k)", 2),
    # Counted, not remembered: this was published as "8 of 679" for a long time and was wrong on
    # the total, the denominator and the breakdown.
    ("decisions with no usable creation date",
     "MATCH (k:Kep) WHERE k.created_ms = 0 RETURN count(k)", 7),
    ("KEP authors appearing in no OWNERS file",
     "MATCH (p:Person)-[:AUTHORED|APPROVED]->(:Kep) "
     "OPTIONAL MATCH (p)-[a:APPROVES]->() OPTIONAL MATCH (p)-[e:EMERITUS_OF]->() "
     "WITH p, count(a) AS na, count(e) AS ne WHERE na = 0 AND ne = 0 "
     "RETURN count(DISTINCT p)", 428),
    # the action's inputs, so the README's claim about it cannot drift from the graph either
    ("lopsided ownership records (>=3 stepped back, <=2 still listed, non-vendored)",
     "MATCH (p:Person)-[:EMERITUS_OF]->(e:OwnersFile) "
     "WITH p, collect(DISTINCT e.path) AS sb WHERE size(sb) >= 3 "
     "MATCH (p)-[:APPROVES]->(a:OwnersFile) "
     "WHERE NOT a.path STARTS WITH 'vendor/' AND NOT a.path STARTS WITH 'third_party/' "
     "WITH p, sb, collect(DISTINCT a.path) AS still WHERE size(still) <= 2 "
     "RETURN count(DISTINCT p)", 3),
    # The README names this person and these two counts in the refusal table. They are the
    # single strongest-looking candidate in the corpus and the one that must NOT be patched, so
    # if either number moves, the argument built on it moves too.
    ("stewart-yu: OWNERS files recording them as emeritus",
     "MATCH (p:Person {key:'stewart-yu'})-[:EMERITUS_OF]->(o:OwnersFile) RETURN count(o)", 20),
    ("stewart-yu: files still naming them an active approver",
     "MATCH (p:Person {key:'stewart-yu'})-[:APPROVES]->(o:OwnersFile) RETURN count(o)", 1),
    ("...excluded because the only straggler is a vendored file",
     "MATCH (p:Person)-[:EMERITUS_OF]->(e:OwnersFile) "
     "WITH p, collect(DISTINCT e.path) AS sb WHERE size(sb) >= 3 "
     "MATCH (p)-[:APPROVES]->(a:OwnersFile) "
     "WITH p, sb, collect(DISTINCT a.path) AS all_p "
     "WITH p, [x IN all_p WHERE x STARTS WITH 'vendor/' OR x STARTS WITH 'third_party/'] AS v, all_p "
     "WHERE size(v) > 0 AND size(all_p) <= 2 RETURN count(DISTINCT p)", 1),
]

fails = 0
for name, q, want in CLAIMS:
    got = one(q)
    ok = got == want
    fails += not ok
    print(f"  {'PASS' if ok else 'FAIL'}  {name:<34} claimed={want:<6} actual={got}")
_as_of = datetime.datetime.fromtimestamp(AS_OF_MS / 1000).strftime("%Y-%m-%d")
# How many claims this file checks is itself stated in prose, in four places, and nothing
# connected those sentences to this list. FINISH.md said 21 while the list held 31 -- the third
# stale figure found in that one file today, because FINISH.md appears in no checker's document
# list and is the file read LAST, under deadline, with the answers to a judge's hard questions in
# it. Asserted here, over whatever is tracked, rather than over a list of filenames that has
# already been extended twice and missed this one both times.
_ONES = ["zero", "one", "two", "three", "four", "five", "six", "seven", "eight", "nine", "ten",
         "eleven", "twelve", "thirteen", "fourteen", "fifteen", "sixteen", "seventeen",
         "eighteen", "nineteen"]
_TENS = {"twenty": 20, "thirty": 30, "forty": 40, "fifty": 50, "sixty": 60, "seventy": 70,
         "eighty": 80, "ninety": 90}


def _as_int(token: str):
    """A count written in digits or in words, or None when it is not a number at all."""
    t = token.strip().lower()
    if t.isdigit():
        return int(t)
    if t in _ONES:
        return _ONES.index(t)
    if t in _TENS:
        return _TENS[t]
    if "-" in t:
        head, _, tail = t.partition("-")
        if head in _TENS and tail in _ONES[1:10]:
            return _TENS[head] + _ONES.index(tail)
    return None


def _check_stated_count() -> int:
    import re as _re
    import subprocess as _subp
    want, bad = len(CLAIMS), 0
    docs = [d for d in _subp.run(["git", "ls-files", "*.md"], capture_output=True,
                                 text=True).stdout.split() if os.path.exists(d)]
    # The walkthrough's closing card now states this count too -- it used to make a vague claim
    # about "numbers" and was corrected to name a figure, which is better prose and a new thing
    # to keep in step. A viewer reads that card; it belongs in the same sweep as the documents.
    if os.path.exists("scripts_build_walkthrough.py"):
        docs.append("scripts_build_walkthrough.py")
    seen = 0
    for doc in docs:
        # Whitespace-flattened before scanning. The blog post wraps this very phrase as
        # "thirty-six graph\nclaims", and a pattern with a literal space between the words
        # matches nothing across that line break -- the third time in two days that wrapped
        # prose has silently disabled a regex in this repository.
        text = " ".join(open(doc).read().split())
        # Digits AND the spelled form. The blog post wrote "thirty-one graph claims", this scan
        # matched only \d+, and so the one document written for a separate prize kept a stale
        # count through every green build -- while the eval's own checker had already learned
        # this exact lesson and carries a spelling map for it. A number spelled out drifts
        # exactly as readily as one in digits and is harder to grep for.
        for pat in (r"([\d]+|[a-z]+(?:-[a-z]+)?) graph claims",
                    r"verify_claims\.py`? re-(?:checks|queries) (?:all|the) ([\d]+|[a-z]+(?:-[a-z]+)?)",
                    r"the script checks ([\d]+|[a-z]+(?:-[a-z]+)?) claims"):
            for said in _re.findall(pat, text, _re.I):
                parsed = _as_int(said)
                if parsed is None:
                    continue          # an adjective, not a count: "the graph claims" and friends
                seen += 1
                if parsed != want:
                    print(f"  FAIL  {doc} says {said} claims; this file checks {want}")
                    bad += 1
    if not seen:
        print(f"  FAIL  no tracked document says how many claims this checks ({want})")
        bad += 1
    elif not bad:
        print(f"  the claim count is stated {seen}x across the docs and every one says {want}")
    return bad


# Counted separately from `fails`, not added to it. Folding it in made a stale sentence in a
# document print as "30/31 claims verified", which says a claim about the graph could not be
# verified -- a different and more alarming thing than a number being out of date in prose.
_doc_bad = _check_stated_count()

print(f"\n{len(CLAIMS) - fails}/{len(CLAIMS)} claims verified "
      f"(as of {_as_of}; set AS_OF_MS to pin a different instant)")
if _doc_bad:
    _noun = "document states" if _doc_bad == 1 else "documents state"
    print(f"...but {_doc_bad} {_noun} the wrong number of claims, which is prose drift rather "
          f"than a failed claim.")
sys.exit(1 if (fails or _doc_bad) else 0)
