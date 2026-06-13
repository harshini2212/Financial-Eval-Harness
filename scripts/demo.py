"""End-to-end tieout demo across multiple filings -> one combined report.

For each filing: ground-truth XBRL vs Claude (text) vs baseline (regex), scored on
the constraint layer with three-way attribution. No new API spend once cached.

  python scripts/demo.py                 # COST AMZN KHC
  python scripts/demo.py COST AMZN
"""

from __future__ import annotations

import sys
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from tieout.extract import (BaselineExtractor, LlmTextExtractor, ResponseCache,
                            XbrlDirectExtractor, claude_model)
from tieout.facts import FactStore
from tieout.ingest import EdgarClient
from tieout.ingest.text import edgar_text_provider
from tieout.ingest.xbrl import periods_in
from tieout.registry import REGISTRY
from tieout.report import build_scorecard, render_markdown

DEFAULT_TICKERS = ["COST", "AMZN", "KHC"]


def _store(facts) -> FactStore:
    s = FactStore(); s.add_all(facts); return s


def run_one(ticker: str, client: EdgarClient, text_provider):
    filing = client.find_10k(ticker)
    gt_facts = XbrlDirectExtractor().extract(filing)
    gt = _store(gt_facts)
    periods = periods_in(gt_facts)
    fy = max(p.fiscal_year for p in periods)

    claude = LlmTextExtractor(claude_model("claude-opus-4-8"),
                              ResponseCache(".cache/llm"), text_provider=text_provider)
    extractors = {
        "Claude (text)": _store(claude.extract(filing)),
        "Baseline (regex)": _store(BaselineExtractor(text_provider).extract(filing)),
    }
    scorecards = [build_scorecard(n, s, gt, REGISTRY, periods, fy)
                  for n, s in extractors.items()]
    return filing, scorecards


def main(tickers: list[str]) -> None:
    client = EdgarClient()
    text_provider = edgar_text_provider(client)

    parts = ["# tieout - multi-filing verification report\n",
             "Constraint-layer verification of LLM-extracted figures vs SEC XBRL "
             "ground truth, with three-way violation attribution.\n"]
    for t in tickers:
        filing, scorecards = run_one(t, client, text_provider)
        parts.append("\n---\n")
        parts.append(render_markdown(filing, scorecards))

    md = "\n".join(parts)
    out = Path("out/report.md")
    out.parent.mkdir(exist_ok=True)
    out.write_text(md, encoding="utf-8")
    print(md)
    print(f"\n[written to {out}]")


if __name__ == "__main__":
    main(sys.argv[1:] or DEFAULT_TICKERS)
