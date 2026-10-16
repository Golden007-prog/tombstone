"""How big is Track 3, and how much of it is actually deployed?

SUBMISSION.md used to answer this from a hand-made list of eight repositories. By 16 Oct that
list was wrong by an order of magnitude -- the field is 85 entries -- and one of the conclusions
drawn from it was backwards: it said a live demo "is now the one thing the rest of the field has
and this does not", when most of the field has no public URL at all.

So the count gets a script, like every other number here. This one cannot be gated: it queries
GitHub, the answer changes hourly, and a check that depends on other people's push times would
be red for reasons that have nothing to do with this repository. It is a dated measurement with
a committed script, which is the same contract the benchmarks have.

Two things it is careful about:

  - It counts repositories CREATED in the hackathon window, not everything mentioning FalkorDB.
    The unfiltered query returns 559 repositories, most of them nothing to do with this event.
  - It looks for a demo in the README as well as in the `homepage` field, because three of the
    fifteen largest entries link a live demo only in their README. Counting `homepage` alone
    undercounts, and reporting that undercount as the deployment rate would be the same kind of
    overclaim this repository keeps finding in itself.

It reports a CENSUS of the N largest rather than a rate over all 85, because reading 85 READMEs
to check 85 URLs is slow and the tail is mostly scaffolding -- several entries are 0KB. A rate
over a subset you have actually examined is honest; one extrapolated from a sample is not.

Usage:  python3 scripts_survey_field.py [N]        (needs `gh`, no graph, no token beyond gh's)
"""
from __future__ import annotations

import base64
import json
import re
import subprocess
import sys
import urllib.parse

WINDOW = "2026-10-14"          # entries created on or after this date
QUERIES = [
    f'falkordb created:>={WINDOW} in:readme "track 3"',
    f'falkordb created:>={WINDOW} company brain',
    f'falkordb created:>={WINDOW} in:readme "company brain"',
]
MINE = "aviralgarg05/tombstone"
HOST = re.compile(
    r"https?://[^\s)\]\"'>*]*?(?:vercel\.app|hf\.space|huggingface\.co/spaces|onrender\.com"
    r"|railway\.app|fly\.dev|streamlit\.app|netlify\.app|sslip\.io)[^\s)\]\"'>*]*", re.I)

# Named public corpora only, and the exclusions matter more than the inclusions. The first
# version of this also matched "apache" and "acme", which made it useless in both directions:
# "apache" is the LICENCE on half of these repositories, and "acme" appears most often inside a
# sentence refusing to invent an Acme Corp -- including in this repository's own README, which
# the first run therefore classified as synthetic. A pattern keyed on a word rather than a
# meaning, for the third time in two days.
CORPUS = re.compile(r"\b(kubernetes|k8s|cpython|PEP-?\d|discuss\.python\.org|linux\s+kernel|"
                    r"chromium|rust-lang|tensorflow|kafka|airflow|openstack|wikipedia|"
                    r"stack\s*overflow|arxiv)\b", re.I)


def gh(path: str, jq: str) -> str:
    return subprocess.run(["gh", "api", path, "--jq", jq],
                          capture_output=True, text=True, timeout=60).stdout.strip()


def reachable(url: str) -> str:
    """curl, not urllib: two of these time out under urllib's default headers and answer 200 to
    curl, and reporting a live competitor as dead would be a flattering error."""
    out = subprocess.run(["curl", "-s", "-o", "/dev/null", "-w", "%{http_code}",
                          "-m", "40", "-L", url], capture_output=True, text=True).stdout.strip()
    return out or "timeout"


def main() -> int:
    top_n = int(sys.argv[1]) if len(sys.argv) > 1 else 20
    total = gh(f"search/repositories?q={urllib.parse.quote(f'falkordb created:>={WINDOW}')}"
               "&per_page=1", ".total_count")
    seen: dict[str, dict] = {}
    for q in QUERIES:
        out = gh(f"search/repositories?q={urllib.parse.quote(q)}&per_page=100",
                 ".items[] | {full_name, pushed_at, homepage, size}")
        for line in out.splitlines():
            if line.strip():
                r = json.loads(line)
                seen[r["full_name"]] = r
    if not seen:
        print("  REFUSING to report: the search returned nothing. Is `gh` authenticated?")
        return 1

    field = sorted(seen.values(), key=lambda r: -(r.get("size") or 0))
    print(f"  {total} repositories created since {WINDOW} mention FalkorDB.")
    print(f"  {len(field)} of them are Track 3 / company-brain entries.\n")

    mine = next((i for i, r in enumerate(field) if r["full_name"] == MINE), None)
    live, checked, real = [], [], []
    print(f"  {'repo':<44}{'MB':>6}  demo")
    for r in field[:top_n]:
        name = r["full_name"]
        cands = []
        home = (r.get("homepage") or "").strip()
        if home.startswith("http") and "wemakedevs" not in home:
            cands.append(home)
        body = gh(f"repos/{name}/readme", ".content")
        decoded = ""
        if body:
            try:
                decoded = base64.b64decode(body).decode("utf-8", "replace")
                cands += HOST.findall(decoded)
            except Exception:
                pass
        status, url = "-", ""
        for u in dict.fromkeys(cands):
            code = reachable(u)
            if code == "200":
                status, url = "200", u
                break
            status, url = code, u
        checked.append(name)
        if status == "200":
            live.append((name, url))
        corpora = sorted({m.group(0).lower() for m in CORPUS.finditer(decoded)})
        if corpora:
            real.append((name, corpora))
        mark = " <- this one" if name == MINE else ""
        print(f"  {name[:43]:<44}{(r.get('size') or 0) / 1024:>6.0f}  "
              f"{status}{'  ' + url[:44] if url else ''}{mark}")

    print(f"\n  {len(live)} of the {len(checked)} largest serve a reachable demo:")
    for name, url in live:
        print(f"     {name:<42} {url}")
    print(f"\n  {len(real)} of the {len(checked)} largest name a specific real public corpus "
          f"in the README:")
    for name, corpora in real:
        print(f"     {name:<42} {', '.join(corpora)}")
    print("     (What a README claims, not what its code does. Read as a claim.)")
    if mine is not None:
        print(f"\n  This repository is {mine + 1} of {len(field)} by size.")
    deployed_here = any(n == MINE for n, _ in live)
    print(f"  Deployed: {'yes' if deployed_here else 'NOT YET'}.")
    if not deployed_here:
        print(f"  So deploying moves this into a minority of the serious field, not up to par "
              f"with it -- {len(checked) - len(live)} of the {len(checked)} largest have no "
              f"reachable demo either.")
    print("\n  Dated, not gated: other people's repositories change hourly, and a check that goes")
    print("  red when a stranger force-pushes is a check nobody can act on.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
