#!/usr/bin/env bash
# Everything this submission claims, checked in one command.
#
# The checks accumulated one at a time, each after something went wrong, and by the end there
# were eight scripts that had to be run in the right order with the app already serving. That is
# fine while building and bad at a deadline, which is exactly when you most want to know whether
# anything has drifted. So: one command, one verdict.
#
# CI runs most of this set on every push, but the two lists differ in BOTH directions, and the
# header used to claim they were the same. Four checks here run in no workflow at all --
# bench_memory_growth.py, bench_index_scope.py, scripts_check_shots_fresh.py and
# scripts_check_verification_claims.py -- and CI adds what is too slow or too stateful for a
# laptop: bench_vs_networkx.py, eval_graph_vs_text.py --dense, a docker build, the quickstart
# against a deliberately colliding container, and the install on 3.11 and 3.14. So a green run
# here does not predict a green CI. It is the fastest way to catch local drift before pushing,
# which is what it is actually for.
#
# Usage:  ./run.sh    (in another shell, so the app is serving)
#         ./preflight.sh
#         ./preflight.sh --quick     (no app, no Docker, no Chrome, no graph)
#
# --quick exists for a contributor's first hour. The full run needs FalkorDB serving, the app on
# 8099, headless Chrome and a seeded graph, and someone who has just cloned this has none of
# those -- so their first experience of the project was a red wall that said nothing about their
# change. --quick runs the checks that need nothing but this repository, which is the same set
# the push gate runs, and it NAMES what it skipped rather than printing a green verdict over a
# third of the suite. It is not a substitute: a green --quick does not mean a green preflight.
set -uo pipefail
cd "$(dirname "$0")"

# Same interpreter rule as run.sh: prefer the venv the README tells you to create, then an
# active one, then python3. PY can be set explicitly for an environment that keeps its venv
# somewhere else.
if   [ -n "${PY:-}" ];              then :
elif [ -x ".venv/bin/python" ];     then PY=".venv/bin/python"
elif [ -n "${VIRTUAL_ENV:-}" ];     then PY="$VIRTUAL_ENV/bin/python"
else PY="$(command -v python3)"; fi
export PYTHONPATH="${PYTHONPATH:-}:$(pwd)/src"

# Python 3.15 cannot run this. fastembed needs onnxruntime, and onnxruntime publishes wheels for
# cp311 through cp314 only, so `pip install -r requirements.txt` fails with ResolutionImpossible
# and a wall of version lines that never mention Python. Found by cloning fresh on a machine whose
# default python3 had moved to 3.15: the documented quickstart simply did not work, and said so in
# the least useful way available.
ver="$("$PY" -c 'import sys; print("%d.%d" % sys.version_info[:2])' 2>/dev/null || echo 0.0)"
major="${ver%%.*}"; minor="${ver#*.}"
if [ "$major" != "3" ] || [ "$minor" -lt 11 ] || [ "$minor" -gt 14 ]; then
  echo "This needs Python 3.11-3.14; $PY is $ver." >&2
  echo "  fastembed depends on onnxruntime, which has no wheel outside that range." >&2
  for cand in python3.14 python3.13 python3.12 python3.11; do
    if command -v "$cand" >/dev/null; then
      echo "  You have $cand. Create the venv with it:" >&2
      echo "      rm -rf .venv && $cand -m venv .venv && ./.venv/bin/pip install -r requirements.txt" >&2
      exit 1
    fi
  done
  echo "  Install one of 3.11-3.14, or use Docker: see DEPLOY.md" >&2
  exit 1
fi


# Fail on the cause, not fourteen times on the symptom. Without this, a missing venv produces
# fourteen identical ModuleNotFoundError traces and buries the one line that matters.
if ! "$PY" -c "import falkordb, fastembed, fastapi, pytest" 2>/dev/null; then
  echo "  $PY cannot import this project's dependencies." >&2
  echo >&2
  echo "  Create the venv the README describes:" >&2
  echo "      python3 -m venv .venv && ./.venv/bin/pip install -r requirements.txt" >&2
  echo "  or point this at an existing one:" >&2
  echo "      PY=/path/to/python ./preflight.sh" >&2
  exit 1
fi

QUICK=0
for arg in "$@"; do
  case "$arg" in
    --quick) QUICK=1 ;;
    -h|--help) sed -n '1,30p' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
    *) echo "unknown argument: $arg (try --quick, or --help)" >&2; exit 2 ;;
  esac
done

pass=0; fail=0; skip=0; failed=()

# A check that cannot run here must say so -- never pass, and never read as a product failure.
# scripts_check_ui.py drives real headless Chrome, and on a machine without Chrome it exits 1, so
# "one command, one verdict" printed a red FAIL for an environmental reason no document mentioned.
# The escape hatch (UI_CHECK_OPTIONAL) existed in exactly one line of code and nowhere in the
# docs. CI structurally cannot see this, because GitHub's runners ship Chrome. Same shape as the
# pre-push hook's SKIP when no interpreter has pyyaml.
skip_if_missing() {   # skip_if_missing <label> <reason> <probe-command...>
  local label="$1" reason="$2"; shift 2
  if "$@" >/dev/null 2>&1; then return 1; fi
  printf '  \033[33mSKIP\033[0m  %s\n' "$label"
  printf '          %s\n' "$reason"
  skip=$((skip + 1)); return 0
}

run() {   # run <label> <command...>
  local label="$1"; shift
  local out
  if out="$("$@" 2>&1)"; then
    printf '  \033[32mok\033[0m    %s\n' "$label"
    pass=$((pass + 1))
  else
    printf '  \033[31mFAIL\033[0m  %s\n' "$label"
    printf '%s\n' "$out" | tail -6 | sed 's/^/          /'
    fail=$((fail + 1)); failed+=("$label")
  fi
}

echo "checking everything this submission claims"
echo

if [ "$QUICK" -eq 1 ]; then
  echo "  --quick: the checks that need nothing but this repository."
  echo
  run "the demo script is speakable"          python3 scripts_check_demo_timing.py
  run "the narration cut matches the script"  python3 scripts_build_narration.py --check
  run "SUBMISSION.md's stated lengths"        python3 scripts_check_submission_lengths.py
  run "committed artefacts match the code"    python3 scripts_check_shots_fresh.py --hashes-only
  run "drafted/refused counts match the verified run" python3 scripts_check_action_counts.py
  run "that count checker can still fail"     python3 scripts_check_action_counts.py --self-test
  run "FINISH.md matches what the deploy will upload" python3 scripts_check_deploy_size.py
  run "no universal claims about checking"    "$PY" scripts_check_verification_claims.py
  echo
  echo "  NOT run, because they need a live graph, the app on 8099, or Chrome:"
  echo "    the invariants (190 tests) · every README number against the graph · the drafting"
  echo "    action's claims · the memory claims · retrieval · the keyless router · the text"
  echo "    baseline · every rendered UI state · the data model · both benchmarks · the Cypher"
  echo "    catalogue. That is most of the suite, and a green run here does not predict them."
  echo
  if [ "$fail" -eq 0 ]; then
    printf '  \033[32m%d quick checks passed.\033[0m Run ./run.sh then ./preflight.sh for the rest.\n' "$pass"
    exit 0
  fi
  printf '  \033[31m%d of %d quick checks failed:\033[0m %s\n' "$fail" "$((pass + fail))" "${failed[*]}"
  exit 1
fi

if ! curl -sf -m 5 http://localhost:8099/api/health >/dev/null 2>&1; then
  echo "  the app is not serving on 8099. Start it with ./run.sh in another shell."
  echo "  (the UI, demo-script and README-output checks all drive the live app)"
  echo "  No graph yet? ./preflight.sh --quick runs what needs nothing but this repository."
  exit 1
fi

run "the invariants"                       "$PY" -m pytest tests/ -q
run "the graph against the raw corpus"  "$PY" eval_gold.py
run "every README number, against the graph" "$PY" verify_claims.py
run "the drafting action's own claims"     "$PY" verify_action.py
run "the memory claims"                    "$PY" verify_memory.py
run "retrieval, with negative controls"    "$PY" eval_retrieval.py
run "the keyless router, on held-out language" "$PY" eval_router.py
run "graph against a text baseline"        "$PY" eval_graph_vs_text.py
if ! skip_if_missing "every rendered answer state" \
      "needs headless Chrome, which is not on this machine. Everything else still ran; CI checks
          this one on every push, on a runner that has Chrome. Set CHROME=/path/to/chrome to run
          it here." \
      "$PY" -c 'import sys; sys.path.insert(0, "."); import scripts_check_ui as u; sys.exit(0 if u.CHROME else 1)'; then
  run "every rendered answer state"        "$PY" scripts_check_ui.py
fi
run "the README's printed output"          "$PY" scripts_check_readme_examples.py
# Not read-only, and the label says so because run() swallows a passing check's stdout. Beat 7
# is the memory beat, and the only way to prove the recall comes from the demo's OWN beats is to
# replay them against an empty memory -- so this clears every remembered answer first. Total
# rather than scoped, because recall is a nearest-neighbour query and a row left by an earlier
# session could satisfy the beat without the demo having recorded anything.
run "the demo script's facts (clears remembered answers)" "$PY" scripts_check_demo_facts.py
run "the demo script's timing"             "$PY" scripts_check_demo_timing.py
run "the premise measurement"              "$PY" measure_repeat_rejections.py
run "GRAPH.COPY carries the whole graph"   "$PY" bench_copy.py
# The memory-growth figure the README states was measured by a script that ran in no gate
# at all, so its reconciliation against the page only happened when someone remembered.
# It cleans up the rows it writes, which is what makes it safe to run here.
run "what the agent's memory costs to keep" "$PY" bench_memory_growth.py
run "why the search index excludes 206 nodes" "$PY" bench_index_scope.py
run "the blog post's claims"               "$PY" verify_blog.py
run "corpus counts across every doc"       "$PY" scripts_check_doc_counts.py
# Rule 10 asks for the data model, and the README block that IS that deliverable was the
# one schema description nobody re-derived -- it had drifted to missing INHERITS_FROM, the
# edge every ownership answer walks. Checked the same way its sibling table already was.
run "the data model matches the live graph" "$PY" scripts_check_data_model.py
run "the README renders on GitHub"         "$PY" scripts_check_markdown_renders.py
run "no universal claims about checking" "$PY" scripts_check_verification_claims.py
run "artefacts match the code and corpus"  "$PY" scripts_check_shots_fresh.py
run "the principles table matches the code" "$PY" scripts_check_principles.py

# The Cypher catalogue is generated; drift means the README shows queries that no longer run.
if "$PY" scripts_gen_readme_cypher.py > /tmp/preflight-cypher.md 2>/dev/null \
   && "$PY" - <<'PY' >/dev/null 2>&1
import re, sys
readme = open("README.md").read(); gen = open("/tmp/preflight-cypher.md").read()
start = readme.index("## The Cypher this product depends on")
m = re.search(r"^## ", readme[start + 10:], flags=re.M)
end = start + 10 + m.start() if m else len(readme)
sys.exit(0 if gen.strip() == readme[start:end].strip() else 1)
PY
then
  printf '  \033[32mok\033[0m    the README Cypher matches the source\n'; pass=$((pass + 1))
else
  printf '  \033[31mFAIL\033[0m  the README Cypher has drifted from tools.py\n'
  fail=$((fail + 1)); failed+=("Cypher drift")
fi

echo
if [ "$fail" -eq 0 ]; then
  # Skips are named in the verdict rather than folded into the pass count, because "23 checks
  # passed" over 22 that ran is the kind of quietly-wrong number this whole file exists to catch.
  if [ "$skip" -gt 0 ]; then
    printf '  \033[32m%d checks passed\033[0m, \033[33m%d skipped\033[0m (named above, each with its reason).\n' "$pass" "$skip"
  else
    printf '  \033[32m%d checks passed.\033[0m Deploy with ./scripts_verify_deploy.sh then ./deploy_hf.sh\n' "$pass"
  fi
else
  printf '  \033[31m%d of %d failed:\033[0m %s\n' "$fail" "$((pass + fail))" "${failed[*]}"
fi
exit "$([ "$fail" -eq 0 ] && echo 0 || echo 1)"
