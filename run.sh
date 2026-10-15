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
echo "using $PY ($("$PY" --version 2>&1))"

if ! "$PY" -c "import falkordb, fastembed, fastapi" 2>/dev/null; then
  echo "Dependencies missing. Run:  $PY -m pip install -r requirements.txt" >&2
  exit 1
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
