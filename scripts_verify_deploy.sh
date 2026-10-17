#!/usr/bin/env bash
# Verify the deploy BEFORE spending a token on it.
#
# Hugging Face Spaces builds this repo's Dockerfile on linux/amd64 and runs it as a non-root user.
# A build or boot failure is discovered minutes later in a web log, which is a bad place to find
# out. This reproduces the Space locally -- same platform, same UID, no volumes -- and asserts the
# product actually answers, rather than just that the container started.
#
# Usage:  ./scripts_verify_deploy.sh          (then ./deploy_hf.sh once HF_TOKEN is set)
set -euo pipefail
cd "$(dirname "$0")"

IMG=tombstone-deploycheck
PORT="${PORT:-8111}"
# The second container: the hosted size, imposed rather than asserted. See the stage near the end.
PROD="$IMG-prod"
PROD_PORT="${PROD_PORT:-8112}"
PROD_MB="${PROD_MB:-512}"
STAGE="$(mktemp -d)"
trap 'rm -rf "$STAGE"; docker rm -f "$IMG" "$PROD" >/dev/null 2>&1 || true' EXIT

echo "staging exactly what deploy_hf.sh uploads (committed tree + the Space README)"
git archive HEAD | tar -x -C "$STAGE"
cp deploy/README-hf-space.md "$STAGE/README.md"
grep -q '^sdk: docker' "$STAGE/README.md" || { echo "FAIL: Space front-matter lost"; exit 1; }
if find "$STAGE" -name '.env' -o -name '*.pem' | grep -q .; then
  echo "FAIL: a secret-looking file is staged for upload"; exit 1
fi

echo "building for linux/amd64, as the Space does"
docker build --platform linux/amd64 -t "$IMG" "$STAGE" >/dev/null 2>&1

# The image installs python3 from the pinned base image's apt repos, so its version moves only
# when the base tag moves. That is stable, and stable is not the same as checked: fastembed needs
# onnxruntime, which has no wheel outside 3.11-3.14, and a base bump that carried Python past
# that would break the build in a way whose error never mentions Python. It is cheap to assert.
img_py="$(docker run --rm --platform linux/amd64 --entrypoint /opt/venv/bin/python "$IMG" \
          -c 'import sys; print("%d.%d" % sys.version_info[:2])' 2>/dev/null || echo unknown)"
case "$img_py" in
  3.11|3.12|3.13|3.14) echo "  image Python $img_py -> inside the supported range" ;;
  *) echo "FAIL: the image runs Python $img_py; fastembed needs 3.11-3.14"; exit 1 ;;
esac

echo "running as a non-root user with no volumes, as the Space does"
docker rm -f "$IMG" >/dev/null 2>&1 || true
# This container gets room, and the production-sized run is a SEPARATE stage further down. That
# split is the correction to a wrong call made here, and the wrong call cost an outage.
#
# What this block used to say: serial ~400MB, six concurrent copies ~900MB, OOMs at 1GB, so give
# it 2GB and assert only the serial ceiling. The 900MB figure was real when it was taken and was
# never retaken after the lock in `Agent._remember` landed -- which is the change that made it
# false. Re-measured in this image at 512MB with six DISTINCT counterfactuals, so none can be
# answered from memory: 319MiB, five answered, one honestly degraded, no kill. GRAPH.COPY was not
# the multiplier. The embedder was: ONNX Runtime takes ~119MiB of arena per concurrent `Run`, and
# `_remember` happened to serialise the one path this check exercised.
#
# So the burst below proved the wrong thing at the wrong size, and the path it never ran -- free
# text through /api/ask, two unbounded embed sites -- is the one the hosted demo died on, on
# 17 Oct, when the platform killed it for exceeding 512MB while serving. Four concurrent visitors
# did it. The fix is in `tombstone.embedding`; the check for it is the 512MB stage below.
SERIAL_CEILING_MB=512
docker run -d --name "$IMG" --platform linux/amd64 --user 1000 \
  --memory=2g --memory-swap=2g -p "$PORT:8099" "$IMG" >/dev/null

# Timed, because the Space README states a boot figure and a stated figure needs a measurement
# behind it. Polled tightly so the number is the container's, not the poll interval's.
_boot_start=$(date +%s)
for _ in $(seq 1 600); do
  health="$(curl -s -m 3 "http://localhost:$PORT/api/health" 2>/dev/null || true)"
  [ -n "$health" ] && break
  sleep 0.2
done
_boot_s=$(( $(date +%s) - _boot_start ))
[ -n "${health:-}" ] || { echo "FAIL: never served"; docker logs --tail 40 "$IMG"; exit 1; }
echo "$health" | grep -q '"up"' || { echo "FAIL: FalkorDB down in-container: $health"; exit 1; }
echo "  health: $health"
echo "  cold boot to healthy: ~${_boot_s}s on this host (the Space README quotes 3.7s, measured on an M-series laptop; a shared-CPU Space will be slower)"

# Serving is not the same as working. Exercise a real traversal, the ACTION, and GRAPH.COPY.
# Serving is not the same as working, so exercise a real traversal, the ACTION, and GRAPH.COPY.
# who_owns needs its path INCLUDING the trailing /OWNERS -- that is the node key. Called with a
# path that does not exist it returns UNKNOWN_ENTITY, which is the product refusing to guess.
call() {  # call <tool> <args-json>
  curl -s -m 60 -X POST "http://localhost:$PORT/api/tool" -H 'content-type: application/json' \
    -d "{\"tool\":\"$1\",\"args\":$2}" \
    | python3 -c 'import json,sys; print(json.load(sys.stdin).get("shape"))'
}
expect_answer() {  # expect_answer <label> <shape>
  echo "  $1 -> $2"
  case "$2" in ANSWERED_WITH_PATH|ANSWERED_FROM_MEMORY|NOT_IN_GRAPH) ;;
    *) echo "FAIL: $1 returned $2 in-container"; exit 1;; esac
}

OWNERS_PATH="staging/src/k8s.io/apiserver/pkg/endpoints/metrics/OWNERS"
expect_answer "who_owns(depth=4)" "$(call who_owns "{\"path\":\"$OWNERS_PATH\",\"depth\":4}")"
expect_answer "draft_owners_patch" "$(call draft_owners_patch '{}')"

shape=$(curl -s -m 90 -X POST "http://localhost:$PORT/api/tool" -H 'content-type: application/json' \
  -d '{"tool":"what_if_they_go","args":{"handles":["deads2k","liggitt"]}}' \
  | python3 -c 'import json,sys; print(json.load(sys.stdin).get("shape"))')
echo "  what_if_they_go (GRAPH.COPY) -> $shape"
[ "$shape" = "ANSWERED_WITH_PATH" ] || { echo "FAIL: GRAPH.COPY cannot fork in-container"; exit 1; }

# The hosted Space has NO API key, so free-text routing there is the local one. If that breaks,
# the ask box on the public demo goes back to being dead, which is what this whole path exists to
# prevent. Check both halves: it answers what it should, and refuses what it should.
ask() {
  curl -s -m 120 -X POST "http://localhost:$PORT/api/ask" -H 'content-type: application/json' \
    -d "{\"question\":\"$1\"}" \
    | python3 -c 'import json,sys; d=json.load(sys.stdin); print(d.get("shape"), d.get("routed_to"))'
}
got="$(ask 'which areas have exactly one approver?')"
echo "  keyless ask (answerable) -> $got"
case "$got" in ANSWERED_WITH_PATH*|ANSWERED_FROM_MEMORY*) ;;
  *) echo "FAIL: keyless free-text routing did not answer in-container"; exit 1;; esac
got="$(ask 'write me a poem about kubernetes')"
echo "  keyless ask (refusable)  -> $got"
case "$got" in UNSURE_WHICH_TOOL*) ;;
  *) echo "FAIL: keyless routing did not refuse an out-of-domain question"; exit 1;; esac

for path in / /app.js /style.css "/?run=draft_owners_patch&focus=1"; do
  code=$(curl -s -m 10 -o /dev/null -w '%{http_code}' "http://localhost:$PORT$path")
  echo "  $path -> $code"
  [ "$code" = "200" ] || { echo "FAIL: $path returned $code"; exit 1; }
done

# Hugging Face renders a Space INSIDE AN IFRAME on its page. Two things break that silently and
# neither produces an error anywhere a developer would look: a framing header, which leaves the
# judge staring at a blank box, and browser storage, which throws in a cross-origin frame when
# third-party cookies are blocked -- the default in Safari and increasingly elsewhere.
headers="$(curl -s -D- -o /dev/null -m 10 "http://localhost:$PORT/")"
if printf '%s' "$headers" | grep -qiE 'x-frame-options|frame-ancestors'; then
  echo "FAIL: the app sends a framing header, so it will not render inside the Space's iframe"
  printf '%s' "$headers" | grep -iE 'x-frame-options|content-security-policy' >&2
  exit 1
fi
echo "  no framing headers -> embeds in the Space iframe"

app_js="$(curl -s -m 10 "http://localhost:$PORT/app.js")"
if printf '%s' "$app_js" | grep -qE 'localStorage|sessionStorage|document\.cookie|indexedDB'; then
  echo "FAIL: the front end uses browser storage, which throws in a cross-origin iframe when"
  echo "      third-party cookies are blocked. The Space would break for a chunk of judges."
  exit 1
fi
echo "  no browser storage   -> survives third-party cookie blocking"

# The read path's identity, checked on the ARTEFACT rather than in the source tree. Reading 28
# `ro_query` calls proves a convention; this asks the server what it will let that identity do.
# A hardening that is configured and not in force is the same defect as a measurement that was
# true last week -- which is the one that cost this project a day.
ident="$(curl -s -m 10 "http://localhost:$PORT/api/health" \
         | python3 -c 'import json,sys; print(json.load(sys.stdin).get("read_identity"))')"
echo "  read identity        -> $ident"
[ "$ident" = "tombstone-reader" ] || {
  echo "FAIL: the container answers public requests as '$ident'. The reader ACL did not take, so"
  echo "      the read path is a convention again. docker-entrypoint.sh says why on stdout:"
  docker logs "$IMG" 2>&1 | grep -i "read path" >&2
  exit 1; }
# Each probe is spelled out with ITS OWN arguments. DRYRUN checks arity before permissions, so a
# shared argument list would turn a refusal into "wrong number of arguments" for whichever command
# it did not fit -- and this script has already shipped one check that passed on a coincidence.
refuses() {  # refuses <label> <command and its real arguments...>
  label="$1"; shift
  verdict="$(docker exec "$IMG" redis-cli ACL DRYRUN tombstone-reader "$@" 2>&1)"
  case "$verdict" in
    *"no permissions"*) echo "  $label -> $verdict" ;;
    *) echo "FAIL: the read identity was not refused $label: $verdict"; exit 1 ;;
  esac
}
refuses "GRAPH.QUERY " GRAPH.QUERY tomb:k8s 'CREATE (:X)'
refuses "GRAPH.COPY  " GRAPH.COPY tomb:k8s tomb:stolen
refuses "GRAPH.DELETE" GRAPH.DELETE tomb:k8s
refuses "FLUSHALL    " FLUSHALL
# And the counterfactual copies it must not be able to read either, because the grant names one
# key rather than a `tomb:*` pattern.
verdict="$(docker exec "$IMG" redis-cli ACL DRYRUN tombstone-reader \
             GRAPH.RO_QUERY "tomb:k8s:cf:probe" 'MATCH (n) RETURN n' 2>&1)"
case "$verdict" in
  *"no permissions to access"*) echo "  a counterfactual copy -> $verdict" ;;
  *) echo "FAIL: the read identity can reach hypothetical graphs: $verdict"; exit 1 ;;
esac

serial_mb="$(docker stats --no-stream --format '{{.MemUsage}}' "$IMG" 2>/dev/null \
             | awk '{print $1}' | sed 's/MiB//')"
serial_int="${serial_mb%%.*}"
if [ -n "$serial_int" ] && [ "$serial_int" -gt "$SERIAL_CEILING_MB" ]; then
  echo "FAIL: serial use peaked at ${serial_mb}MiB, above the ${SERIAL_CEILING_MB}MiB ceiling"
  exit 1
fi
echo "  serial peak ${serial_mb}MiB, under the ${SERIAL_CEILING_MB}MiB ceiling"

# Six counterfactuals at once, every one materialising a copy. The failure this is looking for is
# a 500 or a hung request; a DEGRADED is the designed answer when a copy genuinely cannot happen,
# and is counted as a pass. Judges share links, so concurrent use of the one hosted container is
# the normal case rather than the stress case.
#
# They are deliberately the SAME question, because this stage is about GRAPH.COPY under contention
# and the repeats legitimately come back from memory. The distinct-handle version of this, at
# 512MB, is the stage below.
python3 - <<'PY'
import json, sys, urllib.request, concurrent.futures as cf, os
base = f"http://localhost:{os.environ.get('PORT', '8111')}"
body = {"tool": "what_if_they_go", "args": {"handles": ["deads2k", "liggitt"]}}

def call(_):
    req = urllib.request.Request(base + "/api/tool", method="POST",
                                 data=json.dumps(body).encode(),
                                 headers={"content-type": "application/json"})
    try:
        return json.load(urllib.request.urlopen(req, timeout=180)).get("shape")
    except Exception as exc:
        return f"HARD-FAILURE:{type(exc).__name__}"

with cf.ThreadPoolExecutor(max_workers=6) as ex:
    shapes = list(ex.map(call, range(6)))
# Both shapes are a successful answer. The serial checks above ask this same counterfactual, so
# by the time the burst runs the question is legitimately remembered and the repeats come back
# ANSWERED_FROM_MEMORY. Counting only ANSWERED_WITH_PATH reported six successes as zero and read
# exactly like a concurrency regression -- a narrow assertion that only became wrong when memory
# started recording tool calls, which was itself a bug fixed hours earlier.
ANSWERED = {"ANSWERED_WITH_PATH", "ANSWERED_FROM_MEMORY"}
answered = sum(s in ANSWERED for s in shapes)
degraded = sum(s == "DEGRADED" for s in shapes)
hard = [s for s in shapes if s and s.startswith("HARD-FAILURE")]
print(f"  6 concurrent forking requests: {answered} answered, {degraded} degraded honestly, "
      f"{len(hard)} hard failures")
if hard:
    sys.exit(f"FAIL: concurrent counterfactuals produced {hard}")
if answered == 0:
    sys.exit("FAIL: not one concurrent counterfactual completed")
PY

peak="$(docker stats --no-stream --format '{{.MemUsage}}' "$IMG" 2>/dev/null)"
echo "  peak with six concurrent copies: $peak"
if docker inspect "$IMG" --format '{{.State.OOMKilled}}' 2>/dev/null | grep -q true; then
  echo "FAIL: the container was OOM-killed inside the 2GB it was given"
  exit 1
fi

# ---------------------------------------------------------------------------
# The production envelope, imposed rather than asserted: 512MB, no swap, and the traffic the
# hosted demo actually died on -- concurrent FREE TEXT, which is the path with the embeds.
#
# Everything above runs with 2GB of room, and every number it prints is therefore a number about
# a box the demo does not have. On 17 Oct the platform killed the hosted instance for exceeding
# its memory limit while serving. Two concurrent asks measured 415MiB, so the fourth visitor was
# the kill; a link shared with judges is concurrent by definition. This stage is the one that
# would have caught it, so it runs at exactly the hosted size and lets the kernel be the judge:
# no stats reading, no ceiling to argue with, just whether the kernel killed it.
echo
echo "the production envelope: a second container at exactly ${PROD_MB}MB, no swap, flooded with"
echo "concurrent free text -- the shape of traffic the hosted demo was killed by"
docker rm -f "$PROD" >/dev/null 2>&1 || true
docker run -d --name "$PROD" --platform linux/amd64 --user 1000 \
  --memory="${PROD_MB}m" --memory-swap="${PROD_MB}m" -p "$PROD_PORT:8099" "$IMG" >/dev/null
for _ in $(seq 1 600); do
  curl -s -m 3 "http://localhost:$PROD_PORT/api/health" >/dev/null 2>&1 && break
  sleep 0.2
done
curl -s -m 3 "http://localhost:$PROD_PORT/api/health" | grep -q '"up"' \
  || { echo "FAIL: the ${PROD_MB}MB container never became healthy"; docker logs --tail 30 "$PROD"; exit 1; }
echo "  booted at ${PROD_MB}MB: $(docker stats --no-stream --format '{{.MemUsage}}' "$PROD")"

PROD_PORT=$PROD_PORT python3 - <<'PY'
import json, os, sys, urllib.request, concurrent.futures as cf
from collections import Counter
base = f"http://localhost:{os.environ['PROD_PORT']}"
# DISTINCT questions, so every one embeds, routes and answers for real. The repeats-from-memory
# that make the burst above cheap are exactly what must not happen here.
QS = ["which areas have exactly one approver?", "who owns the scheduler?",
      "has anyone tried {t}?", "what did we decide about {t}?",
      "which approvals have gone stale?", "what breaks if {t} leaves?"]
def ask(i):
    q = QS[i % len(QS)].format(t=f"idea-{i}")
    req = urllib.request.Request(base + "/api/ask", method="POST",
                                 data=json.dumps({"question": q}).encode(),
                                 headers={"content-type": "application/json"})
    try:
        return json.load(urllib.request.urlopen(req, timeout=240)).get("shape")
    except Exception as e:
        return f"HARD:{type(e).__name__}"
with cf.ThreadPoolExecutor(max_workers=8) as ex:
    shapes = list(ex.map(ask, range(24)))
counts = dict(Counter(shapes))
print(f"  24 distinct asks, 8 at a time: {counts}")
hard = [s for s in shapes if s.startswith("HARD")]
if hard:
    sys.exit(f"FAIL: {len(hard)} of 24 requests got no answer at all: {dict(Counter(hard))}")
PY

echo "  peak: $(docker stats --no-stream --format '{{.MemUsage}}' "$PROD")"
if [ "$(docker inspect "$PROD" --format '{{.State.OOMKilled}}')" = "true" ]; then
  echo "FAIL: the kernel killed the container at ${PROD_MB}MB -- this is the hosted outage, reproduced"
  exit 1
fi
[ "$(docker inspect "$PROD" --format '{{.State.Running}}')" = "true" ] \
  || { echo "FAIL: the ${PROD_MB}MB container is no longer running"; docker logs --tail 30 "$PROD"; exit 1; }
curl -s -m 5 "http://localhost:$PROD_PORT/api/health" | grep -q '"up"' \
  || { echo "FAIL: survived the flood but is no longer healthy"; exit 1; }
echo "  survived ${PROD_MB}MB: not killed, still answering"
docker rm -f "$PROD" >/dev/null 2>&1 || true

# ---------------------------------------------------------------------------
# "Turn FalkorDB off and it fails loudly" is one of the README's central claims, and until now it
# had only ever been checked by reading the code for a fallback that is not there. On a Space the
# database being killed is not hypothetical -- it is what an OOM looks like. So kill it here, in
# the container, and watch what the product does. This runs LAST because it ends the instance.
echo
echo "killing FalkorDB inside the container, to see what the product does when it is gone"
# Two things wrong with the version this replaces, and they hid each other.
#
# It matched `falkordb` OR `redis-server` against every /proc/N/cmdline -- including its own,
# because the pattern it is searching for is sitting in the shell's own command line. And
# /proc/[0-9]* globs in STRING order, so whether the shell reached PID 7 before killing itself
# depended on the digits it happened to be assigned: "105" sorts before "7". It worked when it was
# written, and on this run it killed its own shell and nothing else -- then the stage below
# reported the product's honest "up" as a product failure. A check that kills the wrong process
# and blames the program is worse than no check.
#
# So: skip self, match only the process name, and -- the part that was missing -- VERIFY the
# target is gone before drawing any conclusion from what the app says next.
docker exec "$IMG" sh -c '
  self=$$
  for p in /proc/[0-9]*; do
    pid=${p##*/}
    [ "$pid" = "$self" ] && continue
    grep -aq redis-server "$p/cmdline" 2>/dev/null || continue
    kill -9 "$pid" 2>/dev/null
  done' >/dev/null 2>&1 || true
sleep 3

if docker exec "$IMG" redis-cli -t 2 PING 2>/dev/null | grep -q PONG; then
  echo "FAIL: FalkorDB is still answering, so nothing below tests what it claims to test."
  echo "      The kill did not land -- fix the kill, do not reinterpret the result."
  docker exec "$IMG" sh -c 'for p in /proc/[0-9]*; do tr "\0" " " < $p/cmdline 2>/dev/null; echo; done' | grep -v '^$'
  exit 1
fi
echo "  FalkorDB is gone: redis-cli no longer answers inside the container"

down_health="$(curl -s -m 5 "http://localhost:$PORT/api/health" || true)"
echo "$down_health" | grep -q '"down"' \
  || { echo "FAIL: health still claims FalkorDB is up after it was killed: $down_health"; exit 1; }
echo "  health reports down, rather than claiming to be fine"

down_answer="$(curl -s -m 20 -X POST "http://localhost:$PORT/api/tool" \
  -H 'content-type: application/json' -d '{"tool":"sole_approver_risk","args":{}}' || true)"
echo "$down_answer" | grep -q 'DEGRADED' \
  || { echo "FAIL: a tool answered something other than DEGRADED with no database: $down_answer"; exit 1; }
# The same question answered a moment ago. If memory could serve it now, the product would be
# handing back a stale claim while the thing it cites is unreachable -- which is the exact failure
# this whole project argues against. Memory lives in the graph, so it dies with it.
echo "$down_answer" | grep -q 'ANSWERED_FROM_MEMORY' \
  && { echo "FAIL: memory served an answer while the graph was unreachable"; exit 1; }
echo "  a question answered moments ago now returns DEGRADED, not a remembered answer"

down_typed="$(curl -s -m 20 -X POST "http://localhost:$PORT/api/ask" \
  -H 'content-type: application/json' -d '{"question":"which areas have exactly one approver?"}' || true)"
echo "$down_typed" | grep -q 'DEGRADED' \
  || { echo "FAIL: a typed question did not degrade honestly: $down_typed"; exit 1; }

page_code="$(curl -s -o /dev/null -w '%{http_code}' -m 10 "http://localhost:$PORT/" || true)"
[ "$page_code" = "200" ] \
  || { echo "FAIL: the page itself stopped serving when the database died ($page_code)"; exit 1; }
echo "  the page still serves, so a visitor sees an honest error instead of a dead site"

echo
echo "Deploy path verified. The only thing left is HF_TOKEN:"
echo "  export HF_TOKEN=hf_...   &&   ./deploy_hf.sh"
