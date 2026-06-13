"""Phase 2 demo on a real filing: propagation cascade + localization.

1. Load Costco ground truth, run the propagating engine, and show the facts the
   *graph derived* that the filing never stated (gross profit/margin, opex, ...),
   each with its provenance formula.
2. Inject one wrong segment figure and show the engine localize the culprit.
"""

from __future__ import annotations

import sys
from decimal import Decimal

from tieout.engine import PropagatingEngine
from tieout.facts import DerivedProv, Fact, FactStore, Source
from tieout.ingest import EdgarClient
from tieout.ingest.xbrl import periods_in
from tieout.extract import XbrlDirectExtractor
from tieout.registry import REGISTRY


def _fmt(f: Fact) -> str:
    if f.unit == "ratio":
        return f"{f.value:.4f}"
    return f"{f.value:,.0f}"


def main(ticker: str = "COST") -> None:
    filing = EdgarClient().find_10k(ticker)
    facts = XbrlDirectExtractor().extract(filing)
    store = FactStore()
    store.add_all(facts)
    periods = periods_in(facts)
    fy = max(p.fiscal_year for p in periods)

    print(f"{filing.issuer} ({filing.ticker}) FY{fy}\n")

    eng = PropagatingEngine(REGISTRY)
    eng.run(store, periods)

    print("=== Facts DERIVED by the graph (not stated in the filing) ===")
    for f in eng.derived_facts:
        if f.period.fiscal_year != fy:
            continue
        prov: DerivedProv = f.provenance
        print(f"  {f.concept:<24} = {_fmt(f):>16}   [{prov.op}]")

    # ---- Localization: inject one wrong segment figure ----
    seg_facts = [f for f in facts if f.concept == "revenue.segment"
                 and f.period.fiscal_year == fy]
    if not seg_facts:
        print("\n(no segment facts to perturb for localization demo)")
        return

    victim = max(seg_facts, key=lambda f: f.value)
    corrupted = Fact(victim.concept, victim.value + Decimal("5000000000"),
                     victim.period, Source.XBRL, victim.provenance,
                     decimals=victim.decimals, dimensions=victim.dimensions)
    store2 = FactStore()
    store2.add_all([f for f in facts if f.fact_id != victim.fact_id])
    store2.add(corrupted)

    print("\n=== Localization (injected +$5B error into segment "
          f"{dict(victim.dimensions).get('segment','?')}) ===")
    eng2 = PropagatingEngine(REGISTRY)
    results = eng2.run(store2, periods)
    for r in results:
        if r.template_id == "rev.segments_sum" and r.period.fiscal_year == fy:
            print(f"  {r.template_id}: {r.status.value}  residual={r.residual:,.0f}")
            ranked = eng2.localizations.get(r.inst_id, [])
            total_score = next(
                (s for fid, s in ranked
                 if not eng2.store.get(fid).dimensions), None)
            print(f"  -> consolidated revenue.total suspicion={total_score} "
                  "(exonerated: corroborated by margin identities)")
            print("  -> fault narrowed to the segment set "
                  "(single member needs cross-period signal to isolate):")
            for fid, score in ranked:
                f = eng2.store.get(fid)
                seg = dict(f.dimensions).get("segment")
                if seg:
                    print(f"       score={score:<5} {seg} = {_fmt(f)}")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "COST")
