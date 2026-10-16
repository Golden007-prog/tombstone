#!/usr/bin/env bash
# Start FalkorDB, seed the graph from the committed snapshot, and serve the app.
set -euo pipefail
cd "$(dirname "$0")"

# Pick an interpreter the way a stranger's machine actually looks: prefer a local venv (which is
# what the README tells you to create), then python3, then python. A bare `python` is not safe --
# plenty of systems only ship python3, and on others it resolves outside the venv you just
# installed into, so the dependencies appear missing.
if   [ -n "${PY:-}" ];              then :   # honoured so a venv kept elsewhere can be named,
                                             # the same way preflight.sh accepts it
elif [ -x ".venv/bin/python" ];      then PY=".venv/bin/python"
elif [ -n "${VIRTUAL_ENV:-}" ];      then PY="$VIRTUAL_ENV/bin/python"
elif command -v python3 >/dev/null;  then PY="$(command -v python3)"
elif command -v python  >/dev/null;  then PY="$(command -v python)"
else
  echo "No Python found. Install Python 3.10+ and re-run." >&2
  exit 1
fi
# If there is no venv yet and the interpreter we found cannot run this, BUILD the venv rather
# than printing the command that would. The quickstart used to name python3.13, which fails with
# `command not found` on a machine that does not have exactly that; naming `python3` instead moves
# the failure to a ResolutionImpossible wall from pip on a machine whose python3 is 3.15. Both
# stop a stranger at the first line, before anything here can explain itself. Measured on this
# machine, which has python3 -> 3.15 and python3.13 installed: the documented command failed, and
# the help that would have fixed it lives further down this file than the reader ever got.
if [ ! -x ".venv/bin/python" ]; then
  _v="$("$PY" -c 'import sys; print("%d.%d" % sys.version_info[:2])' 2>/dev/null || echo 0.0)"
  _usable=no
  case "$_v" in
    3.11|3.12|3.13|3.14)
      # In range, but that is only half the question: a bare clone has no dependencies either.
      if "$PY" -c "import falkordb, fastembed, fastapi" 2>/dev/null; then
        _usable=yes
      else
        echo "No .venv and no dependencies yet. Building .venv with $PY."
        "$PY" -m venv .venv || exit 1
        ./.venv/bin/pip install -q -r requirements.txt || {
          echo "  pip failed inside the new .venv; the output above says why" >&2; exit 1; }
        PY=".venv/bin/python"
        _usable=yes
      fi ;;
  esac
  if [ "$_usable" = no ]; then
      for _cand in python3.13 python3.12 python3.14 python3.11; do
        command -v "$_cand" >/dev/null || continue
        echo "$PY is $_v, which cannot install this. Building .venv with $_cand instead."
        "$_cand" -m venv .venv || exit 1
        ./.venv/bin/pip install -q -r requirements.txt || {
          echo "  pip failed inside the new .venv; the output above says why" >&2; exit 1; }
        PY=".venv/bin/python"
        break
      done
  fi
fi

echo "using $PY ($("$PY" --version 2>&1))"

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


if ! "$PY" -c "import falkordb, fastembed, fastapi" 2>/dev/null; then
  echo "Dependencies missing. Run:  $PY -m pip install -r requirements.txt" >&2
  exit 1
fi

# --forget: drop the agent's remembered answers and exit, starting nothing.
#
# This exists for recording the demo. The checklist says to pre-click every chip so nothing is
# cold, and that is right -- but answering also RECORDS the answer, so on camera every pre-clicked
# chip comes back ANSWERED_FROM_MEMORY, noted "Asked before (1x, last ...)" with a timestamp from
# before you hit record. The memory beat is worse: its line is that everything asked got written
# back into this graph, and a warm memory makes it cite answers the viewer never saw asked. A judge
# opening the deployed Space gets a cold graph, so the video has to show one too.
if [ "${1:-}" = "--forget" ]; then
  PYTHONPATH=src "$PY" - <<'PYFORGET'
import os
import sys

try:
    from graphkit.ingest import connect
    graph = connect().select_graph(os.environ.get("GRAPH", "tomb:k8s"))
    # nodes_deleted comes back as a float, so 3 would print as "3.0".
    n = int(graph.query("MATCH (a:Answer) DETACH DELETE a").nodes_deleted or 0)
except Exception as exc:
    sys.exit(f"could not reach FalkorDB ({exc}).\n  Start it first:  ./run.sh")
print(f"forgot {n} remembered {'answer' if n == 1 else 'answers'}; "
      f"the next question is a first visit")
PYFORGET
  exit 0
fi

if ! command -v docker >/dev/null; then
  echo "Docker is required to run FalkorDB. Install Docker Desktop and re-run." >&2
  exit 1
fi

# Is a FalkorDB already answering on 6380? Checked over a plain socket rather than with
# `docker exec falkordb`, because that assumes WE started it and that it is called that.
#
# This matters more than it looks. The compose file fixes `container_name: falkordb`, so anyone
# who already has a FalkorDB container -- a second checkout of this repo, or simply someone who
# has used FalkorDB before, which at a FalkorDB hackathon is most people -- got:
#
#   Error response from daemon: Conflict. The container name "/falkordb" is already in use
#
# and the quickstart stopped there. Reusing a healthy instance is both the fix and the better
# behaviour: nobody wants a second database started behind their back.
ping_falkordb() {
  "$PY" - <<'PY' 2>/dev/null
import socket, sys
try:
    sock = socket.create_connection(("localhost", 6380), timeout=2)
    sock.sendall(b"PING\r\n")
    sys.exit(0 if b"PONG" in sock.recv(64) else 1)
except Exception:
    sys.exit(1)
PY
}

if ping_falkordb; then
  echo "FalkorDB is already serving on 6380 — reusing it rather than starting a second one."
else
  if ! docker compose up -d 2>/tmp/tombstone-compose.err; then
    echo "Could not start FalkorDB:" >&2
    sed 's/^/  /' /tmp/tombstone-compose.err >&2
    if grep -q 'already in use by container' /tmp/tombstone-compose.err; then
      cat >&2 <<'MSG'

  A container called "falkordb" already exists but is not serving on 6380. Either start it:
      docker start falkordb
  or remove it and let this script create a fresh one:
      docker rm -f falkordb
MSG
    fi
    exit 1
  fi
  echo "waiting for FalkorDB on 6380…"
  for _ in $(seq 1 40); do
    ping_falkordb && break
    sleep 1
  done
  if ! ping_falkordb; then
    echo "FalkorDB did not come up. Check: docker compose logs falkordb" >&2
    exit 1
  fi
fi

export PYTHONPATH="${PYTHONPATH:-}:$(pwd)/src"
"$PY" - <<'PY'
import time
from tombstone.snapshot import load
from tombstone.build import build
t0 = time.perf_counter()
st = build(load())
print(f"seeded in {time.perf_counter()-t0:.2f}s: "
      f"{st['Kep']} decisions, {st.get('NamedOption')} named options, "
      f"{st['Person']} people, {st.get('vectors_loaded')} vectors")
PY

echo
echo "  ready on http://localhost:${PORT:-8099}  (no API key needed)"
exec "$PY" -m uvicorn tombstone.server:app --host 0.0.0.0 --port "${PORT:-8099}"
