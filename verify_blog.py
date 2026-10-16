"""Re-check the blog post's factual claims against the live graph.

The README's numbers are checked by verify_claims.py and the printed output by another script.
The blog was never covered, and it is the artifact that goes out under a byline to an audience
that cannot run anything -- so a stale number there is both the most embarrassing and the least
correctable. It had four wrong when it was read end to end, one of them a figure the README had
retracted hours earlier.

These are the specific claims the post makes. The corpus-wide counts are covered separately by
scripts_check_doc_counts.py, which reads the blog among other files.
"""
from __future__ import annotations

import sys

sys.path.insert(0, "src")
from graphkit.ingest import connect       # noqa: E402
from tombstone.snapshot import load       # noqa: E402

g = connect().select_graph("tomb:k8s")
corpus = load()


def q(cypher: str) -> int:
    return g.ro_query(cypher).result_set[0][0]


owners_with_emeritus = sum(1 for d in corpus.owners.values() if (d or {}).get("emeritus_approvers"))
total_owners = len(corpus.owners)

CLAIMS = {
    "OWNERS files parsed": (total_owners, 585),
    "declare emeritus approvers": (owners_with_emeritus, 138),
    "...as a percentage": (round(owners_with_emeritus / total_owners * 100, 1), 23.6),
    "emeritus entries": (q("MATCH ()-[r:EMERITUS_OF]->() RETURN count(r)"), 298),
    "distinct emeritus people": (
        q("MATCH (p:Person)-[:EMERITUS_OF]->() RETURN count(DISTINCT p)"), 111),
    "of those, hold no approval anywhere": (q(
        "MATCH (p:Person)-[:EMERITUS_OF]->() OPTIONAL MATCH (p)-[a:APPROVES]->() "
        "WITH p, count(a) AS n WHERE n = 0 RETURN count(DISTINCT p)"), 83),
    "titled rejected options": (q("MATCH (n:NamedOption) RETURN count(n)"), 752),
    "internal pointers that go nowhere": (
        q("MATCH ()-[r:CITES_MISSING]->() RETURN count(r)"), 55),
    "decisions claiming descent from apply.md": (q(
        "MATCH (m:MissingRecord)<-[:CITES_MISSING]-(k:Kep) "
        "WITH m, count(DISTINCT k) AS n ORDER BY n DESC LIMIT 1 RETURN n"), 4),
}

blog = open("docs/BLOG-POST.md").read()
fails = 0
for label, (live, claimed) in CLAIMS.items():
    printed = str(claimed) in blog
    ok = live == claimed and printed
    fails += not ok
    note = "" if printed else "  (the post no longer prints this)"
    print(f"  {'PASS' if ok else 'FAIL'}  {label:<38} post={claimed:<7} live={live}{note}")

print(f"\n{len(CLAIMS) - fails}/{len(CLAIMS)} blog claims verified")
# The post states two counts of its own: how many FalkorDB lessons it carries, and how many CI
# steps run. Both were typed. The second was already stale -- it said twenty-seven while thirty
# run -- which is the same way five other numbers in this repo went wrong in two days.
import re as _re

# Spelled, not looked up in a table. Both of these were hand-maintained dicts and both ran out:
# the lessons map stopped at twelve, and the CI map stopped at thirty-two, so adding a
# thirty-third step produced "the post says Thirty-three CI steps and the workflow has 33" --
# a FAILURE whose own message shows the two agreeing, because .get(33) returned None. The
# sibling checker already carries a comment about this exact defect ("five was missing, so the
# check failed on a pair of numbers that actually agreed") and I reproduced it twice over.
_ONES = ["zero", "one", "two", "three", "four", "five", "six", "seven", "eight", "nine", "ten",
         "eleven", "twelve", "thirteen", "fourteen", "fifteen", "sixteen", "seventeen",
         "eighteen", "nineteen"]
_TENS = [None, None, "twenty", "thirty", "forty", "fifty", "sixty", "seventy", "eighty", "ninety"]


def _spell(n: int) -> str | None:
    """English for 0-99, generated. Returns None above that, where this has no business."""
    if not 0 <= n < 100:
        return None
    if n < 20:
        return _ONES[n]
    tens, ones = divmod(n, 10)
    return _TENS[tens] if not ones else f"{_TENS[tens]}-{_ONES[ones]}"


def _states(label: str, said, n: int) -> int:
    """Compare a spelled count in the prose with a derived one, and say which way it went.

    The distinction the old message could not draw: a document disagreeing with reality is one
    failure, and this checker not knowing how to spell a number is a different one. Reporting the
    second as the first sends you looking in the document.
    """
    want = _spell(n)
    if said is None:
        print(f"  FAIL  the post no longer states {label} where this check reads it")
        return 1
    if want is None:
        print(f"  FAIL  {label}: cannot spell {n}, so this check cannot judge "
              f"{said!r} -- fix the checker, not the post")
        return 1
    if said.strip().lower() != want:
        print(f"  FAIL  the post says {said} {label} and the workflow has {n} ({want})")
        return 1
    print(f"  PASS  the post says {said} {label} and that is {n}")
    return 0


_n_lessons = len(_re.findall(r"^### \d+\.", blog, _re.M))
_said = _re.search(r"^## (\w+(?:-\w+)?) things FalkorDB taught me", blog, _re.M)
fails += _states("FalkorDB lessons", _said.group(1) if _said else None, _n_lessons)

_steps = sum(1 for _l in open(".github/workflows/verify.yml") if _re.match(r"^\s*- name:", _l))
_said_ci = _re.search(r"(\w+(?:-\w+)?) CI steps\.", blog)
fails += _states("CI steps", _said_ci.group(1) if _said_ci else None, _steps)

# FINISH.md tells you how long this post is, so you can budget reading it on the last day. It
# said "~1,750 words" for a post of 4,185 -- off by well over double, in the one file written to
# be read under deadline. The post's own length is the only figure about it that nothing else
# could catch: doc_counts checks the corpus numbers inside it, and the claims above check the
# facts, but how big it is lives in a different file entirely.
_words = len(blog.split())
_said_len = _re.search(r"`docs/BLOG-POST\.md` is finished, ~([\d,]+) words", open("FINISH.md").read())
if not _said_len:
    print("  FAIL  FINISH.md no longer states the post's length where this check looks")
    fails += 1
else:
    _claimed = int(_said_len.group(1).replace(",", ""))
    # Rounded to the nearest 50 in prose, so allow that much slack and no more.
    _close = abs(_claimed - _words) <= 50
    print(f"  {'PASS' if _close else 'FAIL'}  FINISH.md says ~{_claimed:,} words and the post "
          f"has {_words:,}")
    fails += not _close

sys.exit(1 if fails else 0)
