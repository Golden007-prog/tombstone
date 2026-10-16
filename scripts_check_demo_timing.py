"""Fail if the demo script cannot actually be spoken in the time it allocates.

An earlier draft held 767 spoken words in 180 seconds. That is 4.3 words per second; comfortable
narration is about 2.8. Read aloud it ran roughly 4:35, so a 3:00 cap would have been discovered
at midnight during take nine. This checks three things:

  1. the beats are contiguous and sum to the stated total,
  2. no beat exceeds 3.0 spoken words per second,
  3. each beat's stated word budget matches the words actually written in it.
"""
import re
import sys

MAX_WPS = 3.0
PATH = "docs/DEMO-SCRIPT.md"



def narration(body: str) -> str:
    """The words a human actually says.

    The blockquote lines are joined FIRST, because a single narration quote spans many `>` lines
    and per-line matching finds no closing quote on any of them. Stage directions (`*[...]*`) are
    stripped before the quoted spans are read, so a screen note that happens to quote an on-screen
    word is not counted as narration.
    """
    quoted = " ".join(ln.strip()[1:].strip() for ln in body.splitlines()
                      if ln.strip().startswith(">"))
    quoted = re.sub(r"\*\[[^\]]*\]\*", " ", quoted)
    return " ".join(re.findall(r'"([^"]*)"', quoted))


def secs(t: str) -> int:
    m, s = t.split(":")
    return int(m) * 60 + int(s)


text = open(PATH).read()
beats = re.split(r"^### (\d:\d\d)–(\d:\d\d) — (.+?) · (\d+) words$", text, flags=re.M)
if len(beats) < 6:
    sys.exit(f"{PATH}: found no beats with the '### m:ss–m:ss — title · N words' shape.")

fails, prev, total_w, total_s, worst = [], 0, 0, 0, []
print(f"{'beat':<46}{'sec':>5}{'budget':>8}{'actual':>8}{'w/s':>7}")
print("-" * 74)
for i in range(1, len(beats), 5):
    start, end, title, budget, body = beats[i:i + 5]
    spoken = narration(body)
    words, dur = len(spoken.split()), secs(end) - secs(start)
    wps = words / dur if dur else 999
    total_w += words
    worst.append(wps)
    total_s += dur
    if secs(start) != prev:
        fails.append(f"{title}: starts at {start}, but the previous beat ended at "
                     f"{prev // 60}:{prev % 60:02d}")
    prev = secs(end)
    if wps > MAX_WPS:
        fails.append(f"{title}: {words} words in {dur}s = {wps:.1f} w/s, over {MAX_WPS}")
    if abs(int(budget) - words) > 6:
        fails.append(f"{title}: heading claims {budget} words, body has {words}")
    print(f"{title[:44]:<46}{dur:>5}{budget:>8}{words:>8}{wps:>7.1f}")

print("-" * 74)
print(f"{'TOTAL':<46}{total_s:>5}{'':>8}{total_w:>8}{total_w / total_s:>7.1f}")
if total_s != 180:
    fails.append(f"beats total {total_s}s, not the 180s the script caps itself at")

# The prose above the beats states the totals in words, and nothing re-derived that sentence, so
# it drifted: it claimed 464 words at 2.6 w/s while the beats summed to 489 at 2.7. That is the
# precise failure this product is an argument against -- a figure written once and never checked --
# sitting in the one document that gets read aloud. Checked here, where the figures are produced.
# (\d+(?:\.\d+)?) rather than [\d.]+ : the latter is greedy and swallowed the full stop that ends
# the sentence, so the claim parsed as "2.9." and the check died on float() instead of reporting.
claim = re.search(r"holds \*\*(\d+)\*\*,\s+at\s+(\d+(?:\.\d+)?)\s+w/s,"
                  r"\s+with no beat above\s+(\d+(?:\.\d+)?)", text)
if not claim:
    fails.append("the script no longer states its own word total in the form this check reads")
else:
    said_total, said_wps, said_max = int(claim[1]), float(claim[2]), float(claim[3])
    measured_wps = round(total_w / total_s, 1)
    measured_max = round(max(worst), 1)
    if said_total != total_w:
        fails.append(f"the prose says this script holds {said_total} words; the beats hold {total_w}")
    if said_wps != measured_wps:
        fails.append(f"the prose says {said_wps} w/s overall; the beats measure {measured_wps}")
    if said_max != measured_max:
        fails.append(f"the prose says no beat is above {said_max} w/s; the worst is {measured_max}")

if fails:
    print("\n" + "\n".join("  FAIL  " + f for f in fails))
    sys.exit(1)
print(f"\nSpeakable: {total_w} words across {total_s}s, every beat at or under {MAX_WPS} w/s.")
