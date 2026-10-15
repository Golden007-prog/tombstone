# walkthrough-silent.mp4

A 67-second captioned walkthrough: a title card, seven beats, and a closing card, every frame a real headless screenshot of the
running app — no mockups and no reconstruction.

**It is not the submission video.** That needs narration, per [`../DEMO-SCRIPT.md`](../DEMO-SCRIPT.md),
which is written and timed to 3:00. This exists so there is something showing the product working
even if the recording slips, and so the beats are proven to land visually.

## Regenerating it

```bash
./run.sh                                   # in another shell
python scripts_build_walkthrough.py
```

It opens by naming the project and closes with the repository URL, because the one situation
this video exists for is somebody watching with no commentary. If `ffmpeg` on your machine cannot
start — a dependency bump can leave it linked against a dylib that no longer exists — the build
falls back to a container and says so, so regenerating does not depend on the state of a package
manager.

The script captures each frame through the deep links the UI supports (`?run=<tool>&focus=1`), so
it screenshots the real app rather than a mock, and **fails loudly if the app is not serving**
instead of quietly shipping a stale video. The earlier cut of this file was assembled by hand and
its pipeline was never committed — this README used to point at "the ffmpeg pipeline in the commit
that added this file", and that commit contained only the .mp4.

| beat | what it shows |
|---|---|
| 1 | the shallow question returning `NOT_IN_GRAPH`, with what was searched |
| 2 | the same question four hops deep — who held it, and what they decided elsewhere |
| 3 | **a typed question, on an instance with no API key** — routed locally, answered by the same Cypher |
| 4 | **the action**: a real OWNERS patch drafted from the graph and written to disk |
| 5 | **the refusals** — the handle that is not in the file at all, because an alias expands to it |
| 6 | **asked for a poem, it declines by name** rather than route into the patch-drafting tool |
| 7 | betweenness centrality: whose stepping back cost the most connective authority |

Beats 3 and 6 are captured through `?ask=<question>&focus=1`, which deep-links a free-text
question — so a question and its answer can be shared as a URL, and so the walkthrough can show
someone typing rather than only clicking.

## Why there is no staleness check on this file

The obvious one would fingerprint the sources and fail when they move, and I started writing it
before noticing it would be redundant. Every caption here states a **behaviour**, not a number --
"depth 1 returns nothing", "it refuses the handle an alias expands to", "it declines the poem by
name" -- and each of those behaviours is already asserted by a named check: the rendered-state
check covers the depth-1 refusal and the alias strand, the router's out-of-domain bucket is tested
directly, and betweenness is in the Cypher-drift check. So the way this video goes wrong is by a
check going red, not by a number drifting underneath it.

Had the captions quoted figures, the fingerprint would be worth having. They deliberately do not,
which is also why they are still true sixty-seven seconds at a time.

One trap worth keeping written down: ffmpeg's `drawtext` **silently drops** a line containing an
unescaped `%`, with no error. That is how "72%" vanished from a caption in the first cut. The
build script asserts on it rather than trusting anyone to remember.
