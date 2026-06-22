"""Smoke-test the Felix agent + verifier on one filing."""
from __future__ import annotations
import sys

from tieout.agent import FelixAgent, verify_answer
from tieout.extract import XbrlDirectExtractor
from tieout.facts import FactStore
from tieout.ingest import EdgarClient

ticker = sys.argv[1] if len(sys.argv) > 1 else "COST"
model = sys.argv[2] if len(sys.argv) > 2 else "claude-opus-4-8"

filing = EdgarClient().find_10k(ticker)
store = FactStore(); store.add_all(XbrlDirectExtractor().extract(filing))
agent = FelixAgent(store, model_id=model)

qs = [
    f"What was {filing.issuer}'s gross margin in FY{filing.fiscal_year}?",
    f"What was net income attributable to the company in FY{filing.fiscal_year}?",
    f"What was the operating margin in FY{filing.fiscal_year}?",
]
for q in qs:
    a = agent.answer(q, filing.fiscal_year)
    v = verify_answer(a, store)
    print(f"\nQ: {q}")
    if a.error:
        print("  ERROR:", a.error); continue
    print(f"  A: {a.answer}")
    print(f"  value={a.value} {a.unit} | tool_calls={len(a.tool_calls)} | hit={a.cache_hit}")
    print(f"  TRUSTED={v.trusted}  retrieval_ok={v.retrieval_ok}  calc_ok={v.calculation_ok}")
    for c in v.checks:
        print(f"     {c.concept}={c.stated} vs truth={c.truth} ok={c.ok} {c.note}")
