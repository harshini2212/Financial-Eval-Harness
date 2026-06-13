"""Phase 0 end-to-end on a real EDGAR filing (ground-truth XBRL path).

Locate a 10-K -> extract facts via arelle -> run the checker -> print the
per-period reconciliation. Usage:  python scripts/phase0_real.py [TICKER]
"""

from __future__ import annotations

import sys

from tieout.engine import CheckerEngine
from tieout.extract import XbrlDirectExtractor
from tieout.facts import FactStore, Source
from tieout.ingest import EdgarClient
from tieout.ingest.xbrl import periods_in
from tieout.registry import REGISTRY

SYMBOL = {"satisfied": "OK ", "violated": "XX ", "indeterminate": ".. "}


def main(ticker: str = "COST") -> None:
    client = EdgarClient()
    filing = client.find_10k(ticker)
    print(f"{filing.issuer}  ({filing.ticker})  {filing.form} FY{filing.fiscal_year}"
          f"  filed {filing.filing_date}")
    print(f"  {filing.url}\n")

    facts = XbrlDirectExtractor().extract(filing)
    store = FactStore()
    store.add_all(facts)
    print(f"  mapped {len(facts)} ontology facts -> {len(store)} unique in store\n")

    periods = periods_in(facts)
    results = CheckerEngine(REGISTRY, source=Source.XBRL).run(store, periods)

    # Group by fiscal year for a readable scorecard.
    by_fy: dict[int, list] = {}
    for r in results:
        by_fy.setdefault(r.period.fiscal_year, []).append(r)

    for fy in sorted(by_fy, reverse=True):
        print(f"FY{fy}")
        for r in by_fy[fy]:
            line = f"  {SYMBOL[r.status.value]} {r.template_id:<18} {r.status.value:<14}"
            if r.residual is not None:
                line += f" residual={r.residual:>16,.0f}  band=+/-{r.band:>13,.0f}"
            elif r.missing_refs:
                line += f" missing: {', '.join(sorted(set(r.missing_refs)))}"
            print(line)
        print()


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "COST")
