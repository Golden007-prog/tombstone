# Demo video — 3 minutes, hard cap

**3 minutes, self-imposed.** The hackathon publishes no video-length rule — I looked, and there
isn't one on the event page, the rules page or the kickoff blog. Three minutes is simply what
general hackathon-judging advice converges on (MLH, Devpost), and a judge watching dozens of
entries will thank you for it. Plain screen recording, product first, no architecture diagram:
no title card, no "hi everyone", no stack slide. The first frame is the product and the first
sentence is the problem.

Record the voiceover **separately** from the screen capture and lay them together. Narrating live
while driving the UI is the single biggest cause of ten retakes at midnight.

---

### 0:00–0:18 — The problem, over a real screen

> *[Screen: the Kubernetes enhancements repo on GitHub, scrolling a long KEP README, landing on an
> "Alternatives" section.]*
>
> "This is a design proposal in Kubernetes. Four thousand words. Buried in it is a section called
> Alternatives — the things they considered and rejected, and why.
>
> There are seven hundred of these documents. That rejected option is not a document, so it is not
> in any search index. Which means when someone proposes the same idea three years later, nobody
> can find out that it was already refused, or who refused it."

### 0:18–0:38 — The shallow answer, and the silence

> *[Screen: Tombstone. Click "Who owns staging/src/k8s.io/apiserver/pkg/endpoints/metrics? (shallow)".]*
>
> "So let's ask an ordinary question. Who owns this part of the codebase?
>
> Nothing. Zero rows. And notice what it says instead of guessing — it tells you what it actually
> searched, and that an empty result is not proof. A plausible wrong name here would be worse than
> no answer."

*On screen the badge reads `NOT_IN_GRAPH`, and the coverage line names 679 decisions and 585
ownership files.*

### 0:38–1:05 — The same question, four hops deep

> *[Click "…now ask the graph properly (4 hops)". The SVG path draws.]*
>
> "Same question. Four hops.
>
> It is orphaned — no recorded owner still holds approval authority. And now it can tell you who they were, and what
> they decided elsewhere. gmarek shaped KEP-383, and personally rejected this alternative:
> *Leaving Current Dedup Mechanism but Improve Backoff Behavior*.
>
> That is the path the answer came from. Not a summary a model wrote afterwards — the nodes and
> edges the query actually walked."

### 1:05–1:33 — The question you cannot ask a search box

> *[Click "Has anyone tried moving this into the kubelet?"]*
>
> "Here is the question this whole thing exists for. Has anyone tried this before?
>
> Yes. KEP-6061 considered pulling profile artifacts into the kubelet and rejected it — and here is
> the recorded reason, in the author's own words. It also tells me whether anyone who made that call
> still approves anything in this project. Because a rationale whose authors no longer hold authority over it is a different
> kind of risk."

### 1:33–1:58 — The answer no search engine can give

> *[Click "Whose departure cost the most knowledge?"]*
>
> "And this one is my favourite, because no amount of search can produce it.
>
> This is not who owned the most files. It is **betweenness centrality** — who was the structural
> bridge between groups that otherwise did not talk. lavalamp scores highest and left thirty-one
> areas behind. Losing a bridge costs more than losing a maintainer.
>
> That number is a whole-graph property. There is no SQL query and no embedding that produces it.
> It took under twenty milliseconds, inside the request."

### 1:58–2:14 — The honest negative

> *[Click "Ask something it cannot know".]*
>
> "One more. Something it genuinely cannot know.
>
> It says so. It tells me what it searched, and it says an empty traversal is not proof it never
> happened. An agent that only ever answers is an agent you cannot trust when it matters."

### 2:14–2:32 — It remembers, and the memory is in the graph

> *[Click "Has this graph been asked this before?"]*
>
> "Everything I just asked got written back into the same graph — not as text, but as a node that
> cites the exact records the answer came from. So a new session, asking it differently, finds it.
>
> And because the memory lives in the graph, one query can start in memory and end in facts.
> A cache cannot do that."

### 2:32–2:52 — Remove the database

> *[Terminal, side by side with the browser: `docker stop falkordb`. Refresh the page.]*
>
> "The rules say if the product still works without the graph, the graph was decoration. So:
>
> *[FalkorDB down. The header goes red. Ask a question — `DEGRADED`.]*
>
> There is no in-memory mirror and no cached answer anywhere in this repo. It stops, and it says why.
> There is a test that asserts exactly this."

### 2:52–3:00 — Close

> "Seven hundred real decisions, Kubernetes' own public record. Every number in the README has a
> script that re-checks it against the live graph.
>
> Tombstone. The decisions your org already made, and forgot."

---

## Recording checklist

- Browser at 1280×800, **dark mode**, zoom 110% so text is legible after compression.
- Hide bookmarks bar, close other tabs, clear notifications.
- Pre-click every chip once before recording so nothing is cold.
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
