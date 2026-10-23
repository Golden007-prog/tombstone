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

Drafts use the original OWNERS text carried by the corpus. Missing, stale or unsupported
source is refused rather than reconstructed: a parsed mapping cannot preserve policy comments.
The patch is written to disk for a human to read, and nothing is ever sent anywhere.
"""
from __future__ import annotations

import difflib
import re

import yaml

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
    """Move `handle` out of approvers only and into emeritus_approvers."""
    out = {k: (list(v) if isinstance(v, list) else dict(v) if isinstance(v, dict) else v)
           for k, v in owners.items()}
    for field in ("approvers",):
        if field in out:
            out[field] = [h for h in out[field] if h != handle]
            if not out[field]:
                del out[field]
    emeritus = out.get("emeritus_approvers", [])
    if handle not in emeritus:
        emeritus = [*emeritus, handle]
    out["emeritus_approvers"] = emeritus
    return out


def retire_source(source: str, owners: dict, handle: str) -> str:
    """Make a targeted approval edit, or refuse a source we cannot preserve."""
    if not isinstance(source, str) or not source or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9-]*", handle):
        raise ValueError("original OWNERS text and a literal GitHub handle are required")
    if not source.endswith("\n"):
        raise ValueError("OWNERS text without a final newline needs a manual edit")
    try:
        events = list(yaml.parse(source))
        if any(isinstance(e, yaml.AliasEvent) or getattr(e, "anchor", None) for e in events):
            raise ValueError("OWNERS anchors and aliases need a manual edit")
        parsed = yaml.safe_load(source)
        tree = yaml.compose(source)
    except yaml.YAMLError as exc:
        raise ValueError("original OWNERS text is not a single valid YAML mapping") from exc
    if parsed != owners or not isinstance(tree, yaml.MappingNode):
        raise ValueError("original OWNERS text does not match the parsed ownership record")

    def check(node):
        if isinstance(node, yaml.MappingNode):
            if node.flow_style:
                raise ValueError("flow-style OWNERS mappings need a manual edit")
            names = [k.value for k, _ in node.value]
            if len(set(names)) != len(names):
                raise ValueError("duplicate OWNERS keys need a manual edit")
            for key, value in node.value:
                if not isinstance(key, yaml.ScalarNode):
                    raise ValueError("complex OWNERS keys need a manual edit")
                check(value)
        elif isinstance(node, yaml.SequenceNode):
            if node.flow_style:
                raise ValueError("flow-style OWNERS lists need a manual edit")
            for item in node.value:
                check(item)

    check(tree)
    entries = {key.value: (key, value) for key, value in tree.value}
    approvers = owners.get("approvers")
    if not isinstance(approvers, list) or handle not in approvers:
        raise ValueError("the finding does not name a direct approver")
    key, sequence = entries["approvers"]
    if not isinstance(sequence, yaml.SequenceNode):
        raise ValueError("approvers must be a block list")
    lines = source.splitlines(keepends=True)
    newline = "\r\n" if "\r\n" in source else "\n"
    edits = {}
    additions = {}

    def remove_line(line_number, end_column, prefix):
        tail = lines[line_number][end_column:].rstrip("\r\n")
        if tail.strip() and not tail.lstrip().startswith("#"):
            raise ValueError("OWNERS entries sharing a line need a manual edit")
        edits[line_number] = prefix + tail.lstrip() + newline if tail.strip() else ""

    for item in sequence.value:
        if not isinstance(item, yaml.ScalarNode) or item.start_mark.line != item.end_mark.line:
            raise ValueError("approvers must contain one literal handle per line")
        if item.value != handle:
            continue
        prefix = lines[item.start_mark.line][:item.start_mark.column]
        if not re.fullmatch(r"\s*-\s*", prefix):
            raise ValueError("approvers must contain one literal handle per line")
        remove_line(item.start_mark.line, item.end_mark.column, prefix[:prefix.index("-")])
    if not [name for name in approvers if name != handle]:
        header = lines[key.start_mark.line]
        comment = header.find("#", key.end_mark.column)
        edits[key.start_mark.line] = (header[:key.start_mark.column] + header[comment:].rstrip("\r\n")
                                     + newline) if comment >= 0 else ""

    emeritus = owners.get("emeritus_approvers", [])
    if not isinstance(emeritus, list):
        raise ValueError("emeritus_approvers must be a block list")
    if handle not in emeritus:
        if "emeritus_approvers" in entries:
            _, old = entries["emeritus_approvers"]
            if not isinstance(old, yaml.SequenceNode) or not old.value:
                raise ValueError("emeritus_approvers must be a nonempty block list")
            if any(not isinstance(item, yaml.ScalarNode)
                   or item.start_mark.line != item.end_mark.line for item in old.value):
                raise ValueError("emeritus_approvers must contain one literal handle per line")
            indent = " " * max(0, old.value[0].start_mark.column - 2)
            additions[old.value[-1].end_mark.line + 1] = indent + "- " + handle + newline
        else:
            additions[len(lines)] = ("" if source.endswith(("\n", "\r")) else newline)
            additions[len(lines)] += "emeritus_approvers:" + newline + "  - " + handle + newline
    output = []
    for number, line in enumerate(lines):
        output.append(additions.get(number, ""))
        output.append(edits.get(number, line))
    output.append(additions.get(len(lines), ""))
    result = "".join(output)
    try:
        if yaml.safe_load(result) != retire(owners, handle):
            raise ValueError("targeted edit did not preserve the ownership record")
    except yaml.YAMLError as exc:
        raise ValueError("targeted edit did not preserve valid OWNERS YAML") from exc
    return result


def unified_text(path: str, before: str, after: str) -> str:
    return "".join(difflib.unified_diff(
        before.splitlines(keepends=True), after.splitlines(keepends=True),
        fromfile=f"a/{path}", tofile=f"b/{path}",
    ))


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
