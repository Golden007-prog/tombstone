"""Route a typed question to a tool with no API key, and say so when it cannot.

The hosted demo has no LLM key -- a personal key cannot safely power a public site -- and the
consequence was that the ask box was *disabled*. A judge landed on the page and the most prominent
control on it was dead, which makes an agent look like a button panel.

This routes locally instead, with the embedding model already baked into the image (BAAI/bge-
small-en-v1.5, 384-dim, no network). Each tool carries a handful of example phrasings; the
question is embedded and compared against them; the nearest tool wins.

Three properties are kept deliberately:

* **The router picks a tool NAME. It never writes Cypher, and never writes prose.** That is the
  same contract the LLM path has, so turning the key off changes who chooses, not what runs.
* **It is allowed to refuse.** If nothing is close enough, or the top two are too close to call,
  it returns no tool and names what it nearly matched. A router that always picks something is a
  router that is confidently wrong on anything outside its catalogue.
* **It is deterministic.** The same question routes the same way on every machine, which is why
  the behaviour can be tested at all.

Arguments are extracted by rule, never generated: a path-shaped token for `who_owns`, handles
matched against people who actually exist in the graph, and the question itself as the search text
for `has_this_been_tried`.
"""
from __future__ import annotations

import re

import numpy as np

from tombstone.embedding import LOCK as _EMBED_LOCK, embed_rows

# Example phrasings per tool. These are routing data, and they double as documentation of what
# each tool is actually for. A question is matched against the BEST single phrase of a tool, not
# the average, so adding a phrasing can only ever help that tool.
PHRASES: dict[str, list[str]] = {
    "has_this_been_tried": [
        "has anyone tried this before",
        "was this idea already proposed and rejected",
        "did someone already consider doing this",
        "has this approach been refused before and why",
    
        "was this option considered and turned down",
        "did a proposal already evaluate this approach",
    ],
    "who_owns": [
        "who owns this area of the codebase",
        "who approves changes to this directory",
        "who is responsible for this file",
        "who maintains this path",
    
        "which people can merge changes here",
        "who are the current approvers of this directory",
    ],
    "ownership_dilution": [
        "which areas lost every dedicated owner",
        "which directories have no owners of their own any more",
        "what code fell back to a broader group for approval",
        "which areas are now owned only by inheritance",
    
        "where has ownership emptied out entirely",
        "which code now relies on a parent group for review",
    ],
    "stepped_back_bridges": [
        "whose departure cost the most knowledge",
        "who was the biggest bridge between teams",
        "whose stepping back cost the most connective authority",
        "which departure hurt the structure most",
    
        "whose leaving removed the most connection between groups",
        "which person's exit mattered most structurally",
        "who was the greatest loss when they stopped reviewing things",
    ],
    "successor_for": [
        "who should inherit this person's areas",
        "who can take over from someone who left",
        "who already co-owns what this person owned",
        "who is the natural successor",
    
        "who would naturally pick up this person's areas",
        "who shares ownership with this person already",
    ],
    "broken_lineage": [
        "which cited decisions do not exist",
        "what references point at missing records",
        "which proposals cite something that is not there",
        "find broken links between decisions",
    
        "do we reference records that were never created",
        "which citations point at nothing",
    ],
    "hollowing_communities": [
        "which contributor group is hollowing out",
        "which community is losing its people fastest",
        "which team is shrinking",
        "where is attrition concentrated",
    
        "which group of contributors is shrinking fastest",
        "is any cluster of people disappearing",
    ],
    "sole_approver_risk": [
        "which areas have exactly one approver",
        "where is the bus factor one",
        "who holds an area alone",
        "what has a single point of failure in approval",
    
        "where does review depend on a single person",
        "which paths have only one person who can approve",
    ],
    "what_if_they_go": [
        "what if these people stepped back",
        "what breaks if this group leaves",
        "simulate these people no longer approving",
        "which areas would be left with no owner if they go",
    
        "what would be stranded if these people stopped approving",
        "model the impact of losing these reviewers",
    ],
    "stale_knowledge": [
        "what knowledge here is going stale",
        "which decisions are still undecided years later",
        "what is rotting in this record",
        "which old proposals are still cited but never resolved",
    
        "which records have gone out of date",
        "what is still referenced but no longer current",
    ],
    "stepped_back_but_still_listed": [
        "whose ownership record contradicts itself",
        "who stepped back but is still listed as an approver",
        "which records are inconsistent about who approves",
    
        "whose entries disagree with each other",
        "which ownership records are inconsistent",
    ],
    "draft_owners_patch": [
        "draft the fix",
        "write the patch for the ownership problem",
        "fix the owners file",
        "propose a change rather than just reporting it",
    
        "produce the OWNERS edit that corrects this",
        "write the change that fixes the ownership records",
    ],
    "recall": [
        "has this graph been asked this before",
        "what did you answer last time",
        "do you remember this question",
    ],
}

# Out-of-domain examples, modelled as a pseudo-tool. Without these, routing is an open-set
# problem solved by a threshold, and a threshold cannot tell "unlike anything" from "a bit like
# everything": "write me a poem about kubernetes" scored 0.631 against `draft_owners_patch` and
# was accepted, which is a confidently wrong route into an ACTION tool. Giving the router
# somewhere correct to land fixes that far more reliably than nudging the cutoff upward.
NONE = "__out_of_domain__"
PHRASES[NONE] = [
    "help me fix this error",
    "why is my build failing",
    "debug this stack trace for me",
    "review my pull request for style",
    "how do i install this on my laptop",
    "what should i name this variable",
    "write me a poem",
    "tell me a joke",
    "what is the weather today",
    "translate this into french",
    "write python code to sort a list",
    "what is the capital of france",
    "how are you doing",
    "summarise this article for me",
    "what time is it",
    "explain what kubernetes is",
]

# Tools that cannot run without an argument the question has to supply.
REQUIRED: dict[str, str] = {"who_owns": "path", "successor_for": "handle",
                            "what_if_they_go": "handles"}

MIN_SCORE = 0.62     # below this, nothing in the catalogue is really being asked about
MIN_MARGIN = 0.015   # two tools this close is a coin toss, and a coin toss should be declined


class LocalRouter:
    """Embedding-similarity routing over a fixed catalogue. No key, no network, no prose."""

    def __init__(self, embedder, people: set[str] | None = None):
        self._embed = embedder
        self.people = people or set()
        self._tools: list[str] = []
        self._matrix: np.ndarray | None = None

    def _ready(self) -> None:
        # Double-checked under the embed lock, the same way `Agent.embedder` is and for the same
        # reason. That lock bounded the MODEL and not this: eight concurrent first asks all saw
        # `None` here and all built the 91-phrase matrix, so a cold burst embedded 736 rows where
        # 91 are needed -- on a target with a tenth of a CPU that sleeps after 15 minutes, which
        # is to say on exactly the cold start a judge arrives into. RLock, so re-entering it
        # inside `embed_rows` below is harmless.
        if self._matrix is not None:
            return
        with _EMBED_LOCK:
            if self._matrix is not None:
                return
            flat, owners = [], []
            for tool, phrases in PHRASES.items():
                for phrase in phrases:
                    flat.append(phrase)
                    owners.append(tool)
            vecs = np.asarray(embed_rows(self._embed, flat), dtype=np.float32)
            vecs /= np.linalg.norm(vecs, axis=1, keepdims=True) + 1e-9
            # `_tools` first, `_matrix` last: `_matrix` is the flag the fast path above tests, so
            # publishing it last means no reader sees a matrix beside an empty `_tools`.
            self._tools = owners
            self._matrix = vecs

    def route(self, question: str) -> dict:
        """-> {"tool": name, "args": {...}, "score": float} or {"tool": None, "near": [...]}"""
        self._ready()
        q = np.asarray(embed_rows(self._embed, [question])[0], dtype=np.float32)
        q /= np.linalg.norm(q) + 1e-9
        sims = self._matrix @ q

        best: dict[str, float] = {}
        for tool, score in zip(self._tools, sims):
            if score > best.get(tool, -1.0):
                best[tool] = float(score)
        ranked = sorted(best.items(), key=lambda kv: -kv[1])
        (top, top_score), (second, second_score) = ranked[0], ranked[1]

        near = [{"tool": t, "score": round(sc, 3)} for t, sc in ranked[:3] if t != NONE]
        if top == NONE:
            # `near` is kept for the response because it is useful to see what it scored against,
            # but `offer` is false: these must NOT be presented as choices. Offering the runners-up
            # for a question that is not about this graph at all would hand somebody asking for a
            # poem a button that drafts OWNERS patches -- which is the precise bug the
            # out-of-domain bucket was added to fix, rebuilt one layer higher up.
            return {"tool": None, "near": near, "offer": False,
                    "why": "that is not a question this graph answers"}
        if top_score < MIN_SCORE or (top_score - second_score) < MIN_MARGIN:
            # Offer the candidates ONLY for a genuine near-tie: two tools that both clear the
            # score bar and are within a hair of each other, where the question plainly IS about
            # this graph and the only open point is which of two readings was meant. When nothing
            # clears the bar, the top match is a weak guess, and dressing a weak guess as a
            # choice makes the user commit to it on the product's behalf.
            tie = top_score >= MIN_SCORE
            return {"tool": None, "near": near, "offer": tie,
                    "why": ("nothing in the catalogue is a clear match for that"
                            if top_score < MIN_SCORE
                            else f"'{top}' and '{second}' score too close to call")}

        args = self.args_for(top, question)
        needed = REQUIRED.get(top)
        if needed and not args.get(needed):
            # Running the tool anyway would return "no path supplied", which is honest and
            # useless. Naming what is missing is the same honesty with somewhere to go.
            # Not offered either: forcing the same tool would decline again for the same missing
            # argument, so a button here is a loop. The sentence names what to add instead.
            return {"tool": None, "near": near, "offer": False, "needs": needed, "intended": top,
                    "why": f"that reads like `{top}`, but it needs a {needed} and the question "
                           f"does not contain one"}
        return {"tool": top, "args": args, "score": round(top_score, 3),
                "runner_up": {"tool": second, "score": round(second_score, 3)}}

    def args_for(self, tool: str, question: str) -> dict:
        """Extract arguments by RULE. Nothing here is generated; it is read out of the question."""
        if tool == "has_this_been_tried":
            return {"idea_text": question}
        if tool == "recall":
            return {"question": question}
        if tool == "who_owns":
            path = self._path_in(question)
            return {"path": path, "depth": 4} if path else {}
        if tool in ("successor_for", "what_if_they_go"):
            handles = self._handles_in(question)
            if not handles:
                return {}
            return {"handle": handles[0]} if tool == "successor_for" else {"handles": handles}
        return {}

    def _path_in(self, question: str) -> str:
        """A path-shaped token. OWNERS files are keyed by the file, so add it when it is implied."""
        for token in re.findall(r"[A-Za-z0-9_./-]*/[A-Za-z0-9_./-]*", question):
            token = token.strip(".,;:'\"()")
            if "/" not in token:
                continue
            return token if token.endswith("/OWNERS") else f"{token.rstrip('/')}/OWNERS"
        return ""

    def _handles_in(self, question: str) -> list[str]:
        """Only handles that exist in the graph. An invented handle would be a fabricated person."""
        found = []
        for token in re.findall(r"[A-Za-z0-9_-]{2,}", question):
            handle = token.lower().lstrip("@")
            if handle in self.people and handle not in found:
                found.append(handle)
        return found
