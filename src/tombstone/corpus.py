"""Parse the Kubernetes governance corpus into graph-ready rows.

Kubernetes is used as the "company" because Track 3 forbids private company data and most of the
field is inventing an Acme Corp. Kubernetes is a real organisation of thousands of people that
publishes its decision records, its ownership map, and -- unusually -- its own attrition, all under
Apache-2.0. Every number this produces is checkable by a judge with one `git clone`.

Three traps are handled here deliberately, because each one silently corrupts the graph:

1. OWNERS files reference GROUP ALIASES (`sig-api-machinery-approvers`), not people. The expansion
   table lives in a separate OWNERS_ALIASES file. Skipping it turned 71 of 866 of my `Person` nodes
   into groups and left 293 approver references unexpanded.
2. KEP READMEs keep the template's own HTML comments, so `## Alternatives` sections are full of
   "<!-- What other approaches did you consider -->". Embedding those makes every vector query
   return the same four boilerplate hits at identical distance.
3. `status:` is genuinely dirty -- `imlpemented`, trailing whitespace, and uncleaned template
   strings like `provisional|implementable|implemented|...`.
"""
from __future__ import annotations

import os
import re
from dataclasses import dataclass, field

import yaml


class _StrDateLoader(yaml.SafeLoader):
    """YAML loader that leaves timestamps as strings.

    PyYAML eagerly converts an unquoted `2025-01-30` into a date, and raises
    `ValueError: month must be in 1..12` on a malformed one. The corpus contains exactly that:
    KEP-5075 carries `creation-date: 2025-30-01`. With a bare except around the parse, one typo
    silently removed the whole KEP -- and since four other KEPs cite it, it then showed up as a
    MISSING decision record. A manufactured absence is indistinguishable from a real one, which
    is fatal in a product whose central claim is absence. So: parse dates as text, validate later.
    """


_StrDateLoader.add_constructor(
    "tag:yaml.org,2002:timestamp",
    lambda loader, node: loader.construct_scalar(node),
)

COMMENT = re.compile(r"<!--.*?-->", re.S)
# Sub-headings inside an `Alternatives` section that are structure, not an option someone argued
# for and lost. Measured on the real corpus: these account for 28 of 753 titled sub-headings
# (3.7%). Dropping them raises precision without touching the genuine options, which often do not
# use the word "reject" at all ("LRU cache", "Alternative 1: new API + storage TTL").
STRUCTURAL_HEADING = re.compile(
    r"^(implementation(\s+sketch)?|notes?|summary|overview|background|design|details?|"
    r"appendix|references?|future\s+work|open\s+questions?|examples?|example:.*|"
    r"test(ing)?\s+plan|graduation|user\s+stories|goals?|non-goals?|"
    r"conclusion|prior\s+art|motivation|glossary|terminology|definitions?|"
    r"drawbacks?|risks?(\s+and\s+mitigations)?)\s*$",
    re.I,
)
HEADING = re.compile(r"^(#{1,6})\s*(.+?)\s*$")
PLACEHOLDER = {"n/a", "na", "tbd", "none", "-", "", "null", "todo", "?"}
VALID_STATUS = {
    "provisional", "implementable", "implemented", "deferred",
    "rejected", "withdrawn", "replaced", "superseded", "removed",
}
# the template leaves this pipe-joined list in place; it is not a status
TEMPLATE_STATUS = re.compile(r"\|")


def normalise_status(raw: str) -> tuple[str, str]:
    """Return (clean_status, raw). Unrecognisable values become 'unknown'."""
    r = str(raw or "")
    s = r.split("#")[0].strip().strip('"').strip().lower()
    if TEMPLATE_STATUS.search(s):
        return "unknown", r
    s = re.sub(r"\s*\(.*\)$", "", s).strip()
    if s in VALID_STATUS:
        return s, r
    # one real typo observed in the corpus
    if s == "imlpemented":
        return "implemented", r
    return ("unknown" if s else "unknown"), r


def strip_comments(md: str) -> str:
    return COMMENT.sub(" ", md)


def split_headings(md: str) -> dict[str, str]:
    """Flatten a markdown doc into {lowercased heading: body}."""
    out: dict[str, str] = {}
    last: str | None = None
    buf: list[str] = []
    for line in md.split("\n"):
        m = HEADING.match(line)
        if m:
            if last:
                out[last] = "\n".join(buf).strip()
            last = m.group(2).strip().lower()
            buf = []
        else:
            buf.append(line)
    if last:
        out[last] = "\n".join(buf).strip()
    return out


def rejected_alternatives(md: str) -> list[tuple[str | None, str]]:
    """Extract each titled option inside the KEP's `Alternatives` section.

    Returns (title, body) pairs. A sub-heading inside `Alternatives` IS one rejected option --
    the KEP template produces them, so this is deterministic and needs no LLM. Sections with no
    sub-headings yield a single (None, prose) entry.
    """
    md = strip_comments(md)
    lines = md.split("\n")
    start = lvl = None
    for i, line in enumerate(lines):
        m = re.match(r"^(#{1,4})\s*alternatives\s*$", line.strip(), re.I)
        if m:
            start, lvl = i, len(m.group(1))
            break
    if start is None:
        return []

    body: list[str] = []
    for line in lines[start + 1:]:
        m = re.match(r"^(#{1,4})\s", line)
        if m and len(m.group(1)) <= lvl:
            break
        body.append(line)

    out: list[tuple[str | None, str]] = []
    cur: str | None = None
    buf: list[str] = []

    def _flush() -> None:
        if cur and not STRUCTURAL_HEADING.match(cur):
            out.append((cur, "\n".join(buf).strip()))

    for line in body:
        m = HEADING.match(line)
        if m and len(m.group(1)) > lvl:
            _flush()
            cur, buf = m.group(2).strip(), []
        else:
            buf.append(line)
    _flush()
    if not out:
        prose = "\n".join(body).strip()
        if len(prose) > 120:
            return [(None, prose)]
    return out


def load_alias_table(path: str) -> dict[str, list[str]]:
    """Load OWNERS_ALIASES into {alias: [handles]}. Without this the ownership graph has groups
    standing in for people."""
    try:
        d = yaml.safe_load(open(path, encoding="utf-8", errors="replace")) or {}
    except Exception:
        return {}
    return {
        str(k).strip().lower(): [str(m).strip().lstrip("@").lower() for m in (v or [])]
        for k, v in (d.get("aliases") or {}).items()
    }


def expand(names, alias_table: dict[str, list[str]]) -> list[str]:
    out: list[str] = []
    for n in names or []:
        if not isinstance(n, str):
            continue
        h = n.strip().lstrip("@").lower()
        if not h or h in PLACEHOLDER:
            continue
        out.extend(alias_table.get(h, [h]))
    return out


def is_bot(handle: str) -> bool:
    h = handle.lower()
    return (
        h.endswith("[bot]") or h.endswith("-bot") or h.endswith("-robot")
        or "prow" in h or h in {"k8s-ci-robot", "k8s-publishing-bot"}
    )


# These are the KEP templates themselves, not decisions. They carry placeholder metadata
# (`creation-date: 'yyyy-mm-dd'`, `kep-number: NNNN`) and would otherwise show up as a decision
# with no date and no author.
TEMPLATE_PATHS = ("NNNN-kep-template", "0000-cloud-provider-template")


def is_template(rel_path: str, kep: dict) -> bool:
    if any(t in rel_path for t in TEMPLATE_PATHS):
        return True
    num = str(kep.get("kep-number", "")).strip().upper()
    return num in {"NNNN", ""} or num == "0"


@dataclass
class Corpus:
    keps: dict = field(default_factory=dict)
    parse_failures: list = field(default_factory=list)        # rel_path -> kep.yaml dict
    readmes: dict = field(default_factory=dict)     # rel_path -> markdown
    owners: dict = field(default_factory=dict)      # rel_path -> OWNERS dict
    owners_texts: dict = field(default_factory=dict)  # original policy text for targeted edits
    aliases: dict = field(default_factory=dict)
    legacy_files: list = field(default_factory=list)

    def load(self, enhancements_keps: str, k8s_root: str, aliases_path: str) -> "Corpus":
        self.aliases = load_alias_table(aliases_path)
        self._keps_root = enhancements_keps
        # Collect legacy flat-layout .md records up front so the snapshot can carry them. A
        # snapshot has no filesystem to walk, and if the two paths disagree the published
        # "broken references" number depends on how the graph was built.
        legacy = []
        for dp, _dn, fn in os.walk(enhancements_keps):
            for f in fn:
                if f.endswith(".md") and f != "README.md":
                    legacy.append(os.path.relpath(os.path.join(dp, f), enhancements_keps))
        self.legacy_files = sorted(legacy)
        for dp, _dn, fn in os.walk(enhancements_keps):
            rel = os.path.relpath(dp, enhancements_keps)
            if "kep.yaml" in fn:
                fp = os.path.join(dp, "kep.yaml")
                try:
                    d = yaml.load(open(fp, encoding="utf-8", errors="replace"), Loader=_StrDateLoader)
                    if isinstance(d, dict) and not is_template(rel, d):
                        self.keps[rel] = d
                except Exception as e:
                    # Never silent. A dropped KEP becomes a fake missing record downstream.
                    self.parse_failures.append({"path": rel, "error": f"{type(e).__name__}: {e}"})
            if "README.md" in fn:
                try:
                    self.readmes[rel] = open(os.path.join(dp, "README.md"), encoding="utf-8", errors="replace").read()
                except Exception:
                    pass
        for dp, _dn, fn in os.walk(k8s_root):
            if "/.git" in dp or "OWNERS" not in fn:
                continue
            p = os.path.join(dp, "OWNERS")
            try:
                with open(p, encoding="utf-8", newline="") as source:
                    text = source.read()
                d = yaml.load(text, Loader=_StrDateLoader)
                if isinstance(d, dict):
                    rel = os.path.relpath(p, k8s_root)
                    self.owners[rel] = d
                    self.owners_texts[rel] = text
            except Exception as e:
                self.parse_failures.append(
                    {"path": os.path.relpath(p, k8s_root), "error": f"{type(e).__name__}: {e}"})
        return self

    _keps_root: str = ""

    def resolver(self):
        """Resolve a lineage reference to a KEP dir, or classify why it does not resolve."""
        dirs = set(self.keps)
        bynum = {
            str(d.get("kep-number")): rel
            for rel, d in self.keps.items()
            if d.get("kep-number") is not None
        }

        # Legacy flat-layout records: before KEPs became directories they were single .md files,
        # and plenty of still-valid references point at those. Treat a reference whose file is
        # present on disk as RESOLVED, not broken -- counting it as decay inflates the finding.
        # A snapshot has no filesystem to walk, so the list is carried in it. Without this the
        # snapshot build counts 2 legacy references as broken that the live build resolves --
        # the two paths must agree or the published number depends on how you ran it.
        legacy = set(self.legacy_files)

        def resolve(ref: str) -> tuple[str | None, str]:
            s = (ref or "").strip()
            if s.lower().strip(".,;") in PLACEHOLDER:
                return None, "placeholder"
            if s.startswith("http://") or s.startswith("https://"):
                return None, "external"
            if s.startswith("[") and "](" in s:
                return None, "external"
            # `/kep/` instead of `/keps/` is a typo that appears in the corpus; normalising it is
            # resolution, not charity -- the target is unambiguous.
            t = re.sub(r"^/?keps?/", "", s).strip("/")
            if t in dirs:
                return t, "ok"
            if t in legacy or (t + ".md") in legacy:
                return None, "legacy-file"
            m = re.search(r"(\d{3,4})", t)
            if m and m.group(1) in bynum:
                return bynum[m.group(1)], "ok"
            return None, "broken"

        return resolve
