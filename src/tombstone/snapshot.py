"""Export the parsed corpus to a committed snapshot, and seed a graph from it on boot.

Why this exists: the deploy target is a free tier with no persistent disk, and FalkorDB Cloud's
free tier stops after a day idle and is deleted after seven. Rather than fight that, the app
carries its own data: a compact JSON snapshot in the repo, loaded into a fresh FalkorDB on every
boot. Measured end to end at ~2s, so a cold start is container boot plus two seconds, and the
judge's link works whenever they click it.

It also means `git clone && docker compose up` reproduces the exact graph in the demo video with
no network access and no GitHub rate limit, which is what the setup instructions promise.
"""
from __future__ import annotations

import gzip
import json
import os
import time

SNAPSHOT = os.path.join(os.path.dirname(__file__), "..", "..", "data", "corpus.json.gz")
VECTORS = os.path.join(os.path.dirname(__file__), "..", "..", "data", "vectors.npy")


def export(corpus, path: str = SNAPSHOT) -> dict:
    """Serialise exactly what build() needs -- no markdown bodies beyond the alternatives."""
    from tombstone.corpus import rejected_alternatives

    alts = {}
    for rel, md in corpus.readmes.items():
        if rel not in corpus.keps:
            continue
        found = []
        for i, (title, body) in enumerate(rejected_alternatives(md)):
            if body and len(body) >= 100:
                found.append({"i": i, "title": title, "body": " ".join(body.split())[:1800]})
        if found:
            alts[rel] = found

    payload = {
        "schema": 1,
        "source": {
            "enhancements": "kubernetes/enhancements @ master (Apache-2.0)",
            "kubernetes": "kubernetes/kubernetes OWNERS @ master (Apache-2.0)",
            "note": "Alternatives are pre-extracted here; HTML comments already stripped.",
        },
        "keps": {k: _slim_kep(v) for k, v in corpus.keps.items()},
        "alternatives": alts,
        "owners": {k: _slim_owners(v) for k, v in corpus.owners.items()},
        "owners_texts": corpus.owners_texts,
        "aliases": corpus.aliases,
        "legacy_files": corpus.legacy_files,
        "parse_failures": corpus.parse_failures,
    }
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    with gzip.open(path, "wt", encoding="utf-8") as f:
        json.dump(payload, f, separators=(",", ":"))
    return {
        "path": os.path.abspath(path),
        "bytes": os.path.getsize(path),
        "keps": len(payload["keps"]),
        "owners": len(payload["owners"]),
        "alt_keps": len(alts),
    }


_KEP_FIELDS = (
    "title", "kep-number", "status", "owning-sig", "stage", "creation-date",
    "authors", "approvers", "reviewers", "replaces", "superseded-by", "see-also",
)


def _slim_kep(d: dict) -> dict:
    out = {}
    for k in _KEP_FIELDS:
        if k in d and d[k] not in (None, "", []):
            v = d[k]
            out[k] = str(v) if hasattr(v, "isoformat") else v
    return out


def _slim_owners(d: dict) -> dict:
    return {
        k: d[k]
        for k in ("approvers", "reviewers", "emeritus_approvers", "labels", "options")
        if d.get(k)
    }


def export_vectors(keys: list[str], embeddings: list[list[float]], path: str = VECTORS) -> dict:
    """Persist the alternative embeddings alongside the corpus.

    Embedding 960 real ~1,400-character chunks takes ~115s at a measured 8.4/sec, which is far too
    long to pay on every cold start of a free-tier container. float16 halves the file for a
    cosine-similarity use case where the precision loss is irrelevant.
    """
    import numpy as np

    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    arr = np.asarray(embeddings, dtype="float16")
    np.save(path, arr)
    with open(path + ".keys.json", "w", encoding="utf-8") as f:
        json.dump(keys, f)
    return {"path": os.path.abspath(path), "bytes": os.path.getsize(path), "shape": list(arr.shape)}


def load_vectors(path: str = VECTORS):
    """Return (keys, list-of-float32-lists) or (None, None) when no cache is present."""
    import numpy as np

    if not os.path.exists(path) or not os.path.exists(path + ".keys.json"):
        return None, None
    arr = np.load(path).astype("float32")
    with open(path + ".keys.json", encoding="utf-8") as f:
        keys = json.load(f)
    return keys, arr.tolist()


def load(path: str = SNAPSHOT):
    """Rehydrate a Corpus from the snapshot. No network, no git, no rate limits."""
    from tombstone.corpus import Corpus

    with gzip.open(path, "rt", encoding="utf-8") as f:
        p = json.load(f)
    c = Corpus()
    c.keps = p["keps"]
    c.owners = p["owners"]
    c.owners_texts = p.get("owners_texts", {})
    c.aliases = p["aliases"]
    c.legacy_files = p.get("legacy_files", [])
    c.parse_failures = p.get("parse_failures", [])
    c._prebuilt_alternatives = p["alternatives"]  # build() prefers this over re-parsing markdown
    return c


if __name__ == "__main__":
    import sys

    from tombstone.corpus import Corpus

    enh = sys.argv[1] if len(sys.argv) > 1 else "/tmp/khack/enhancements/keps"
    k8s = sys.argv[2] if len(sys.argv) > 2 else "/tmp/khack/k8s"
    ali = sys.argv[3] if len(sys.argv) > 3 else "/tmp/khack/aliases.yaml"
    t0 = time.perf_counter()
    c = Corpus().load(enh, k8s, ali)
    info = export(c)
    print(f"exported in {time.perf_counter() - t0:.2f}s")
    for k, v in info.items():
        print(f"  {k:<12} {v}")
    t0 = time.perf_counter()
    c2 = load()
    print(f"reload from snapshot: {time.perf_counter() - t0:.2f}s  "
          f"({len(c2.keps)} keps, {len(c2.owners)} owners)")
