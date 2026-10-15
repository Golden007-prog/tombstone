# Graph Hacks — strategy brief (interim, built from verified recon)
Deadline: Oct 18 2026 23:59 IST. Solo entry. Paid LLM key available.

## 1. The de-facto rubric (no official one exists)
Reconstructed from two organizer-owned sources:

**A. WeMakeDevs' own tutorial** (linked from the Resources page). I read it directly to verify. There is no
literal "What judges look for" header, but the judging guidance is explicit and verbatim:
> "In all three tracks the judging comes back to whether the graph is doing work the agent could not do without it."
> "A project where the graph is a store the agent occasionally reads from is a project that any database would have served."
> **"Entries are judged within one track: one submission is judged in it."**

Its suggested demo moves and design rules:
1. Run the same question at TWO DEPTHS and show the contrast.
2. Show the agent DECLINING to answer when the graph has no relevant data.
3. "Fix the queries, parameterise them, and let the model choose between them rather than compose them."
   No model-generated string is ever concatenated into a query. **"The agent never writes a query."**
4. Validate entity names against the graph first; an unresolvable name yields "Unknown service" and
   nothing else runs. "A plausible service name is worse than no answer."
5. Every answer is one of FOUR SHAPES: answered with a path · answered from memory · not in the graph ·
   unknown entity. (A clean outcome taxonomy — worth copying.)
6. "An empty traversal means your graph does not know about a dependency" — an empty result is NOT proof
   that nothing is affected. Show coverage alongside any negative.
7. Use `ro_query` for anything not deliberately a write.
8. Parallel-edge trap: bind the relationship and reference it, or counts double.

Reference architecture: one database, six MCP tools (`blast_radius`, `who_to_wake`, `recent_changes`,
`path_between`, `load_bearing`, `recall`), one LLM. Only `algo.SPpaths` and `algo.pageRank` are
demonstrated — betweenness, harmonic, WCC, CDLP, MSF and MaxFlow are listed but never shown.

**B. WeMakeDevs x Cognee hackathon (Jun 2026, same organizer, same theme) published 6 criteria:**
Potential Impact · Creativity & Innovation · Technical Excellence · Best Use of <sponsor> · User Experience · Presentation Quality

**C. FalkorDB's own winner recap** (Memory Meets Motion, Aug 2026) — the patterns they praise in their own voice:
- 1st place Atrium won on ONE modelling move: **it made each wrong mental model its own node**, so students
  cluster by misconception. FalkorDB: "its cleverest move is graph-native", "a two-hop Cypher traversal that
  a flat table or a vector search simply cannot express."
- Hopper: walked advisory -> contract clause in <100ms and treated **"no path found" as proof of safety**,
  explicitly skipping vector search "because a negative result needs a real traversal, not a similarity score."
- Also praised: precedent written back into the graph; a deterministic non-LLM component with authority
  OVER the LLM; human approval gates; procedural memory compiled into reusable pipelines; failing loudly
  instead of falling back to canned output.

## 2. Organizer hard constraints (violating these is self-inflicted)
- **Video: 3 minutes max**, plain screen recording, product first, not an architecture diagram.
- **"We should not need to sign up or create an account to try it"** — Kunal Kushwaha, verbatim.
- Live deployment preferred. **Do NOT rely on FalkorDB Cloud free tier**: 100MB cap, stopped after 1 day
  idle, deleted after 7. A link submitted Oct 18 is likely dead when judged.
- Required artifacts: public repo · README with setup AND the graph data model · the Cypher/algorithms the
  product depends on · demo video · track(s) named. The data model and Cypher are REQUIRED, not nice-to-have.
- AI assistance must be disclosed; you must be able to explain the model, queries, architecture.
- Public/synthetic/own data only.

## 3. Field intelligence (independently verified by me via gh search)
93 public repos mention FalkorDB created since Oct 1; 119 deduped across search terms.
Track split: **T1 ~28 · T2 ~12 · T3 ~7.** T1 is ~4x T3.
Name clusters: graph 45 · brain 6 · code 5 · mem* 7 · blast 4 · ripple 3 · lineage 2.

Day-1 bar is HIGH, not low — strongest entries already have 87-1405 files and 15-41 commits:
- NishaadG/blastradius — supply-chain vuln triage, all 3 tracks, real OSV.dev + deps.dev + CODEOWNERS,
  MCP server, PageRank, graph-per-tenant, 10/50/100-agent concurrency benchmark, works at $0 with no key.
- hey-shiv/nodus — LIVE on Vercel, no signup, per-visitor isolated graph copy, models postmortem failures
  as structural role/relationship patterns.
- Vaibhaav-Tiwari/lineage — "a company brain that un-learns", 745 real PEPs + forum threads + maintainers.
- Tejas-Sands/undograph — 111 backend tests, Cloudflare Workers, measured before/after numbers.

## 4. SATURATED — do not build
- **Blast radius / on-call / incident impact.** The tutorial's OWN demo app is called "Blast Radius" and 4
  repos already carry the name. Building it marks you a tutorial follower.
- **Code graph / codebase intelligence.** FalkorDB ships `FalkorDB/code-graph` themselves (348 stars).
- **Fraud rings / SOC triage.** The prompt's own worked examples = maximally anchored. 7+ entries already.
- **Un-learning / staleness ripple / fact correction.** Saturated within 24h (ripple, lineage, undograph,
  honest-memory) and FalkorDB already praised "Drift" for it in August.
- **Generic "graph memory layer for agents" with no domain.** Mature incumbents (AutoMem 822*, MegaMem,
  Dragon-Brain, synapse) plus FalkorDB's own mem0-falkordb plugin. You lose the comparison.
- Text2Cypher as the headline — QueryWeaver (1,082*) is the sponsor's own tool.

## 5. OPENINGS (ranked, with evidence)
1. **Pick a domain outside devtools/security/enterprise.** Only ~2 of 93 repos do. Buys "Potential Impact"
   + "Creativity" almost free. The last WeMakeDevs winner was chosen partly for being "built for somebody
   who is not the user."
2. **Model the latent/abstract thing as a first-class node** — the exact move FalkorDB credited for 1st
   place. Unused candidates: the constraint, the assumption, the unstated prerequisite, the counterfactual.
3. **Proof-by-absence as a scripted demo beat** — "nothing connects here, and here is the traversal that
   proves it." On-rubric twice (tutorial item 3 + Hopper). Only 2 of 93 use absence as a feature.
4. **Procedural memory with a visible reuse counter** — approve once, graph compiles a playbook, counter
   proves reuse. This placed 2nd SOLO at the last WeMakeDevs hackathon. Nothing in the field leads with it.
5. **The rare algorithms, framed in FalkorDB's own words.** Everyone uses shortestPath + PageRank.
   FalkorDB's security blog itself maps betweenness -> privilege escalation, CDLP -> coordinated actors,
   WCC -> isolated systems. MaxFlow and MSF are untouched.
6. **The blog post side prize is the best EV on the board** — 1 winner, ~30-100 competitors instead of
   400-700, and FalkorDB's community-projects page is ALL blog posts (they amplify writing, not apps).
   Marginal cost near zero if written as the README narrative + video script.
7. **Ship the removal-test paragraph explicitly.** Two competitors already confessed in their READMEs that
   their demo survives without FalkorDB. Answering the question before it is asked costs five lines.

## 5b. DECISIVE: one track, not three
The tutorial states "one submission is judged in it." Combined with the field evidence that multi-track
claims read as broad-but-shallow (scout-falkordb), the right play is ONE track, maximum depth. Entering
extra tracks is at best free and at worst dilutive; it is not a strategy.

## 6. Track recommendation (preliminary)
T3 "Company Brain" is the least contested (~7 of 93) AND carries the best prize (M6 Mac Mini). Its hard
part is the data rule — no private company data — which is exactly why few attempt it well. Whoever solves
the public-company-corpus problem elegantly gets credibility the T1 crowd cannot buy.
Counterweight: T2 is literally the FalkorDB CEO's own slide deck ("Agent Amnesia"), so sponsor alignment is
highest there despite the cheapest prize. Pending the remaining 7 recon agents.

## Field re-census — 2026-10-15 17:40 IST (first census was 15:40)
Deduped total **127** repos (was 119). Nine new in two hours, so the field is still filling.

Four new entries sit closest to Tombstone's thesis. All four were checked directly:

| repo | thesis overlap | commits | data | live demo |
|---|---|---|---|---|
| `saksham-AI500/Graph_Hackathon-Company-Brain-` | **highest** — "ownership drift", "traces documented decisions", "abstains from unsupported claims" | **1** | GitHub API + **synthetic** | no |
| `harshedabdulla/node-and-nerve` | org context service, "trace decisions, retrieve evidence" | 5 | **fake / synthetic** | no |
| `atharvgaur1845/bidbrain` | "prove absences", "show the path behind every answer" | 5 | **synthetic** | no |
| `dhruvalgupta2003/precedent` | "a decision graph agents check before they act" | 8 | — | no (last push **Oct 12**, before the window opened) |

### What this changes
- **Proof-by-absence and path-showing are no longer uncontested.** `bidbrain` advertises both. They
  were two of the seven openings identified this morning; treat them as table stakes now.
- **Real public data at scale is MORE differentiating than it looked, not less.** Every one of the
  four closest competitors is on synthetic data, which confirms the ~95% figure holds even at the
  sharp end of the field. `saksham` plans to use the GitHub API, which is rate-limited to 60
  requests/hour unauthenticated — they will hit that wall.
- **Nothing in the field has a live deployment yet.**

### What still differentiates Tombstone, in order
1. **The rejected alternative as a first-class node** — 753 titled options extracted
   deterministically from a real corpus. Nobody else has this, and it is the Atrium winning move.
2. **`emeritus_approvers`** — Kubernetes writes its own attrition into a machine-readable field and
   nothing in the world reads it. 83 of 111 departed owners hold no current role.
3. **Betweenness for "whose departure cost most"** — an algorithm as the decision mechanism, which
   only ~2 of 110 entries attempt.
4. **Claims that falsify themselves** — `verify_claims.py` (15/15) and `eval_retrieval.py`
   (12/12 hits, 3/3 negative controls).
5. **A container that boots in 9s and needs no external database.**
