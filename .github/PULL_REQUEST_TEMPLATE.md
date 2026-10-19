## What this changes

<!-- One or two sentences. What was wrong or missing before. -->

## What you measured

<!-- Commands and real output, not expectations. If you added a test, say that you checked it
     FAILS without your change — that sentence is worth more than the test. -->

## Gates

- [ ] `./preflight.sh --quick` passes
- [ ] `./preflight.sh` passes (needs `./run.sh` in another shell — skip if you have no Docker, and say so)
- [ ] If behaviour changed, a test covers it and fails without this change
- [ ] If a documented number changed, every copy of it was updated (`scripts_check_doc_counts.py` finds the stale ones)
- [ ] If `agent.py`, `tools.py` or `web/` changed, artefacts regenerated — or noted here for a maintainer to do
