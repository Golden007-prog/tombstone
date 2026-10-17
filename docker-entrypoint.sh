#!/usr/bin/env bash
# Start FalkorDB in the background, seed the graph, then hand the foreground to the web server.
set -euo pipefail

# RESULTSET_SIZE 10000 silently truncates large returns; TIMEOUT 1000 kills any algorithm call
# over a second; MAX_QUEUED_QUERIES 25 rejects most of a concurrent workload. All three are
# baked into the base image, so all three are overridden here.
redis-server \
  --loadmodule /var/lib/falkordb/bin/falkordb.so \
      RESULTSET_SIZE 1000000 TIMEOUT 0 MAX_QUEUED_QUERIES 4096 THREAD_COUNT 4 \
  --port 6379 --daemonize no --save '' --appendonly no --dir /var/lib/falkordb/data &
FALKOR_PID=$!

echo "waiting for FalkorDB…"
READY=0
for i in $(seq 1 40); do
  if redis-cli PING >/dev/null 2>&1; then echo "FalkorDB up after ${i}s"; READY=1; break; fi
  sleep 1
done
if [ "$READY" -ne 1 ]; then
  echo "FalkorDB did not accept connections within 40s. Last log lines:" >&2
  jobs -p >/dev/null 2>&1
  exit 1
fi

# ---------------------------------------------------------------------------
# An identity for the read path that the SERVER refuses to let write.
#
# Every HTTP request that answers a question goes through `ro_query`, 28 hand-written call sites
# of it, and until now that was a convention: a future call site typing `query` instead would
# work, and nothing would notice. This makes it the engine's rule instead. `tombstone-reader` is
# granted `+graph.ro_query`, `+info` (the client issues INFO at construction, to detect Sentinel)
# and `+ping`, over keys matching `tomb:*`, and nothing else -- so GRAPH.QUERY, GRAPH.COPY,
# GRAPH.DELETE, GRAPH.CONSTRAINT, GRAPH.PROFILE, FLUSHALL, CONFIG SET, SCRIPT LOAD and ACL
# SETUSER are all refused to it by Redis before FalkorDB ever sees them.
#
# The password is generated here, per boot. It is never written to a file, never in the image and
# never in this repository -- the push gate refuses credential-shaped strings, and a credential
# that exists for one container's lifetime cannot be leaked by a commit.
#
# The key pattern is the configured graph name itself, not a wildcard, so the two can never drift:
# point TOMBSTONE_GRAPH somewhere else and the grant follows it. A fixed `~tomb:*` would have left
# a boot that said OK and an app that answered every question with a permission error.
#
# And note `~` rather than `%R~`. A read-only key selector would be the right way to say this and
# it CANNOT work here: `COMMAND INFO graph.RO_QUERY` reports key-spec flags `RW access update`
# even though the command itself is flagged `readonly`, and ACL selectors test the key spec.
# Measured -- with `%R~` even a plain read is refused, "No permissions to access a key". So the
# key pattern bounds WHICH graph, and the command grant bounds what may be done to it.
#
# If any of this does not take -- an older FalkorDB whose module commands ACL cannot name, say --
# the boot does NOT fail. It unsets the password, so the app runs as the default identity and
# `/api/health` reports `read_identity: default`. A demo that is down protects nothing; a demo
# that claims a boundary it does not have is worse than one that admits it.
GRAPH="${TOMBSTONE_GRAPH:-tomb:k8s}"
export TOMBSTONE_READER_PASSWORD="$(python -c 'import secrets; print(secrets.token_hex(32))')"
ACL_OK=1
redis-cli ACL SETUSER tombstone-reader \
    on ">$TOMBSTONE_READER_PASSWORD" resetkeys resetchannels \
    "~$GRAPH" '-@all' +graph.ro_query +info +ping >/dev/null 2>&1 || ACL_OK=0

# Asserted both ways, because "the user exists" is not the claim. The claim is that it can read
# and cannot write, and only the server can settle that.
if [ "$ACL_OK" -eq 1 ]; then
  redis-cli ACL DRYRUN tombstone-reader GRAPH.RO_QUERY "$GRAPH" 'RETURN 1' 2>/dev/null \
    | grep -qx OK || ACL_OK=0
  redis-cli ACL DRYRUN tombstone-reader GRAPH.QUERY "$GRAPH" 'CREATE (:X)' 2>/dev/null \
    | grep -q 'no permissions' || ACL_OK=0
fi

if [ "$ACL_OK" -eq 1 ]; then
  echo "read path: tombstone-reader (+graph.ro_query on $GRAPH; GRAPH.QUERY refused by the server)"
else
  echo "read path: default -- the reader ACL did not take on this server, so the read path is a" >&2
  echo "           convention again. Serving anyway; /api/health will say so." >&2
  unset TOMBSTONE_READER_PASSWORD
fi

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
