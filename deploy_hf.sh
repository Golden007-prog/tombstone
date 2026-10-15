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

LIVE="https://$(echo "$USER" | tr '[:upper:]' '[:lower:]')-${SPACE_NAME}.hf.space"

echo
echo "The Space builds the Dockerfile (several minutes on a first build), then boots in about ten"
echo "seconds cold and five warm. Verify once it is running:"
echo "  curl -s $LIVE/api/health"

# Everything below removes a step from the deadline-night path. Each one is a thing that is
# obvious now and easy to forget at 11pm with a form open in another tab.

# The repo's homepage is what GitHub shows as "the project link". It points at the hackathon page
# until this runs, which sends anyone clicking it to the wrong place.
GH_REPO="$(git remote get-url origin 2>/dev/null \
  | sed -E 's#(git@github.com:|https://github.com/)##; s#\.git$##')"
if [ -n "$GH_REPO" ] && command -v gh >/dev/null && gh auth status >/dev/null 2>&1; then
  if gh repo edit "$GH_REPO" --homepage "$LIVE" >/dev/null 2>&1; then
    echo
    echo "set $GH_REPO's homepage to $LIVE"
  else
    echo
    echo "could not set the repo homepage; do it with:" >&2
    echo "  gh repo edit $GH_REPO --homepage $LIVE" >&2
  fi
fi

# SUBMISSION.md exists to be filled in and pasted into a form. Fill the row this script knows.
if [ -f SUBMISSION.md ] && grep -q '^| Live demo |' SUBMISSION.md; then
  "$PY" - "$LIVE" <<'PY'
import re, sys
live = sys.argv[1]
text = open("SUBMISSION.md").read()
text = re.sub(r"^\| Live demo \|.*$", f"| Live demo | {live} |", text, count=1, flags=re.M)
open("SUBMISSION.md", "w").write(text)
print(f"wrote the live URL into SUBMISSION.md")
PY
fi

cat <<MSG

Left to do by hand, in order:
  1. open $LIVE in a PRIVATE window and click one chip, to confirm it works signed out
  2. paste $LIVE into the README's Rule 10 table (the deployment row)
  3. record the video -- docs/DEMO-SCRIPT.md, keyless, 3:00
  4. submit: SUBMISSION.md has the copy, deadline 11:59 PM IST Sunday 18 October
MSG
