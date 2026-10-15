# Demo video — 3 minutes, hard cap

**3 minutes, self-imposed.** The hackathon publishes no video-length rule — I looked, and there
isn't one on the event page, the rules page or the kickoff blog. Three minutes is simply what
general hackathon-judging advice converges on (MLH, Devpost), and a judge watching dozens of
entries will thank you for it. Plain screen recording, product first, no architecture diagram:
no title card, no "hi everyone", no stack slide. The first frame is the product and the first
sentence is the problem.

Record the voiceover **separately** from the screen capture and lay them together. Narrating live
while driving the UI is the single biggest cause of ten retakes at midnight.

**Every beat below is written to a word budget**, because an earlier draft of this script was not.
It held 767 spoken words in 180 seconds — 4.3 words per second, which is not a narration, it is a
countdown. Read aloud it ran about 4:35, so the 3:00 cap would have been discovered at midnight
during take nine. Comfortable narration is **2.8 words per second**, and visuals need room to
breathe, so the budget for 3:00 is **about 500 spoken words.** This script now holds **464**, at
2.6 w/s, with no beat above 2.9. Each heading carries its own budget, and
`python scripts_check_demo_timing.py` fails if the beats stop being contiguous, stop summing to
180 seconds, drift above 3.0 w/s, or stop matching the word counts in their headings.

---

### 0:00–0:16 — The problem, over a real screen · 47 words

> *[Screen: the Kubernetes enhancements repo on GitHub, scrolling a long KEP README, landing on an
> Alternatives section.]*
>
> "A Kubernetes design proposal. Four thousand words. Buried inside: the options they rejected,
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

*On screen the badge reads `NOT_IN_GRAPH`, and the coverage line names 679 decisions and 585
ownership files.*

### 0:32–0:56 — The same question, four hops deep · 62 words

> *[Click the 4-hop chip. The SVG path draws.]*
>
> "Same question. Four hops.
>
> Nobody named on that file still holds approval authority. But now it can tell you who they were,
> and what they decided elsewhere. gmarek shaped KEP-383, and personally rejected an alternative
> titled Leaving Current Dedup Mechanism but Improve Backoff Behavior.
>
> That's the path the answer came from — the nodes the query walked, not a summary written after."

### 0:56–1:24 — The question you cannot ask a search box · 80 words

> *[Type the question into the box and press Ask. This instance has no API key.]*
>
> "This is the question the whole thing exists for. Has anyone tried this before?
>
> No API key here - that was routed locally, by meaning, against a fixed list of tools.
>
> Yes. KEP-6061 considered pulling profile artifacts into the kubelet, and rejected it. Here's the
> recorded reason, in the author's own words.
>
> It also tells me whether anyone who made that call still approves anything here - a rationale
> whose authors hold no authority is a different kind of risk."

### 1:24–1:42 — The answer no search engine can give · 41 words

> *[Click the whose-departure-cost-most chip.]*
>
> "This one no amount of search can produce.
>
> Not who owned the most files — betweenness centrality. Who bridged groups that otherwise didn't
> talk. lavalamp scores highest, and left thirty-one areas behind.
>
> A whole-graph property. Under twenty milliseconds, inside the request."

### 1:42–2:16 — It drafts the fix, and refuses two of them · 100 words

> *[Click the draft-the-fix chip.]*
>
> "Everything so far was the agent answering. This is it doing.
>
> Kubernetes writes down when someone steps back: emeritus approvers. Three people are recorded
> that way — while another file still lists them as an active approver.
>
> So it drafts the patch. A real diff.
>
> But the refusals are the point. The strongest signal here — emeritus in twenty files, approver
> in one — it won't touch: that file is vendored, synced from another repo.
>
> This one it can't patch at all: his handle isn't in the file. An alias expands to him.
>
> Patching all three would be wrong twice."

*On screen: `2 OWNERS patches drafted from the graph, 1 candidate refused with a reason`. Both
drafts are committed under `docs/patches/`, so a judge can read them without running anything.*

### 2:16–2:30 — It remembers, and the memory is in the graph · 39 words

> *[Click the asked-before chip.]*
>
> "Everything I asked got written back into the same graph — as a node citing the exact records the
> answer came from. A new session, asking differently, finds it.
>
> One query can start in memory and end in facts."

### 2:30–2:46 — Remove the database · 37 words

> *[Terminal beside the browser: stop the falkordb container, then refresh the page.]*
>
> "The rules say if it still works without the graph, the graph was decoration.
>
> No in-memory mirror, no cached answer anywhere in this repo. It stops, and it says why. There is
> a test asserting exactly this."

*The header goes red and the next question returns `DEGRADED`.*

### 2:46–3:00 — Close · 33 words

> "Seven hundred real decisions, from Kubernetes' own public record. Every number in the README has
> a script that re-checks it against the live graph.
>
> Tombstone. The decisions your org already made, and forgot."

---

## Recording checklist

- Browser at 1280×800, **dark mode**, zoom 110% so text is legible after compression.
- Hide bookmarks bar, close other tabs, clear notifications.
- Pre-click every chip once before recording so nothing is cold — including "Draft the fix", which loads the committed snapshot on first call.
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
- **No standalone "honest negative" beat.** It used to sit at 1:58 and it was cut to make room for
  the drafting action. Nothing was lost: the 0:16 beat already shows `NOT_IN_GRAPH` with the
  coverage line, and the two refusals in the drafting beat make the same argument on a harder
  case — refusing to patch the single strongest signal in the corpus is a better demonstration of
  restraint than refusing to answer a question about COBOL.
