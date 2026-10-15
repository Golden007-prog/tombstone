#!/usr/bin/env bash
# Everything this submission claims, checked in one command.
#
# The checks accumulated one at a time, each after something went wrong, and by the end there
# were eight scripts that had to be run in the right order with the app already serving. That is
# fine while building and bad at a deadline, which is exactly when you most want to know whether
# anything has drifted. So: one command, one verdict.
#
# This is the same set CI runs on every push. Running it locally first means a red CI is a
# surprise rather than the way you find out.
#
# Usage:  ./run.sh    (in another shell, so the app is serving)
#         ./preflight.sh
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

pass=0; fail=0; failed=()

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

if ! curl -sf -m 5 http://localhost:8099/api/health >/dev/null 2>&1; then
  echo "  the app is not serving on 8099. Start it with ./run.sh in another shell."
  echo "  (the UI, demo-script and README-output checks all drive the live app)"
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
run "every rendered answer state"          "$PY" scripts_check_ui.py
run "the README's printed output"          "$PY" scripts_check_readme_examples.py
run "the demo script's facts"              "$PY" scripts_check_demo_facts.py
run "the demo script's timing"             python3 scripts_check_demo_timing.py
run "the premise measurement"              "$PY" measure_repeat_rejections.py
run "GRAPH.COPY carries the whole graph"   "$PY" bench_copy.py
run "the blog post's claims"               "$PY" verify_blog.py
run "corpus counts across every doc"       "$PY" scripts_check_doc_counts.py
run "the README renders on GitHub"         "$PY" scripts_check_markdown_renders.py
run "the principles table matches the code" "$PY" scripts_check_principles.py

# The Cypher catalogue is generated; drift means the README shows queries that no longer run.
if "$PY" scripts_gen_readme_cypher.py > /tmp/preflight-cypher.md 2>/dev/null \
   && "$PY" - <<'PY' >/dev/null 2>&1
import re, sys
readme = open("README.md").read(); gen = open("/tmp/preflight-cypher.md").read()
start = readme.index("## The Cypher this product depends on")
m = re.search(r"^## ", readme[start + 10:], flags=re.M)
end = start + 10 + m.start() if m else len(readme)
sys.exit(0 if gen.strip() in readme[start:end].strip() else 1)
PY
then
  printf '  \033[32mok\033[0m    the README Cypher matches the source\n'; pass=$((pass + 1))
else
  printf '  \033[31mFAIL\033[0m  the README Cypher has drifted from tools.py\n'
  fail=$((fail + 1)); failed+=("Cypher drift")
fi

echo
if [ "$fail" -eq 0 ]; then
  printf '  \033[32m%d checks passed.\033[0m Deploy with ./scripts_verify_deploy.sh then ./deploy_hf.sh\n' "$pass"
else
  printf '  \033[31m%d of %d failed:\033[0m %s\n' "$fail" "$((pass + fail))" "${failed[*]}"
fi
exit "$([ "$fail" -eq 0 ] && echo 0 || echo 1)"
