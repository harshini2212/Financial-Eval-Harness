"""Diagnostic: dump raw us-gaap facts to understand ground-truth constraint misses.

  python scripts/inspect.py TICKER names <localName...>   # consolidated facts
  python scripts/inspect.py TICKER segrev                 # segment revenue members
"""

from __future__ import annotations

import sys

from arelle import Cntlr

from tieout.ingest import EdgarClient
from tieout.ingest.xbrl import _normalize_axis


def main() -> None:
    ticker, mode = sys.argv[1], sys.argv[2]
    names = set(sys.argv[3:])
    filing = EdgarClient().find_10k(ticker)
    c = Cntlr.Cntlr(logFileName="logToBuffer")
    c.webCache.httpUserAgent = "tieout-research hv2201@nyu.edu"
    m = c.modelManager.load(filing.url)
    print(f"{filing.issuer} FY{filing.fiscal_year}")

    out = []
    for f in m.facts:
        q = f.qname
        if not q or "us-gaap" not in (q.namespaceURI or "") or not f.isNumeric:
            continue
        if f.xValue is None:
            continue
        ctx = f.context
        dims = {_normalize_axis(d.dimensionQname.localName):
                (d.memberQname.localName if d.memberQname else "?")
                for d in ctx.qnameDims.values()} if ctx.qnameDims else {}
        try:
            end = (ctx.instantDatetime or ctx.endDatetime).date()
        except Exception:
            continue
        ln = q.localName
        if mode == "names" and ln in names and not dims:
            out.append((str(end), ln, str(f.xValue)))
        elif mode == "segrev" and ln in (
                "Revenues", "RevenueFromContractWithCustomerExcludingAssessedTax") \
                and "segment" in dims:
            out.append((str(end), dims.get("segment"), str(f.xValue)))
    for end, label, val in sorted(out, reverse=True):
        print(f"  {end}  {label:<60} {val}")


if __name__ == "__main__":
    main()
