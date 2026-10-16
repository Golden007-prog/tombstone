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


# Hugging Face reads a Space's whole configuration from the YAML block at the top of its
# README, and an unknown or malformed key there fails the build on their side -- minutes later,
# in a web log, at whatever hour the deploy is attempted. The allowed set is published
# (huggingface.co/docs/hub/spaces-config-reference) and was checked against this file on 16 Oct;
# the only prior guard was `grep -q '^sdk: docker'` inside ./scripts_verify_deploy.sh, which
# needs Docker and so runs nowhere near a push.
SPACE_FIELDS = {
    "title", "emoji", "colorFrom", "colorTo", "sdk", "python_version", "sdk_version",
    "suggested_hardware", "suggested_storage", "app_file", "app_build_command", "app_port",
    "base_path", "fullWidth", "header", "short_description", "models", "datasets", "tags",
    "thumbnail", "pinned", "hf_oauth", "hf_oauth_scopes", "hf_oauth_expiration_minutes",
    "hf_oauth_authorized_org", "disable_embedding", "startup_duration_timeout",
    "custom_headers", "preload_from_hub", "license",
}
SPACE_COLORS = {"red", "yellow", "green", "blue", "indigo", "purple", "pink", "gray"}


def space_front_matter() -> list[str]:
    """Validate the Space's YAML header against Hugging Face's published field set.

    Parsed by hand rather than with PyYAML, because this file says at the top that it needs no
    dependencies and that is not decoration: ./scripts/pre-push runs it with the system python3,
    where PyYAML is not installed. My first version imported yaml, passed under the project venv,
    and was refused by the push gate with a ModuleNotFoundError -- a check that only works under
    the interpreter it was developed with is not a gate.

    The block is flat `key: value` lines, so a hand parser is sufficient; anything structurally
    richer is reported rather than quietly accepted.
    """
    path = pathlib.Path("deploy/README-hf-space.md")
    if not path.exists():
        return ["deploy/README-hf-space.md is missing; the deploy swaps it in as the Space README"]
    lines = path.read_text(encoding="utf-8").splitlines()
    if not lines or lines[0].strip() != "---":
        return ["deploy/README-hf-space.md does not open with a YAML front-matter block"]
    try:
        end = lines.index("---", 1)
    except ValueError:
        return ["the Space front-matter block is never closed with ---"]

    meta, bad = {}, []
    for raw in lines[1:end]:
        line = raw.rstrip()
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        if line != line.lstrip():
            bad.append(f"the Space front-matter has an indented line this check cannot read: "
                       f"{line.strip()[:40]!r}")
            continue
        if ":" not in line:
            bad.append(f"the Space front-matter line {line[:40]!r} is not `key: value`")
            continue
        key, _, value = line.partition(":")
        meta[key.strip()] = value.strip()

    unknown = sorted(set(meta) - SPACE_FIELDS)
    if unknown:
        bad.append(f"the Space front-matter has fields Hugging Face does not accept: {unknown}")
    if meta.get("sdk") != "docker":
        bad.append(f"the Space front-matter says sdk={meta.get('sdk')!r}; this image needs docker")
    port = meta.get("app_port", "")
    if meta.get("sdk") == "docker" and not port.isdigit():
        bad.append(f"sdk is docker, so app_port must be a bare integer, not {port!r} "
                   f"(HF defaults to 7860)")
    for key in ("colorFrom", "colorTo"):
        if key in meta and meta[key] not in SPACE_COLORS:
            bad.append(f"{key}={meta[key]!r} is not one of HF's thumbnail colours")
    if not bad:
        print(f"  the Space front-matter is valid: {len(meta)} fields, all accepted by HF, "
              f"sdk=docker on port {port}")
    return bad


def main() -> int:
    finish = pathlib.Path("FINISH.md")
    if not finish.exists():
        print("  FAIL  FINISH.md is missing; it is the file this figure lives in")
        return 1
    said = re.search(r"uploads (\d+) files / ([\d.]+) MB", finish.read_text())
    if not said:
        print("  FAIL  FINISH.md no longer says what the deploy uploads")
        return 1

    for problem in space_front_matter():
        print(f"  FAIL  {problem}")
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
