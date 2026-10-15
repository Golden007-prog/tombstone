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
STAGE="$(mktemp -d)"
trap 'rm -rf "$STAGE"; docker rm -f "$IMG" >/dev/null 2>&1 || true' EXIT

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
# Two memory facts matter and they are very different, so the container runs with room and the
# tighter one is asserted rather than imposed.
#
#   serial use            ~400MB  -- answering, drafting, one counterfactual at a time
#   six concurrent copies ~900MB  -- measured; it OOMs at 768MB and at 1GB, and survives at 2GB
#
# GRAPH.COPY materialises a whole graph per call, so concurrency multiplies it. Running the whole
# check at 512MB -- which an earlier version did -- made the concurrency burst OOM the container
# and looked like a product failure when it was a sizing mistake in the harness. Running it all at
# 2GB would hide a serial regression. So: 2GB of room, and SERIAL_CEILING asserted after the
# serial checks, before any concurrency.
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

serial_mb="$(docker stats --no-stream --format '{{.MemUsage}}' "$IMG" 2>/dev/null \
             | awk '{print $1}' | sed 's/MiB//')"
serial_int="${serial_mb%%.*}"
if [ -n "$serial_int" ] && [ "$serial_int" -gt "$SERIAL_CEILING_MB" ]; then
  echo "FAIL: serial use peaked at ${serial_mb}MiB, above the ${SERIAL_CEILING_MB}MiB ceiling"
  exit 1
fi
echo "  serial peak ${serial_mb}MiB, under the ${SERIAL_CEILING_MB}MiB ceiling"

# Six counterfactuals at once, all of which fork. Needs ~900MB, which is why the container has 2GB. The failure this is looking for is
# a 500 or a hung request; a DEGRADED is the designed answer when a fork genuinely cannot happen,
# and is counted as a pass. Judges share links, so concurrent use of the one hosted container is
# the normal case rather than the stress case.
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
  echo "FAIL: the container was OOM-killed inside 512MB"
  exit 1
fi

echo
echo "Deploy path verified. The only thing left is HF_TOKEN:"
echo "  export HF_TOKEN=hf_...   &&   ./deploy_hf.sh"
