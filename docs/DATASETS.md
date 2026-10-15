# Public dataset availability — probed live 2026-10-15, zero-auth unless noted

## TIER 1: zero auth, rich, graph-shaped, ingestible in <1h
| source | status | scale verified | graph shape |
|---|---|---|---|
| **openFDA drug/event (FAERS)** | HTTP 200 | warfarin 134,328 reports · metformin 432,899 · clopidogrel 108,617 · amiodarone 65,378. **ONE report carried 9 co-prescribed drugs** + indications + reaction + age/sex | Patient -TAKES-> Drug -INDICATED_FOR-> Condition; Patient -EXPERIENCED-> Reaction. Co-prescription edges emerge from co-occurrence. Intrinsically multi-hop. |
| **openFDA drug/label** | HTTP 200 | full structured labels | Drug -WARNS_ABOUT-> Interaction -WITH-> Drug |
| **OpenAlex** | HTTP 200 | **136,811 retracted works**; 143,455 institutions | Work -CITES-> Work; Author -AFFILIATED-> Institution. Retraction propagation = transitive closure. |
| **deps.dev** | HTTP 200 | pre-resolved dependency EDGES (68KB for `express` alone) | Package -DEPENDS_ON-> Package |
| **OSV.dev** | HTTP 200 | full vuln records incl. Log4j | Vuln -AFFECTS-> Package@range |
| **ClinicalTrials.gov v2** | HTTP 200 | full study protocol sections | Trial -STUDIES-> Condition, -USES-> Intervention, -SPONSORED_BY-> Org |
| **UniProt** | HTTP 200 | 180KB for one query | Protein -INTERACTS-> Protein -ASSOCIATED-> Disease |
| **Wikidata SPARQL** | HTTP 200 | arbitrary org/person graphs | anything |
| **Crossref** | HTTP 200 | 187M+ works | Work -REFERENCES-> Work |
| **SEC EDGAR** | HTTP 200 **only with User-Agent header** | Apple: 1,001 recent filings, 3 former names | Company -FILED-> Filing; Person -OFFICER_OF-> Company |
| MusicBrainz / Open Food Facts / MONDO-OLS4 | HTTP 200 | - | - |

## BLOCKED / needs work
- **OpenSanctions**: HTTP 401, needs API key.
- **GovTrack**: HTTP 403 Cloudflare challenge.
- **GDELT**: HTTP 429, hard 1-request-per-5s limit. Unusable for bulk ingest in a sprint.
- **arXiv**: HTTP 301 (use the https endpoint).

## Field context (verified)
~95% of the ~110 Graph Hacks entries use an INVENTED Acme-style synthetic company. Only four use real
public data: shaky-ground (Retraction Watch/Crossref/OpenAlex), downstream (real PyPI), ripplekg (real
disruptions + stock events), gaming-multiverse-reasoner (IGDB). shaky-ground is the only entry in the
field with verifiable numbers in its README.
=> Real public data is itself a differentiator worth more than most features.

## Data-policy note
Rules allow "public, synthetic, or their own" and forbid "private, login-protected, paywalled, personal
or otherwise restricted". FAERS is de-identified public data the FDA publishes for research (age/sex
only, no identifiers), so it qualifies — but any health-adjacent build must frame itself as signal
detection for researchers, never as clinical advice, and must carry the FDA's own disclaimer.

## NEGATIVE RESULT: FAERS prescribing cascades — tested and REJECTED
Spiked it properly (800 real reports across amlodipine / donepezil / risperidone / hydrochlorothiazide).

Mechanically it works: 1,832 distinct drugs, 1,013 reactions, 21,453 drug->reaction edges,
28,123 drug-codrug edges, 1,736 drug->indication edges, 41,590 candidate 2-hop "cascade" paths.

**But the signal is scientifically indefensible:**
- `HYDROCHLOROTHIAZIDE --causes(15)--> PAIN <--treats(4)-- OXYCODONE`. MedDRA terms like "PAIN" and
  "SEDATION" are far too generic to support a causal reading.
- `RISPERIDONE --causes(21)--> SEDATION <--treats(1)-- LORAZEPAM`. Lorazepam *causes* sedation; it does
  not treat it. The FAERS `drugindication` field is user-entered and unreliable.
- 41,590 "cascades" out of 800 reports is a false-positive factory: FAERS is a spontaneous reporting
  system with enormous confounding, no denominator, and no causality assertion (the FDA says so itself).

Any judge with pharmacology knowledge dismantles this with one question, and dressing noisy
spontaneous-report data as clinical findings is a bad bet on both ethics and credibility.
**Decision: do not build on FAERS cascades.** Keep openFDA only if a use case needs drug *labels*
(structured, authoritative) rather than inferred causality from event reports.
