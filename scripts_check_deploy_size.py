"""Does FINISH.md still say what the deploy actually uploads? No database needed.

This exists because adding one file turned CI red. The figure is computed from `git archive HEAD`
-- the same way deploy_hf.sh builds its upload -- so before a commit HEAD does not contain the new
file and the count is right, and after the commit it is wrong. ./preflight.sh runs pre-commit and
passed; CI ran post-commit and failed. Adding any file to this repository guaranteed exactly one
red commit, and the information to prevent it existed only in the window between them.

So it moves into the push, where HEAD is already what CI will see. It needs no database, which is
what lets it live in a hook that has to stay fast.

    python scripts_check_deploy_size.py
"""
from __future__ import annotations

import os
import pathlib
import re
import shutil
import subprocess
import sys
import tempfile

TOLERANCE_MB = 0.15


def staged() -> tuple[int, float]:
    """Build the upload exactly as deploy_hf.sh does: git archive HEAD, Space README swapped in."""
    work = tempfile.mkdtemp(prefix="deploysize-")
    try:
        tar = subprocess.run(["git", "archive", "HEAD"], capture_output=True)
        if tar.returncode != 0:
            sys.exit("git archive HEAD failed; is this a repository with a commit?")
        subprocess.run(["tar", "-x", "-C", work], input=tar.stdout, capture_output=True)
        space = pathlib.Path("deploy/README-hf-space.md")
        if space.exists():
            shutil.copy(space, os.path.join(work, "README.md"))
        files = byts = 0
        for root, _dirs, names in os.walk(work):
            for name in names:
                files += 1
                byts += os.path.getsize(os.path.join(root, name))
        return files, byts / 1_000_000
    finally:
        shutil.rmtree(work, ignore_errors=True)


def main() -> int:
    finish = pathlib.Path("FINISH.md")
    if not finish.exists():
        print("  FAIL  FINISH.md is missing; it is the file this figure lives in")
        return 1
    said = re.search(r"uploads (\d+) files / ([\d.]+) MB", finish.read_text())
    if not said:
        print("  FAIL  FINISH.md no longer says what the deploy uploads")
        return 1

    files, mb = staged()
    want_files, want_mb = int(said.group(1)), float(said.group(2))
    if want_files != files:
        print(f"  FAIL  FINISH.md says the deploy uploads {want_files} files; HEAD gives {files}")
        return 1
    if abs(want_mb - mb) > TOLERANCE_MB:
        print(f"  FAIL  FINISH.md says {want_mb} MB; HEAD gives {mb:.1f} MB")
        return 1
    print(f"  the deploy uploads {files} files / {mb:.1f} MB and FINISH.md says so")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
