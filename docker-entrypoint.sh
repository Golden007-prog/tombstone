#!/usr/bin/env bash
# Start FalkorDB in the background, seed the graph, then hand the foreground to the web server.
set -euo pipefail

# RESULTSET_SIZE 10000 silently truncates large returns; TIMEOUT 1000 kills any algorithm call
# over a second; MAX_QUEUED_QUERIES 25 rejects most of a concurrent workload. All three are
# baked into the base image, so all three are overridden here.
redis-server \
  --loadmodule /var/lib/falkordb/bin/falkordb.so \
      RESULTSET_SIZE 1000000 TIMEOUT 0 MAX_QUEUED_QUERIES 4096 THREAD_COUNT 4 \
  --port 6379 --daemonize no --save '' --appendonly no &
FALKOR_PID=$!

echo "waiting for FalkorDB…"
for i in $(seq 1 40); do
  if redis-cli PING >/dev/null 2>&1; then echo "FalkorDB up after ${i}s"; break; fi
  sleep 1
done

# The graph is rebuilt from the committed snapshot on every boot. Nothing persists, nothing to
# restore, and the container is identical whether it is 10 seconds or 10 days old.
python - <<'PY'
import time
from tombstone.snapshot import load
from tombstone.build import build
t0 = time.perf_counter()
st = build(load())
print(f"seeded in {time.perf_counter()-t0:.2f}s: "
      f"{st['Kep']} decisions, {st.get('NamedOption')} named options, "
      f"{st['Person']} people, {st.get('vectors_loaded')} vectors", flush=True)
PY

trap 'kill $FALKOR_PID 2>/dev/null' EXIT
exec python -m uvicorn tombstone.server:app --host 0.0.0.0 --port "${PORT:-8099}"
