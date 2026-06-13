# Build plan

Phased so something runs end-to-end early and the cut line falls on whole phases,
never half-wired modules. Status as of the current build.

## Phases (0–5 complete)

- **Phase 0 — Walking skeleton** ✅
  Ingest one filing's XBRL via arelle → ontology → `Fact`/`FactStore` → one
  identity → green check. Gold-set schema + loader (answers gated unverified).
  *Done: Costco FY2025 balance reconciles to residual 0 from live EDGAR XBRL.*

- **Phase 1 — Identity registry** ✅
  ~16 hand-authored identities (balance sheet, income, segments, ratios).
  Source-aware tolerance; interval division for ratio definitions; concept
  fallbacks. *Done: clean on Costco ground truth, zero false positives.*

- **Phase 2 — Propagating engine (headline)** ✅
  Fixpoint propagation (derive missing slots → derived facts with provenance);
  localization of violation suspects. *Done: derives Costco's unreported gross
  margin etc.; localization exonerates corroborated totals.*

- **Phase 3 — Extraction + comparison** ✅
  Provider-agnostic `llm_text` adapter (default Claude) + regex baseline +
  response cache. *Done: live on Costco/Amazon/Kraft Heinz; discrimination table.*

- **Phase 4 — Attribution** ✅
  Three-way label (extraction / filing-inconsistency / constraint-model /
  undetermined) via XBRL disambiguator; soft identities excluded. *Done.*

- **Phase 5 — Report** ✅
  Multi-filing scorecard + attribution breakdown → `out/report.md`. *Done.*

## Hardening done during the build (the "airtight" pass)

Real filings surfaced four would-be false positives; all fixed so ground truth
reconciles cleanly:
- Kraft Heinz balance off by $12M → **redeemable (mezzanine) equity** term.
- Amazon net income off by $554M → **equity-method income** term.
- 3M net income off by $1.4B → **discontinued operations** term.
- 3M segments off by $24B → **segment×product de-duplication**.
- Amazon/KHC extracted nothing → **52/53-week fiscal-year anchoring** + robust
  statement-window selection + larger token budget + truncation-salvage parsing.

## Cut line

Stretch items are last-in-first-cut; the cut falls between Phase 5 and stretch so
nothing is ever half-wired. A clean narrow B (hand-authored identities + the
discrimination table) beats a sprawling half-built B+C.

## Stretch / next

1. **Gold set**: hand-verify ~30–50 Q&A; add an LLM-judge baseline to quantify the
   caught-vs-passed "money metric" directly.
2. **Systematic eval**: sweep cheaper models / harder line items to measure
   catch-rate where it matters.
3. **Segment reconciliation**: explicit corporate/unallocated/eliminations terms
   so conglomerates (3M) evaluate instead of declining.
4. **XBRL calculation-linkbase harvester**: auto-derive filing-specific constraints.
5. **Factor-graph engine (C)**: probabilistic per-figure confidence on one hard filing.
