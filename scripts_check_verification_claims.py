"""Catch the one sentence shape that has been wrong five times: a universal claim about checking.

Every claim this repository makes about the PRODUCT turned out to be right. Five claims it made
about its own VERIFICATION were overstated, in five different documents, and each was written
without being checked because it was a sentence about diligence and therefore felt like diligence:

  "every benchmark re-run on each push"        — two of five run in CI
  "every number here is re-checked"            — thirty-one graph claims are
  "Every number is checked against the live graph"  (the video's closing card)
  "a script that re-queries every number in the README"
  "there is a verify_claims.py that re-checks each factual claim"

None was a lie. Each paired a universal quantifier with a verification verb, which is the
combination worth refusing outright: the repository has three different guarantees (derived,
bounded, dated) and a sentence that flattens them into "every" is wrong by construction.

This is deliberately NARROW. It does not flag "every answer carries its Cypher" or "the model
never writes a query" -- claims about the product, which are checked elsewhere and are true. It
flags only a universal quantifier applied to the act of checking.

Run: python scripts_check_verification_claims.py
"""
from __future__ import annotations

import pathlib
import re
import sys

DOCS = ["README.md", "SUBMISSION.md", "docs/EXPLAIN-IT.md", "docs/BLOG-POST.md",
        "docs/video/README.md", "deploy/README-hf-space.md",
        # Not a document, but it holds the video's title and closing cards -- text a
        # viewer reads, in a file no prose checker was looking at.
        "scripts_build_walkthrough.py"]

# A universal quantifier within a few words of a verification verb.
QUANT = r"(every|each|all)\s+(?:single\s+)?(number|claim|figure|benchmark|fact|statement|metric)s?"
VERB = r"(check|re-?check|verif|assert|re-?run|re-?quer|guarantee|gated)"
BAD = re.compile(rf"{QUANT}\b[^.]{{0,60}}?\b{VERB}|{VERB}[a-z]*\b[^.]{{0,40}}?\b{QUANT}", re.I)

# A bare plural subject makes the same claim without the quantifier, and the rule above
# cannot see it: the video's closing card read "Numbers re-checked against the live graph
# on every push", where "every" attaches to "push" and the sweep over nouns finds nothing.
# Three of the five benchmarks are dated measurements, so that sentence was the one place
# in the project still making the claim this file exists to stop -- on the last frame a
# viewer sees.
# `[^A-Za-z]{0,4}` because in the walkthrough builder the sentence is a Python string, so the
# stripped line begins `("` rather than with the word.
BARE = re.compile(rf"^[^A-Za-z]{{0,4}}(numbers|claims|figures|benchmarks|facts|metrics)"
                  rf"\b[^.]{{0,40}}?\b{VERB}", re.I)

# Sentences that describe the mistake rather than make it. Each is a correction this repo wrote
# about itself, and refusing them would mean refusing to document the thing being prevented.
# Two kinds of line are fine and the first version of this check flagged both, which is how a
# check earns its way into being skipped. A SCOPED claim names what it covers -- "in this
# section", "above", "the 35 graph claims" -- and is a different sentence from "every number".
# A QUOTED one is this repository documenting the mistake, and refusing those would mean refusing
# to write down the thing being prevented.
ALLOWED = re.compile(r"used to say|previously|was wrong|overstated|not quite true|"
                     r"neither was|I had written|which was comfortable and wrong|"
                     r"this footer|the old version|wrong three times|had been wrong|"
                     r"README said|\bsaid\b.{0,20}\"|"                       # quoting
                     r"in this section|\babove\b|\bbelow is\b|this page|"    # scoped
                     r"\d+ graph claims|is checkable", re.I)


def main() -> int:
    hits = []
    for doc in DOCS:
        p = pathlib.Path(doc)
        if not p.exists():
            continue
        for lineno, line in enumerate(p.read_text().split("\n"), 1):
            text = line.strip()
            if len(text) < 20:
                continue
            m = BAD.search(text) or BARE.search(text)
            if not m or ALLOWED.search(text):
                continue
            # A match inside quotation marks in PROSE is this repository quoting a sentence it
            # already corrected, and refusing those would make it impossible to write down what
            # the mistake was. In a .py file the same quotes mean the opposite: the string IS the
            # text a viewer reads. Applying the prose rule there would have excused the video's
            # closing card, which is the one place this claim survived.
            quoted_is_a_quotation = not doc.endswith(".py")
            if quoted_is_a_quotation and any(
                    m.group(0)[:20] in q for q in re.findall(r'"([^"]{10,160})"', text)):
                continue
            hits.append((doc, lineno, m.group(0)[:60], text[:96]))

    if hits:
        print(f"{len(hits)} universal "
              f"{'claim' if len(hits) == 1 else 'claims'} about verification:\n")
        for doc, lineno, frag, text in hits:
            print(f"  {doc}:{lineno}")
            print(f"      matched: {frag!r}")
            print(f"      {text}")
        print("\nThis repository has three guarantees, not one: numbers derived from the graph are")
        print("checked on every push, benchmark ratios are reported with their conditions, and the")
        print("tenancy figures are dated. A sentence that says 'every number is checked' flattens")
        print("them and is wrong about two thirds of them. Name which kind you mean.")
        return 1

    print(f"  no universal claims about verification in {len(DOCS)} shipped documents")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
