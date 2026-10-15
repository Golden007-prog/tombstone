#!/usr/bin/env bash
# Start FalkorDB, seed it from the committed snapshot, and serve the app.
set -euo pipefail
cd "$(dirname "$0")"

docker compose up -d
echo "waiting for FalkorDB on 6380…"
for i in $(seq 1 30); do
  if docker exec falkordb redis-cli PING >/dev/null 2>&1; then break; fi
  sleep 1
done

export PYTHONPATH="${PYTHONPATH:-}:$(pwd)/src"
python -c "
from tombstone.snapshot import load
from tombstone.build import build
import time
t0=time.perf_counter()
st=build(load())
print(f'seeded in {time.perf_counter()-t0:.2f}s:', {k:v for k,v in st.items() if isinstance(v,int)})
"
exec python -m uvicorn tombstone.server:app --host 0.0.0.0 --port "${PORT:-8099}"
