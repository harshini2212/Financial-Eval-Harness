"""Load a filing's XBRL via arelle and map it into provenanced Facts.

This is the ground-truth path: arelle resolves the inline-XBRL instance + its DTS
(us-gaap taxonomy, linkbases), and we project each numeric us-gaap fact that maps
to our ontology into a `Fact`. Contexts become Periods (+ dimensions), and XBRL's
`decimals` attribute drives the rounding band.

arelle is imported lazily so the Phase 0 core stays importable without it.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from ..facts import Fact, FiscalPeriod, Period, Source, XbrlProv, make_dims
from ..ontology import PeriodType, concept_for_gaap_tag
from .edgar import DEFAULT_USER_AGENT

# Dimension-axis normalisation: collapse common XBRL axes to short, stable keys
# the constraint registry can target (e.g. the "segment" key in rev.segments_sum).
_AXIS_MAP = {
    "StatementBusinessSegmentsAxis": "segment",
    "OperatingSegmentsAxis": "segment",
    "StatementGeographicalAxis": "geography",
    "ProductOrServiceAxis": "product",
    "ConsolidationItemsAxis": "consolidation_item",
}


def _normalize_axis(axis_local: str) -> str:
    if axis_local in _AXIS_MAP:
        return _AXIS_MAP[axis_local]
    return axis_local[:-4].lower() if axis_local.endswith("Axis") else axis_local


# A tag shared by a consolidated concept and its per-segment concept (e.g.
# RevenueFromContract...) must route to the .segment concept when the fact
# actually carries a segment dimension.
_SEGMENT_ROUTING = {
    "revenue.total": "revenue.segment",
    "operating_income.total": "operating_income.segment",
}


def _route_dimensional(concept_id: str, dims: dict[str, str]) -> str:
    if "segment" in dims and concept_id in _SEGMENT_ROUTING:
        return _SEGMENT_ROUTING[concept_id]
    return concept_id


def _parse_decimals(raw) -> int | None:
    if raw in (None, "INF"):
        return None
    try:
        return int(raw)
    except (TypeError, ValueError):
        return None


def _unit_code(fact) -> str:
    try:
        nums = fact.unit.measures[0]
        if nums:
            local = nums[0].localName
            if local == "USD":
                return "USD"
            if "shares" in local.lower():
                return "shares"
            return local
    except Exception:
        pass
    return "USD"


class XbrlLoader:
    """Holds one arelle controller; reuse across filings to share the cache."""

    def __init__(self, user_agent: str = DEFAULT_USER_AGENT, timeout: int = 60) -> None:
        from arelle import Cntlr  # lazy

        self._cntlr = Cntlr.Cntlr(logFileName="logToBuffer")
        self._cntlr.webCache.httpUserAgent = user_agent
        self._cntlr.webCache.timeout = timeout

    def load_facts(self, url: str, *, doc_id: str = "") -> list[Fact]:
        model = self._cntlr.modelManager.load(url)
        doc_id = doc_id or url.rsplit("/", 1)[-1]
        raw = list(model.facts)
        offset = self._fiscal_year_offset(raw)
        facts: list[Fact] = []
        for xf in raw:
            f = self._map_fact(xf, doc_id, offset)
            if f is not None:
                facts.append(f)
        self._cntlr.modelManager.close()
        return facts

    @staticmethod
    def _fiscal_year_offset(raw) -> int:
        """fiscal_year = context-end year + offset.

        Anchored on the filer's own DocumentFiscalYearFocus *and its context's end
        year* (the primary period). A 52/53-week filer whose FY2025 ends
        2026-01-01 reports focus=2025 against a context end year of 2026 -> offset
        -1. We must use that fact's OWN context end, not a global max, because
        forward-dated contexts (e.g. debt maturities) would otherwise inflate it.
        """
        for xf in raw:
            q = xf.qname
            if not (q and "dei" in (q.namespaceURI or "")
                    and q.localName == "DocumentFiscalYearFocus"):
                continue
            try:
                focus = int(str(xf.value or xf.xValue)[:4])
                end = xf.context.instantDatetime or xf.context.endDatetime
                return focus - end.year
            except Exception:
                return 0
        return 0

    @staticmethod
    def _map_fact(xf, doc_id: str, fy_offset: int = 0) -> Fact | None:
        q = xf.qname
        if not q or not q.namespaceURI or "us-gaap" not in q.namespaceURI:
            return None
        if not xf.isNumeric or xf.xValue is None:
            return None
        concept_id = concept_for_gaap_tag(q.localName)
        if concept_id is None:
            return None

        ctx = xf.context
        if ctx is None:
            return None
        try:
            if ctx.isInstantPeriod:
                end = ctx.instantDatetime.date()
                period = Period(PeriodType.INSTANT, end.year + fy_offset,
                                FiscalPeriod.FY, end=end.isoformat())
            elif ctx.isStartEndPeriod:
                start = ctx.startDatetime.date()
                end = ctx.endDatetime.date()
                period = Period(PeriodType.DURATION, end.year + fy_offset,
                                FiscalPeriod.FY, start=start.isoformat(),
                                end=end.isoformat())
            else:
                return None  # forever / undated context
        except Exception:
            return None

        dims = {
            _normalize_axis(d.dimensionQname.localName):
                (d.memberQname.localName if d.memberQname else "?")
            for d in ctx.qnameDims.values()
        } if ctx.qnameDims else {}
        concept_id = _route_dimensional(concept_id, dims)

        return Fact(
            concept=concept_id,
            value=Decimal(str(xf.xValue)),
            period=period,
            source=Source.XBRL,
            provenance=XbrlProv(tag=q.localName, context_ref=xf.contextID,
                                decimals=_parse_decimals(xf.decimals)),
            unit=_unit_code(xf),
            decimals=_parse_decimals(xf.decimals),
            dimensions=make_dims(dims),
        )


def periods_in(facts: list[Fact]) -> list[Period]:
    """Distinct periods present, newest-first by fiscal year then type."""
    seen: dict[tuple, Period] = {}
    for f in facts:
        seen[f.period.key()] = f.period
    return sorted(seen.values(),
                  key=lambda p: (-p.fiscal_year, p.type.value))
