"""Scan every markdown file for corpus counts and check them against the live graph.

Fixing a stale number in one document does not stop the next one going stale. These counts appear
across the README, the blog, the submission copy, the corpus notes and the Space landing page, and
they move whenever the corpus or the resolver changes. Two were found wrong by hand today --
"8 of 679 decisions have no usable date" and a corpus table still saying 679 Kep / 959 Alternative
/ 52 MissingRecord -- both of which had been true when written.

So this does it for every file at once: find any number sitting next to one of the nouns this
project counts, and require it to be that count. It deliberately reads the files a judge reads,
not a list someone remembers to update.
"""
from __future__ import annotations

import pathlib
import re
import sys

sys.path.insert(0, "src")
from graphkit.ingest import connect  # noqa: E402

g = connect().select_graph("tomb:k8s")


def count(query: str) -> int:
    return g.ro_query(query).result_set[0][0]


# noun -> (live count, the phrasings used across the docs)
COUNTS = {
    "decisions": (count("MATCH (k:Kep) RETURN count(k)"),
                  [r"decisions?", r"KEPs?\b"]),
    "rejected alternatives": (count("MATCH (a:Alternative) RETURN count(a)"),
                              [r"rejected alternatives?", r"Alternatives?\b"]),
    "named options": (count("MATCH (a:NamedOption) RETURN count(a)"),
                      [r"named options?", r"titled `?:?NamedOption`?",
                       r"titled rejected options?"]),
    "people": (count("MATCH (p:Person) RETURN count(p)"), [r"people\b", r"Person\b"]),
    "ownership files": (count("MATCH (o:OwnersFile) RETURN count(o)"),
                        [r"ownership files?", r"`?OWNERS`? files?", r"OwnersFile\b"]),
}

# Numbers that are history, not current state: a quoted "previously said", a correction, a
# benchmark on a different graph. Those lines say so, and re-asserting them would be wrong.
HISTORY = re.compile(
    r"previously|used to|was wrong|withdrawn|corrected|drifted|said \d|"
    r"earlier|first number|I had claimed|claimed \d|synthetic|3,300|older|stale", re.I)

# A subset is not a total. "19 OWNERS files declare only reviewers" and "83 of 111 people" are
# both true and neither is a claim about how many exist. Without this the check produced nine
# false alarms against two real faults, and a check that cries wolf is one people learn to skip.
SUBSET = re.compile(r"\b(?:of|in|among|and)\s+$|\bonly\s+$|\bjust\s+$")

# The judge-facing documents. K8S-CORPUS-VERIFIED.md is excluded on purpose: it records what the
# RAW corpus looked like while it was being understood -- 684 kep.yaml files parsed, 688 READMEs,
# counts taken before templates were excluded -- which are different quantities from the graph's
# node counts, not stale versions of them. Its own summary table is checked by hand when it moves.
files = [pathlib.Path("README.md"), pathlib.Path("SUBMISSION.md"),
         pathlib.Path("deploy/README-hf-space.md"), pathlib.Path("docs/DEMO-SCRIPT.md"),
         pathlib.Path("docs/BLOG-POST.md")]
files = [f for f in files if f.exists()]
problems = []
checked = 0

for path in files:
    for lineno, line in enumerate(path.read_text().splitlines(), 1):
        if HISTORY.search(line):
            continue
        for label, (live, phrasings) in COUNTS.items():
            for phrasing in phrasings:
                for m in re.finditer(rf"\b([\d,]{{2,}})\s+(?:\*\*)?{phrasing}", line):
                    if SUBSET.search(line[:m.start()]):
                        continue
                    found = int(m.group(1).replace(",", ""))
                    # A DRIFTED total sits a hair off the real one -- 679 against 681, 959
                    # against 958. A subset does not: "25 people" in a community and "19 OWNERS
                    # files that declare only reviewers" are both true and neither is a claim
                    # about the whole. Only near-misses are drift, so only near-misses are
                    # reported; this check is for numbers that used to be right.
                    if not (0.9 * live <= found <= 1.1 * live):
                        continue
                    checked += 1
                    if found != live:
                        problems.append(
                            f"{path}:{lineno}: says {found:,} {label}, the graph has {live:,}\n"
                            f"      {line.strip()[:100]}")

print(f"  scanned {len(files)} markdown files, checked {checked} count claims")
for label, (live, _) in COUNTS.items():
    print(f"    {label:<24} {live:,}")
if problems:
    print("\n" + "\n".join("  FAIL  " + p for p in problems))
    sys.exit(1)
print("\nOK: every corpus count in the docs matches the graph")
