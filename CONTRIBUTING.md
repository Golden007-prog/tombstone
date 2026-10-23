# Contributing

Thanks for looking. This file exists because an honest audit of this repository said it was
hostile to newcomers — not by intent, by construction. There is a push gate with ten checks, a
preflight with twenty-four more, 190 tests, and artefact fingerprints that fail the build if you
touch `agent.py` without regenerating a *video*. All of that is deliberate and all of it is
undocumented, which is a bad combination. So here is the map.

**The short version:** make your change, run `./preflight.sh --quick`, open the PR. If a gate
fails and you cannot tell why, say so in the PR — a gate whose failure message does not explain
itself is a bug in the gate, and fixing that is a welcome contribution in its own right.

---

## Your first fifteen minutes, with no Docker

```bash
git clone https://github.com/aviralgarg05/tombstone.git
cd tombstone
python3 -m venv .venv && ./.venv/bin/pip install -r requirements.txt
./preflight.sh --quick
```

`--quick` runs the eight checks that need nothing but this repository — no FalkorDB, no Docker,
no Chrome, no seeded graph. It prints what it did **not** run, because a green verdict over a
third of the suite would be a lie, and this project's whole argument is about not telling those.

That is enough to work on documentation, the check scripts, the corpus parser, or anything under
`web/`.

## The full environment, when you need the graph

```bash
./run.sh                 # starts FalkorDB in Docker, seeds the graph, serves on :8099
./preflight.sh           # in another shell, with the app running
```

`run.sh` is careful about interpreters: Python **3.11–3.14** only, because `fastembed` needs
`onnxruntime`, which publishes no wheel outside that range. If there is no `.venv` it builds one;
if the interpreter it finds already has the dependencies it uses that instead and builds nothing
— so on some machines `./.venv/bin/python` will not exist, and `PY=$(which python3) ./run.sh` is
the way through.

First run downloads the embedding model (BGE-small, ~67 MB) and takes a minute. After that the
graph seeds from the committed snapshot in about 1.5 seconds.

---

## Where things are

```
src/tombstone/
  tools.py          the 13 tools. One hand-written Cypher constant each, no query built by
                    string concatenation, ever. 775 lines and the heart of the project.
  agent.py          routing, dispatch, the answer shapes, the drafting action. The HTTP trust
                    boundary lives in `dispatch` — it strips filesystem arguments.
  build.py          snapshot -> graph. Indexes, constraints, vectors.
  corpus.py         raw Kubernetes markdown -> structured records. The extraction logic.
  server.py         FastAPI. ~8 endpoints, one of them the public read path.
  memory.py         answers written back as (:Answer) nodes that CITE what they were built from.
  route.py          the keyless router: embedding similarity over a fixed tool catalogue.
  counterfactual.py GRAPH.COPY, mutate the copy, diff, drop it.
  embedding.py      one embed at a time, process-wide. Read the docstring before touching it.
src/graphkit/
  ingest.py         generic two-phase FalkorDB loader. No Kubernetes in it at all.
web/                three files: index.html, app.js, style.css. No framework, no build step.
tests/              190 invariants, each one locking in a bug that actually happened.
scripts_check_*.py  the gates. Most have a --self-test that proves they can still fail.
docs/               GROUND-TRUTH.md is the list of things this project got wrong and corrected.
```

If you read one file first, read [`docs/GROUND-TRUTH.md`](docs/GROUND-TRUTH.md). It is the
catalogue of defects this codebase has actually shipped and the shape of each one. Most of the
gates exist because of an entry in there.

---

## The rules that are not obvious

**Every number in the documentation is checked against something.** Graph counts come from the
live graph, test counts from `pytest --collect-only`, the video's size from the file on disk.
If you change a count, a gate will catch the stale copy — that is the gate working, not you
breaking something. `scripts_check_doc_counts.py` is usually the one that notices.

**Queries are fixed text with parameters.** Never interpolate a user value into Cypher. There is
a test (`test_cypher_injection_is_structurally_impossible`) that will fail if you do.

**Answers have shapes, and the shapes mean specific things.** `NOT_IN_GRAPH` means "I looked and
there is nothing." `UNKNOWN_ENTITY` means "that is a bad request, I did not traverse."
`DEGRADED` means "no answer was produced." Do not reach for `DEGRADED` to report a malformed
argument — that conflates a bad request with the database being gone, and it was a real bug here.

**Embedding is serialised on purpose.** One `embed` at a time, process-wide. A second concurrent
one costs ~119 MiB of ONNX arena and the hosted demo gets killed at 512 MB. `src/tombstone/
embedding.py` explains it; a test enforces it; a source scan stops new call sites bypassing it.

**A check that cannot run must say so, never pass.** Several gates have a `--self-test` that
mutates a known-good input and requires the check to catch it. If you add a gate, add that too —
this repository has shipped three checks that silently verified nothing.

**Artefacts are fingerprinted.** The screenshots, the GIF and the walkthrough video record the
hashes of the source files they were generated from. Change `agent.py` or `web/app.js` and
`scripts_check_shots_fresh.py` will tell you to regenerate them:

```bash
CHROME="/path/to/chrome" ./.venv/bin/python scripts_gen_readme_shots.py
./.venv/bin/python scripts_gen_depth_gif.py
./.venv/bin/python scripts_build_walkthrough.py
```

If you do not have Chrome, say so in the PR and leave them — a maintainer can regenerate.

---

## Opening a pull request

1. Branch from `main`.
2. `./preflight.sh --quick` at minimum. The full `./preflight.sh` if you have the graph up.
3. If you changed behaviour, add a test that **fails before your change**. Say in the PR that you
   checked it fails — that sentence is worth more than the test.
4. Describe what you measured, not what you believe. "Reproduced with X, got Y" beats "should be
   faster now."
5. Small PRs. A 2,000-line PR will sit unreviewed; a 40-line one with a test gets merged.

Commit messages here are long and explain *why*, often including what was wrong before. You do
not have to match that, but if you know why your change is needed, write it down.

### What will get a PR rejected

- A claim added to the documentation with nothing checking it
- A gate weakened or deleted to make a change pass
- A new query built by string concatenation
- An LLM introduced into a path that currently answers with hand-written Cypher — the project's
  argument is that the graph answers and the model only picks a tool

---

## Good places to start

Issues labelled [`good first issue`](https://github.com/aviralgarg05/tombstone/issues?q=is%3Aissue+is%3Aopen+label%3A%22good+first+issue%22)
are scoped, name the files involved, and say which gate has to pass. Difficulty labels
(`difficulty:easy` / `medium` / `hard`) mark roughly how much of the codebase you need in your
head.

If an issue is unclear, comment and ask. If you want to work on one, say so on the issue first —
not to reserve it formally, just so two people do not do the same work.

## Something you want to build that is not an issue

Open an issue describing it before writing the code, especially for anything that adds a
dependency, a model call, or a new data source. The project has strong opinions about all three
and it is cheaper to find out before you have written it.

---

## Code of conduct

Be decent. Assume the other person is trying. Disagree about the work, not the person.
Harassment of any kind means you are done here.
