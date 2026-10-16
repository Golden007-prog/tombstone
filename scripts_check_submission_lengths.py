"""The submission copy states its own lengths. Check them, because nobody else was.

`SUBMISSION.md` carries the pitch at three lengths and says how long each one is. Those numbers
are not decoration: the form's fields are invisible until you register, so if the Description
field turns out to cap at 2,000 characters you want to paste a shorter tier rather than rewrite
at 11pm. A stated length that is wrong at that moment is worse than no length at all.

Nothing verified them. The Description said 3,556 characters and had grown to 3,654 when the
dense-retrieval figure was added to it — a number describing the submission copy, inside the
submission copy, ninety-eight characters adrift and no check reading it.

Needs no database and no browser, so it runs in the push gate rather than waiting for
./preflight.sh.

    python3 scripts_check_submission_lengths.py
"""
from __future__ import annotations

import re
import sys

PATH = "SUBMISSION.md"
TIER_SLACK = 8      # the tiers are written "~273", so rounding is expected
EXACT_SLACK = 5     # the Description states a bare figure, so it should be the figure


def _flat(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def main() -> int:
    src = open(PATH, encoding="utf-8").read()
    problems, checked = [], 0

    # Each tier: the blockquote immediately under its "**~N characters:**" marker.
    tiers = list(re.finditer(r"\*\*~(\d+) characters:\*\*\n\n((?:>.*\n)+)", src))
    if not tiers:
        problems.append(f"{PATH}: no '**~N characters:**' tiers found where this check reads them")
    for m in tiers:
        said = int(m.group(1))
        body = _flat(" ".join(ln.lstrip("> ").rstrip() for ln in m.group(2).splitlines()
                              if ln.strip().startswith(">")))
        if abs(len(body) - said) > TIER_SLACK:
            problems.append(f"{PATH}: a tier says ~{said} characters and holds {len(body)}")
        else:
            checked += 1
            print(f"  the ~{said}-character tier holds {len(body)}")

    # The full Description, and the sentence above it that states its length.
    if "## Description" not in src:
        problems.append(f"{PATH}: no '## Description' section")
    else:
        # NOT flattened, unlike the tiers, and the distinction is the whole point of the number.
        # A tier is one paragraph wrapped across lines in this file, so it pastes into a form
        # field as a single line and its newlines are not characters anyone pays for. The
        # Description is several paragraphs and pastes WITH its blank lines, which a character
        # cap counts. Measure what the person pastes, not what is convenient to measure: the two
        # differ by six characters here, which is small enough to hide inside any slack and
        # wrong in the direction that matters when a field caps at exactly the wrong place.
        desc = src.split("## Description", 1)[1].split("\n## ", 1)[0].strip()
        said = re.search(r"Description below is (\d+) characters", src)
        if not said:
            problems.append(f"{PATH}: no longer states the Description's length where this reads it")
        elif abs(len(desc) - int(said.group(1))) > EXACT_SLACK:
            problems.append(f"{PATH}: says the Description is {said.group(1)} characters; "
                            f"it is {len(desc)}")
        else:
            checked += 1
            print(f"  the Description holds {len(desc)} characters and says so")

    # Ordering: a shorter tier that is longer than a longer tier would be nonsense, and is the
    # kind of thing an edit to one block introduces silently.
    lens = [int(m.group(1)) for m in tiers]
    if lens != sorted(lens):
        problems.append(f"{PATH}: the tiers are not in increasing order: {lens}")
    elif lens:
        checked += 1

    if problems:
        print("\n" + "\n".join(f"  FAIL  {p}" for p in problems))
        return 1
    print(f"\nOK: {checked} stated lengths in {PATH} match the text they describe.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
