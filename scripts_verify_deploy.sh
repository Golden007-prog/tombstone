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

echo "running as a non-root user with no volumes, as the Space does"
docker rm -f "$IMG" >/dev/null 2>&1 || true
docker run -d --name "$IMG" --platform linux/amd64 --user 1000 -p "$PORT:8099" "$IMG" >/dev/null

for _ in $(seq 1 60); do
  health="$(curl -s -m 3 "http://localhost:$PORT/api/health" 2>/dev/null || true)"
  [ -n "$health" ] && break
  sleep 3
done
[ -n "${health:-}" ] || { echo "FAIL: never served"; docker logs --tail 40 "$IMG"; exit 1; }
echo "$health" | grep -q '"up"' || { echo "FAIL: FalkorDB down in-container: $health"; exit 1; }
echo "  health: $health"

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

for path in / /app.js /style.css "/?run=draft_owners_patch&focus=1"; do
  code=$(curl -s -m 10 -o /dev/null -w '%{http_code}' "http://localhost:$PORT$path")
  echo "  $path -> $code"
  [ "$code" = "200" ] || { echo "FAIL: $path returned $code"; exit 1; }
done

echo
echo "Deploy path verified. The only thing left is HF_TOKEN:"
echo "  export HF_TOKEN=hf_...   &&   ./deploy_hf.sh"
