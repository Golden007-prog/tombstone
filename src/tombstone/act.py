"""The one thing this agent *does* rather than says.

Track 3's prize is for an agent that "understands how a company works **and gets work done**",
and the brief asks for one that "**acts** on connected data". Everything else in this product
answers questions. This module turns one of those answers into a reviewable change.

The finding it acts on is a record inconsistency the org itself created:

    a person is recorded as `emeritus_approvers` in N OWNERS files -- the project's own, explicit
    way of saying "they stepped back from this area" -- while one or two other files still name
    them an ACTIVE approver.

That is not automatically a bug, and this module never claims it is. `emeritus_approvers` is
per-area in Kubernetes, so stepping back from nine areas and deliberately keeping a tenth is
normal and correct. What makes a case worth a human's attention is the *shape*: a systematic
step-back across many areas with one straggler left behind. So the output is a drafted patch plus
the question to ask -- not an assertion that anything is broken.

Three guards exist because each one, left out, would have produced a wrong patch:

1. **Vendored paths are excluded.** `vendor/` and `third_party/` are synced from other
   repositories. The single strongest signal in this corpus -- one person recorded as emeritus in
   20 files, still an approver in exactly one -- is excluded by this rule, because that one file
   is `vendor/k8s.io/utils/ptr/OWNERS`, a copy of another repo's OWNERS. Patching it here would
   be reverted by the next sync.

2. **The handle must be literally named in the file.** An `APPROVES` edge can come from alias
   expansion: `approvers: [sig-cluster-lifecycle-leads]` expands to that group's members, so a
   person can hold approval authority over a file that never mentions them. There is no edit to
   that file that removes them. Those cases are reported with the alias named, and no patch is
   drafted, because the only real fix is to `OWNERS_ALIASES` -- a far more consequential change
   that no tool should draft unasked.

3. **Stranding is computed before the patch is offered.** If removing the handle would empty the
   `approvers` list, the file stops having its own approvers and silently starts inheriting from
   an ancestor. The draft says so, and names what would inherit it. This is the check a text tool
   cannot perform, because the consequence lives in the inheritance tree rather than in the file.

The diff is produced against a canonical re-serialisation of the PARSED file, not against the
bytes upstream: the committed snapshot stores parsed OWNERS structures, so comments and key order
from the original are not preserved. Every draft says this on its face. The patch is written to
disk for a human to read, and nothing is ever sent anywhere.
"""
from __future__ import annotations

import difflib

# Kubernetes writes OWNERS keys in this order. Anything unrecognised is kept, after these.
KEY_ORDER = ["approvers", "reviewers", "emeritus_approvers", "labels", "options"]

VENDORED_PREFIXES = ("vendor/", "third_party/")


def canonical(owners: dict) -> str:
    """Serialise an OWNERS dict the way Kubernetes writes one.

    Hand-rolled rather than `yaml.dump` so the output is predictable: block lists, two-space
    indent, no document markers, no line wrapping, no sorted-key surprises.
    """
    lines: list[str] = []
    keys = [k for k in KEY_ORDER if k in owners] + [k for k in owners if k not in KEY_ORDER]
    for key in keys:
        val = owners[key]
        if isinstance(val, list):
            if not val:
                continue
            lines.append(f"{key}:")
            lines.extend(f"  - {v}" for v in val)
        elif isinstance(val, dict):
            if not val:
                continue
            lines.append(f"{key}:")
            for k2, v2 in val.items():
                lines.append(f"  {k2}: {str(v2).lower() if isinstance(v2, bool) else v2}")
        else:
            lines.append(f"{key}: {val}")
    return "\n".join(lines) + "\n"


def retire(owners: dict, handle: str) -> dict:
    """Move `handle` out of approvers/reviewers and into emeritus_approvers."""
    out = {k: (list(v) if isinstance(v, list) else dict(v) if isinstance(v, dict) else v)
           for k, v in owners.items()}
    for field in ("approvers", "reviewers"):
        if field in out:
            out[field] = [h for h in out[field] if h != handle]
            if not out[field]:
                del out[field]
    emeritus = out.get("emeritus_approvers", [])
    if handle not in emeritus:
        emeritus = sorted([*emeritus, handle])
    out["emeritus_approvers"] = emeritus
    return out


def unified(path: str, before: dict, after: dict) -> str:
    return "".join(difflib.unified_diff(
        canonical(before).splitlines(keepends=True),
        canonical(after).splitlines(keepends=True),
        fromfile=f"a/{path}", tofile=f"b/{path}",
    ))


def classify(path: str, handle: str, owners: dict, aliases: dict) -> tuple[str, str]:
    """Decide whether this file can be patched for this handle, and why/why not."""
    if path.startswith(VENDORED_PREFIXES):
        return "vendored", (
            f"`{path}` is synced from another repository, so an edit here would be reverted by "
            f"the next sync. Excluded, not drafted.")
    declared = owners.get("approvers") or []
    if handle in declared:
        return "direct", ""
    # Not named: approval must arrive through an alias. Name it, so the human knows where to look.
    via = [a for a in declared if handle in (aliases.get(a) or [])]
    if via:
        return "via_alias", (
            f"`{handle}` is not named in `{path}`. Approval arrives through the alias "
            f"`{via[0]}`, so no edit to this file removes it -- the only real fix is to "
            f"OWNERS_ALIASES, which this tool will not draft.")
    return "unexplained", (
        f"`{handle}` holds approval over `{path}` but is neither named in it nor reachable "
        f"through any alias in it. That is a gap in this tool's understanding, not a finding.")


def strand_check(after: dict) -> bool:
    """Would the patched file have no approvers of its own left?"""
    return not (after.get("approvers") or [])
