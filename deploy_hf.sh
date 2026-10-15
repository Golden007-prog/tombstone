#!/usr/bin/env bash
# One-command deploy to Hugging Face Spaces.
#
# Usage:
#   export HF_TOKEN=hf_xxxxxxxxxxxx      # a WRITE token from huggingface.co/settings/tokens
#   ./deploy_hf.sh [space-name]
#
# Why Spaces: free, no card, the image is kept, and it wakes on request. FalkorDB Cloud's free
# tier stops after a day idle and is deleted after seven, so a link submitted on the 18th could
# be dead when a judge clicks it. This image carries its own data and re-seeds on boot instead.
set -euo pipefail
cd "$(dirname "$0")"

SPACE_NAME="${1:-tombstone}"

if [ -z "${HF_TOKEN:-}" ]; then
  echo "HF_TOKEN is not set." >&2
  echo "  1. Go to https://huggingface.co/settings/tokens" >&2
  echo "  2. Create a token with the WRITE role" >&2
  echo "  3. export HF_TOKEN=hf_... && ./deploy_hf.sh" >&2
  exit 1
fi

PY="${PY:-.venv/bin/python}"
[ -x "$PY" ] || PY="$(command -v python3)"
"$PY" -c "import huggingface_hub" 2>/dev/null || "$PY" -m pip install -q huggingface_hub

USER=$("$PY" - <<'PY'
import os
from huggingface_hub import HfApi
print(HfApi(token=os.environ["HF_TOKEN"]).whoami()["name"])
PY
)
REPO="$USER/$SPACE_NAME"
echo "deploying to https://huggingface.co/spaces/$REPO"

# Spaces reads its config from front-matter in the Space's own README, which is NOT this repo's
# README. Stage a copy of the tree with the Space README swapped in.
STAGE="$(mktemp -d)"
trap 'rm -rf "$STAGE"' EXIT
git archive HEAD | tar -x -C "$STAGE"
cp deploy/README-hf-space.md "$STAGE/README.md"

"$PY" - "$STAGE" "$REPO" <<'PY'
import os, sys
from huggingface_hub import HfApi
stage, repo = sys.argv[1], sys.argv[2]
api = HfApi(token=os.environ["HF_TOKEN"])
api.create_repo(repo_id=repo, repo_type="space", space_sdk="docker", exist_ok=True)
api.upload_folder(
    folder_path=stage, repo_id=repo, repo_type="space",
    commit_message="Deploy Tombstone (Graph Hacks 2026, Track 3)",
    ignore_patterns=[".git/*", "**/__pycache__/*", "*.pyc", ".venv/*", ".pytest_cache/*"],
)
print(f"\nhttps://huggingface.co/spaces/{repo}")
PY

echo
echo "The Space builds the Dockerfile (several minutes on a first build), then boots in seconds."
echo "Verify once it is running:"
echo "  curl -s https://$(echo "$USER" | tr '[:upper:]' '[:lower:]')-${SPACE_NAME}.hf.space/api/health"
