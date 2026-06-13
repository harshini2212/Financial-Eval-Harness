"""Phase 3 live: extract figures from filing TEXT with Claude, check vs XBRL.

One real (cached) Claude call. Shows the text-extracted figures agreeing or
disagreeing with the structured ground truth — the raw material for Phase 4
attribution — and runs the constraint engine over the model's own extractions.
"""

from __future__ import annotations

import sys
from decimal import Decimal

from tieout.engine import PropagatingEngine
from tieout.extract import LlmTextExtractor, ResponseCache, claude_model
from tieout.extract.xbrl_direct import XbrlDirectExtractor
from tieout.facts import FactStore, Source
from tieout.ingest import EdgarClient
from tieout.ingest.text import edgar_text_provider
from tieout.ingest.xbrl import periods_in


def main(ticker: str = "COST") -> None:
    client = EdgarClient()
    filing = client.find_10k(ticker)
    print(f"{filing.issuer} ({filing.ticker}) FY{filing.fiscal_year}\n")

    # Ground truth
    gt_facts = XbrlDirectExtractor().extract(filing)
    gt = FactStore(); gt.add_all(gt_facts)
    periods = periods_in(gt_facts)
    fy = max(p.fiscal_year for p in periods)

    # Claude extraction from text (1 cached call)
    extractor = LlmTextExtractor(
        claude_model("claude-opus-4-8"),
        ResponseCache(".cache/llm"),
        text_provider=edgar_text_provider(client, size=60000),
    )
    text_facts = extractor.extract(filing)
    tx = FactStore(); tx.add_all(text_facts)
    print(f"Claude extracted {len(text_facts)} facts "
          f"({sum(1 for f in text_facts if f.period.fiscal_year == fy)} for FY{fy})\n")

    print(f"=== Claude (text) vs XBRL (ground truth), FY{fy} consolidated ===")
    agree = disagree = noground = 0
    for f in sorted(text_facts, key=lambda x: x.concept):
        if f.period.fiscal_year != fy or f.dimensions or f.unit != "USD":
            continue
        g = gt.query(f.concept, f.period, dimensions={}, source=Source.XBRL)
        if not g:
            noground += 1
            print(f"  ?   {f.concept:<26} text={f.value:>16,.0f}   (no XBRL tag)")
            continue
        gv = g[0].value
        band = max(abs(gv) * Decimal("0.002"), Decimal("1000000"))
        ok = abs(f.value - gv) <= band
        agree += ok; disagree += (not ok)
        flag = "OK " if ok else "XX "
        note = "" if ok else f"   <-- DISAGREES (xbrl={gv:,.0f})"
        print(f"  {flag} {f.concept:<26} text={f.value:>16,.0f}{note}")
    print(f"\n  agree={agree}  disagree={disagree}  no-ground-truth={noground}")

    print(f"\n=== Constraint engine over Claude's OWN extractions, FY{fy} ===")
    eng = PropagatingEngine(REGISTRY := __import__(
        'tieout.registry', fromlist=['REGISTRY']).REGISTRY, ground_truth=False)
    results = eng.run(tx, periods)
    for r in results:
        if r.period.fiscal_year != fy or r.status.value == "indeterminate":
            continue
        extra = f" residual={r.residual:,.0f}" if r.residual is not None else ""
        print(f"  {r.status.value:<12} {r.template_id}{extra}")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "COST")
