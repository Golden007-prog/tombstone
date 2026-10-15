# walkthrough-silent.mp4

A 50-second captioned walkthrough of six beats, every frame a real headless screenshot of the
running app — no mockups and no reconstruction.

**It is not the submission video.** That needs narration, per [`../DEMO-SCRIPT.md`](../DEMO-SCRIPT.md),
which is written and timed to 3:00. This exists so there is something showing the product working
even if the recording slips, and so the beats are proven to land visually.

## Regenerating it

```bash
./run.sh                                   # in another shell
python scripts_build_walkthrough.py
```

The script captures each frame through the deep links the UI supports (`?run=<tool>&focus=1`), so
it screenshots the real app rather than a mock, and **fails loudly if the app is not serving**
instead of quietly shipping a stale video. The earlier cut of this file was assembled by hand and
its pipeline was never committed — this README used to point at "the ffmpeg pipeline in the commit
that added this file", and that commit contained only the .mp4.

| beat | what it shows |
|---|---|
| 1 | the shallow question returning `NOT_IN_GRAPH`, with what was searched |
| 2 | the same question four hops deep — who held it, and what they decided elsewhere |
| 3 | "has this been tried?" — the rejected option, its reason, and whether a decider still has authority |
| 4 | **the action**: a real OWNERS patch drafted from the graph and written to disk |
| 5 | **the refusals** — the handle that is not in the file at all, because an alias expands to it |
| 6 | betweenness centrality: whose stepping back cost the most connective authority |

One trap worth keeping written down: ffmpeg's `drawtext` **silently drops** a line containing an
unescaped `%`, with no error. That is how "72%" vanished from a caption in the first cut. The
build script asserts on it rather than trusting anyone to remember.
