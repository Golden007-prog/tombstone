# Demo video — 3 minutes, hard cap

**3 minutes, self-imposed.** The hackathon publishes no video-length rule — I looked, and there
isn't one on the event page, the rules page or the kickoff blog. Three minutes is simply what
general hackathon-judging advice converges on (MLH, Devpost), and a judge watching dozens of
entries will thank you for it. Plain screen recording, product first, no architecture diagram:
no title card, no "hi everyone", no stack slide. The first frame is the product and the first
sentence is the problem.

(The silent walkthrough in `docs/video/` *does* open and close with a card. That is not an
inconsistency: it has no narration, so nothing else can say what the thing is. Here your voice
does that in the first eight words, and a card would spend six seconds repeating it.)

Record the voiceover **separately** from the screen capture and lay them together. Narrating live
while driving the UI is the single biggest cause of ten retakes at midnight.

**While recording, read [`DEMO-NARRATION.md`](DEMO-NARRATION.md), not this file.** It is this
script with everything but the spoken words removed — cue times, one sentence per line, no stage
directions to skip past on take four. It is generated from this file by
`scripts_build_narration.py` and the push gate refuses a push where the two disagree, so it
cannot quietly fall behind an edit made here.

**Every beat below is written to a word budget**, because an earlier draft of this script was not.
It held 767 spoken words in 180 seconds — 4.3 words per second, which is not a narration, it is a
countdown. Read aloud it ran about 4:35, so the 3:00 cap would have been discovered at midnight
during take nine. Comfortable narration is **2.8 words per second**, and visuals need room to
breathe, so the budget for 3:00 is **about 500 spoken words.** This script now holds **488**, at
2.7 w/s, with no beat above 2.9. Each heading carries its own budget, and
`python scripts_check_demo_timing.py` fails if the beats stop being contiguous, stop summing to
180 seconds, drift above 3.0 w/s, stop matching the word counts in their headings, or stop
matching the three figures in this very paragraph — which had already drifted to 464 words at
2.6 w/s, because a sentence stating a total is exactly as perishable as a number in a README.

---

### 0:00–0:16 — The problem, over a real screen · 47 words

> *[Screen: KEP-6061 on GitHub — <https://github.com/kubernetes/enhancements/tree/master/keps/sig-node/6061-oci-artifact-security-profiles>
> — scrolling the README, landing on `## Alternatives`. Deliberately THIS proposal: it is the one
> the 0:56 beat retrieves, so the opening shot pays off twice. Measured 18,241 words, with six
> named rejected options under that heading, all six of them nodes in the graph.]*
>
> "A Kubernetes design proposal. Eighteen thousand words. Buried inside: the options they rejected,
> and why.
>
> There are seven hundred of these. A rejected option isn't a document, so no search index holds
> it. Propose it again three years later and nobody can find out it was refused."

### 0:16–0:32 — The shallow answer, and the silence · 43 words

> *[Screen: Tombstone. Click the shallow who-owns chip for
> staging/src/k8s.io/apiserver/pkg/endpoints/metrics.]*
>
> "So: who owns this part of the codebase?
>
> Nothing. And notice what it does instead of guessing — it tells you what it searched, and that
> an empty result is not proof. A plausible wrong name here would be worse than no answer."

*On screen the badge reads `NOT_IN_GRAPH`, and the coverage line names 681 decisions and 585
ownership files.*

### 0:32–0:56 — The same question, four hops deep · 61 words

> *[Click chip **2**, "…now ask the graph properly (4 hops)". The SVG path draws.]*
>
> "Same question. Four hops.
>
> Nobody named on that file still holds approval authority. But now it can tell you who they were
> and what they decided elsewhere. logicalhan shaped six decisions, and personally rejected an
> alternative titled: Doing nothing is a viable alternative.
>
> That's the path the answer came from — the nodes the query walked, not a summary written after."

### 0:56–1:14 — The question you cannot ask a search box · 52 words

> *[Type the question into the box and press Ask. This instance has no API key.]*
>
> "This is the question the whole thing exists for. Has anyone tried this before?
>
> No API key - routed locally, by meaning, against a fixed list of tools.
>
> The nearest is KEP-6061 - it considered pulling profile artifacts into the kubelet and rejected
> it. Author's own words, and the distance: nothing bounded this."

### 1:14–1:25 — Fork the graph and ask what breaks · 25 words

> *[Click "What if the apiserver reviewers all stepped back?". Let the picture draw.]*
>
> "Now the forward-looking one. Fork the graph, delete their approvals, re-run, drop the copy.
>
> One area loses its last approver. The others inherit coverage upward."

### 1:25–1:43 — The answer no search engine can give · 52 words

> *[Click "Whose stepping back cost the most connective authority?".]*
>
> "This one no amount of search can produce.
>
> Not who owned the most files — betweenness centrality, whole graph, inside the request.
>
> The honest part is on the page: this one is sampled. Compute it exactly and the order changes.
> I'd rather show that than a ranking I can't defend."

### 1:43–2:17 — It drafts two fixes, and refuses the third · 100 words

> *[Click chip **3**, "Draft the fix — don't just report it".]*
>
> "It answered. Now it acts - and then stops.
>
> Kubernetes records when someone steps back: emeritus approvers. Three are recorded that way,
> while another file still calls them active.
>
> So it drafts two patches. Real diffs - it does not apply them.
>
> The third it refuses, and that is the point: the handle isn't in the file. An alias expands to
> them, so no edit here removes it.
>
> The strongest signal never reaches this screen: emeritus in twenty files, approver in one -
> that file is vendored, dropped in the Cypher.
>
> Patching all of it would be wrong three ways."

*On screen: `2 OWNERS patches drafted from the graph, 1 candidate refused with a reason`. Both
drafts are committed under `docs/patches/`, so a judge can read them without running anything.*

### 2:17–2:31 — It remembers, and the memory is in the graph · 39 words

> *[Click "Has this graph been asked this before?".]*
>
> "Everything I asked got written back into the same graph — as a node citing the exact records the
> answer came from. A new session, asking differently, finds it.
>
> One query can start in memory and end in facts."

### 2:31–2:47 — Remove the database · 37 words

> *[Terminal beside the browser: stop the falkordb container, then refresh the page.]*
>
> "The rules say if it still works without the graph, the graph was decoration.
>
> No in-memory mirror, no cached answer anywhere in this repo. It stops, and it says why. There is
> a test asserting exactly this."

*The header goes red and the next question returns `DEGRADED`.*

### 2:47–3:00 — Close · 33 words

> "Seven hundred real decisions, from Kubernetes' own public record. Every number in the README has
> a script that re-checks it against the live graph.
>
> Tombstone. The decisions your org already made, and forgot."

---

## Recording checklist

- Browser at 1280×800, **dark mode**, zoom 110% so text is legible after compression.
- Hide bookmarks bar, close other tabs, clear notifications.
- Pre-click every chip once before recording so nothing is cold — including "Draft the fix", which loads the committed snapshot on first call.
- **Then `./run.sh --forget`, and only then hit record.** Pre-clicking warms the caches, but
  answering also *records* the answer, so without this every chip on camera comes back
  `ANSWERED_FROM_MEMORY`, noted "Asked before (1x, last …)" with a timestamp from before the take.
  The 2:17 beat is the one that breaks worst: its line is that everything you asked got written
  back into this graph, and a warm memory makes it cite answers the viewer never saw you ask. A
  judge opening the Space gets a cold graph, so the video has to show one. Measured: cold gives
  `ANSWERED_WITH_PATH`, a second ask gives `ANSWERED_FROM_MEMORY`, and `--forget` puts it back.
- **Do not clear memory again mid-take.** The 2:17 beat has nothing to recall unless the 0:32 beat
  ran earlier in the *same* recording — the chip asks a deliberate rewording of it, so the memory
  it finds must be one the viewer watched you create. Replayed cold in beat order, 0:16 gives
  `NOT_IN_GRAPH`, 0:32 and 1:25 give `ANSWERED_WITH_PATH`, and 2:17 returns the 0:32 question under
  its other wording. Record the beats in the order they are written.
- The `docker stop` beat needs a second terminal already open and positioned.
- Export at 1080p. **Do not** ship a watermarked export — finish in iMovie (free, preinstalled) if
  the editor would stamp it.
- Upload unlisted on YouTube, then **open the link in a private window** to confirm it plays without
  a sign-in.

## What is deliberately NOT in this video

- No architecture diagram. Judges see the product first or they stop watching.
- No stack list. It is in the README.
- No multi-tenancy benchmark. It is a strong result but it is not what Track 3 asks for, and it
  would cost 20 seconds this script does not have.
- **No "who decided this is still here" line on the rejected-option beat.** It was the third
  paragraph of that beat and it cost ten seconds, which bought the GRAPH.COPY beat instead. The
  trade is deliberate: that line restates a point the four-hop beat already makes, while forking
  the graph to ask what breaks is the one thing on screen that no other database in this field
  does, and it is now the clearest picture in the product.
- **No standalone "honest negative" beat.** It used to sit at 1:58 and it was cut to make room for
  the drafting action. Nothing was lost: the 0:16 beat already shows `NOT_IN_GRAPH` with the
  coverage line, and the two refusals in the drafting beat make the same argument on a harder
  case — refusing to patch the single strongest signal in the corpus is a better demonstration of
  restraint than refusing to answer a question about COBOL.
