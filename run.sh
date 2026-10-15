#!/usr/bin/env bash
# Start FalkorDB, seed the graph from the committed snapshot, and serve the app.
set -euo pipefail
cd "$(dirname "$0")"

# Pick an interpreter the way a stranger's machine actually looks: prefer a local venv (which is
# what the README tells you to create), then python3, then python. A bare `python` is not safe --
# plenty of systems only ship python3, and on others it resolves outside the venv you just
# installed into, so the dependencies appear missing.
if   [ -x ".venv/bin/python" ];      then PY=".venv/bin/python"
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

docker compose up -d
echo "waiting for FalkorDB on 6380…"
for _ in $(seq 1 40); do
  if docker exec falkordb redis-cli PING >/dev/null 2>&1; then break; fi
  sleep 1
done
if ! docker exec falkordb redis-cli PING >/dev/null 2>&1; then
  echo "FalkorDB did not come up. Check: docker compose logs falkordb" >&2
  exit 1
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
