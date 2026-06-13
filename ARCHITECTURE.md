# Architecture

`tieout` verifies LLM-extracted financial figures against deterministic
accounting identities, using a filing's own XBRL as ground truth. This document
describes the design; [PLAN.md](PLAN.md) covers the phased build.

## Principles

1. **The fact store is a deterministic snapshot.** LLM calls are non-deterministic,
   so extraction *outputs* are frozen (content-addressed cache) before they enter
   the store. Everything downstream is a pure function of that snapshot — the
   harness is reproducible even though the models aren't.
2. **Decimal everywhere; tolerance is interval arithmetic.** Money is `Decimal`;
   reconciliation uses rounding-aware intervals (driven by XBRL `decimals`),
   never `==`. Tolerance is source-aware: tight for ground truth, looser for prose.
3. **Abstract identity ≠ instantiated constraint.** A template (`Assets =
   Liabilities + Equity`) is *bound* to a filing's periods/segments to produce the
   concrete nodes the engine evaluates. Binding is where quantifiers live.

## The spine

```
EDGAR ingest ─▶ Concept Normalizer ─▶ Fact Store ─▶ Constraint Engine ─▶ Attribution ─▶ Report
        ▲                                  ▲
   Extractors ────────────────────────────┘
```

| Module | Responsibility |
|---|---|
| `ingest/edgar.py` | ticker → CIK → locate 10-K (primary inline-XBRL doc) |
| `ingest/xbrl.py` | arelle load → `Fact`s; period/dimension mapping; **52/53-week fiscal-year anchoring**; `decimals`-driven rounding |
| `ingest/text.py` | filing HTML → text; window the financial-statements section (skips the table of contents) |
| `ontology.py` | canonical concept space + us-gaap tag index (the dictionary that makes identities cross-source verifiable) |
| `facts.py` | provenanced `Fact` (discriminated-union provenance), `FactStore` snapshot |
| `extract/` | adapters behind one interface: `xbrl_direct` (truth), `llm_text` (under test, provider-agnostic + cached), `baseline` (regex floor) |
| `constraints.py` | structured `Expr` tree, `ConstraintTemplate`, the `Binder`, interval mul/div |
| `engine/` | backends: `checker` (A), `propagating` (B, headline), factor-graph (C, planned) |
| `attribution/` | three-way violation labelling via ground truth |
| `report/` | scorecards + discrimination/attribution markdown |

## Core data shapes

**Fact** (provenanced): `concept`, `value: Decimal` (base units), `period`,
`dimensions`, `source ∈ {xbrl,text,derived,gold}`, `provenance` (discriminated:
`XbrlProv{tag,context,decimals}` · `TextProv{model,prompt_version,raw_response_ref}`
· `DerivedProv{constraint_id,input_fact_ids,op}` · `GoldProv`), `decimals`, optional
explicit uncertainty `band`. `fact_id` is a content hash → automatic de-dup.

**ConstraintTemplate**: `target` + structured `expr` over `ConceptRef`s, a
`Tolerance`, and `severity ∈ {hard,soft}`. A `ConceptRef` carries a binding
(`consolidated` / `aggregate` over a dimension), `fallbacks` (e.g. equity.total →
equity.parent), and `optional_zero` (contribute 0 when untagged: mezzanine equity,
NCI, equity-method, discontinued ops). The `Binder` explodes templates into
`InstantiatedConstraint`s per matching period.

## Engine backends (one interface)

- **A — CheckerEngine**: boolean evaluation of instantiated constraints. Used for
  the scorecard (scores the model's *raw* extractions).
- **B — PropagatingEngine** (headline): solves any single missing slot (forward
  for the target, algebraic inversion for a missing operand across Add/Sub/Div/Mul),
  to fixpoint, emitting `derived` facts with a full provenance chain — so the graph
  both checks *and* fills gaps. Plus **localization**: ranks a violation's suspect
  facts by inverse "vouches" from satisfied constraints (correctly exonerates a
  corroborated total; documents the limit that sibling roll-up members need a
  cross-period signal to isolate).
- **C — factor graph** (planned): probabilistic per-figure confidence, behind the
  same interface, for one deliberately hard multi-error filing.

## Attribution (disambiguated by XBRL)

For a hard-identity violation on the text extraction:

| XBRL ground truth | Text vs truth | → label |
|---|---|---|
| satisfies the identity | a figure disagrees | **extraction_error** |
| breaks the identity itself | — | **filing_inconsistency** |
| satisfies, text matches it, yet rule fires | — | **constraint_model_error** |
| incomplete | — | **undetermined** |

Soft identities (the pretax→net bridge) are advisory and not attributed.

## Real-world XBRL handling (where the work actually is)

- **Fiscal-year anchoring** on `DocumentFiscalYearFocus` and *its own context's*
  end year (not a global max — forward-dated contexts would skew it). Handles
  52/53-week filers (Amazon FY2025 ends 2026-01-01).
- **Segment-total de-duplication**: aggregate only facts whose extra dimensions
  are *view selectors* (e.g. ConsolidationItems), excluding *disaggregating* axes
  (product/geography) — so 3M's segment×product rows don't double-count.
- **Structural completeness** via optional-zero terms: redeemable/temporary
  equity, noncontrolling interest, equity-method income, discontinued operations.
- **Determinism**: response cache keyed on the SHA-256 of the fully-rendered
  request (model + decoding params + prompt version + adapter version + rendered
  prompt), so a cache hit can only occur for bytes the model actually received.
