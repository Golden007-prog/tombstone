"""Pin the drafted/refused counts in prose to the dict the live run is verified against.

`verify_action.py` runs the drafting layer against the live graph and asserts
`CLAIMED = {"candidates": 3, "drafted": 2, "refused": 1, ...}`. That is the source of truth, and
CI re-derives it on every push. What CI could *not* see was the prose: five documents and the
GitHub repo description said "refuses the two candidates it cannot justify" -- inverting both
numbers -- while the README three screens down printed the real output, `2 OWNERS patches drafted
... 1 candidate refused`. The inversion came from counting the vendored case as a refusal; it is
excluded in the Cypher (`tools.py`), so it never becomes a candidate and no refusal is returned
for it. Same defect as every other count drift here: two copies of one claim, one of them edited.

The repo description is the worst place for it to live, because it is the first text a judge reads
and no file-reading check can see it. So this also asks GitHub, when `gh` is available.

Needs no database, no Docker and nothing outside the standard library, so it runs in the push
gate. Negative-tested: flip either number in any scanned file and it fails -- see `--self-test`.

    python3 scripts_check_action_counts.py
    python3 scripts_check_action_counts.py --self-test
"""
from __future__ import annotations

import pathlib
import re
import subprocess
import sys

TRUTH = pathlib.Path("verify_action.py")

WORDS = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5}
NUM = r"(\d+|one|two|three|four|five)"


def as_int(tok: str) -> int | None:
    return int(tok) if tok.isdigit() else WORDS.get(tok.lower())


# Each family states a count outright. Deliberately narrow: an ordinal like "refuses the third
# candidate" says *which* one, not how many, so it is not matched. A pattern broad enough to
# catch every phrasing is a pattern that cannot fail, which is how two earlier audits here
# returned false all-clears.
DRAFTED = [
    re.compile(rf"\b{NUM} (?:real |reviewable )?OWNERS patches\b", re.I),
    re.compile(rf"\b{NUM} patches drafted\b", re.I),
    re.compile(rf"\bdrafts {NUM} (?:real |reviewable )?patches\b", re.I),
    re.compile(rf"\bbecomes {NUM} reviewable OWNERS patches\b", re.I),
    re.compile(rf"\b{NUM} drafts and\b", re.I),
]
REFUSED = [
    re.compile(rf"\b{NUM} candidates? (?:is |are )?refused\b", re.I),
    re.compile(rf"\brefuses the {NUM} candidates?\b", re.I),
    re.compile(rf"\band {NUM} refusals?\b", re.I),
]


def flat(text: str) -> str:
    """Join wrapped lines before scanning: prose here wraps at 100 columns, and a claim split
    across two lines has defeated three regexes in this repo already."""
    return re.sub(r"\s+", " ", text)


def expected() -> dict:
    m = re.search(r"^CLAIMED = \{(.+?)\}\n", TRUTH.read_text(encoding="utf-8"), re.M | re.S)
    if not m:
        sys.exit(f"FAIL  cannot find the CLAIMED dict in {TRUTH} -- this checker is stale, "
                 f"fix the checker rather than deleting it")
    out = {}
    for key in ("drafted", "refused"):
        km = re.search(rf'"{key}": (\d+)', m.group(1))
        if not km:
            sys.exit(f'FAIL  {TRUTH} no longer pins "{key}"')
        out[key] = int(km.group(1))
    return out


def scan(text: str, where: str, want: dict, problems: list) -> int:
    hits = 0
    for label, pats in (("drafted", DRAFTED), ("refused", REFUSED)):
        for pat in pats:
            for m in pat.finditer(text):
                got = as_int(m.group(1))
                if got is None:
                    continue
                hits += 1
                if got != want[label]:
                    problems.append(f"{where}: says {label} = {got}, the verified run says "
                                    f"{want[label]} -- \"{m.group(0)}\"")
    return hits


def tracked() -> list[pathlib.Path]:
    out = subprocess.run(["git", "ls-files", "*.md", "web/*.html", "web/*.js"],
                         capture_output=True, text=True).stdout.split()
    return [pathlib.Path(p) for p in out if pathlib.Path(p).exists()]


def description() -> str | None:
    """The repo description, or None when gh is absent or unauthenticated. Absence is a skip, not
    a failure: the push gate must work offline."""
    try:
        r = subprocess.run(["gh", "repo", "view", "--json", "description", "-q", ".description"],
                           capture_output=True, text=True, timeout=20)
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return None
    return r.stdout.strip() if r.returncode == 0 and r.stdout.strip() else None


def main() -> int:
    want = expected()
    problems: list[str] = []
    hits = 0
    for path in tracked():
        hits += scan(flat(path.read_text(encoding="utf-8")), str(path), want, problems)

    # Anti-vacuity: if the phrasings all changed, this checker is silently checking nothing.
    if hits == 0:
        problems.append("no count claims matched at all -- the patterns have gone stale, which "
                        "means this check was passing over an empty set")

    desc = description()
    if desc is None:
        print("  skip  repo description (gh unavailable or unauthenticated)")
    else:
        before = len(problems)
        scan(flat(desc), "GitHub repo description", want, problems)
        if len(problems) == before:
            print("  ok    repo description agrees with the verified run")

    if problems:
        for p in problems:
            print(f"  FAIL  {p}")
        return 1
    print(f"  ok    {hits} drafted/refused claims across {len(tracked())} files all match "
          f"verify_action.py (drafted={want['drafted']}, refused={want['refused']})")
    return 0


def self_test() -> int:
    """Prove the patterns can fail. Each sample is a real phrasing from this repo with one number
    flipped; every one must be caught."""
    want = expected()
    samples = [
        "2 OWNERS patches drafted from the graph, 2 candidates refused with a reason",
        "two patches drafted, two candidates refused mid-list",
        "it drafts three patches, and refuses the one it cannot justify",
        "a finding becomes one reviewable OWNERS patches",
        "the live run reports two drafts and three refusals",
        "refuses the two candidates it cannot justify",
    ]
    bad = []
    for s in samples:
        problems: list[str] = []
        scan(flat(s), "sample", want, problems)
        if not problems:
            bad.append(s)
    # And a correct sentence must NOT trip it.
    clean: list[str] = []
    scan(flat("2 OWNERS patches drafted from the graph, 1 candidate refused with a reason"),
         "sample", want, clean)
    if clean:
        bad.append("false positive on a correct sentence: " + "; ".join(clean))
    for s in bad:
        print(f"  FAIL  not caught: {s}")
    if bad:
        return 1
    print(f"  ok    all {len(samples)} wrong-count phrasings caught, correct phrasing passes")
    return 0


if __name__ == "__main__":
    raise SystemExit(self_test() if "--self-test" in sys.argv else main())
