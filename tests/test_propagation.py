"""Phase 2 checks: propagation (derive + cascade + audit trail) and localization."""

from __future__ import annotations

from decimal import Decimal

from tieout.constraints import Status
from tieout.engine import PropagatingEngine
from tieout.facts import (
    Fact,
    FactStore,
    FiscalPeriod,
    Period,
    Scale,
    Source,
    XbrlProv,
    make_dims,
)
from tieout.ontology import PeriodType
from tieout.registry import REGISTRY

DUR = Period(PeriodType.DURATION, 2023, FiscalPeriod.FY)
INST = Period(PeriodType.INSTANT, 2023, FiscalPeriod.FY)


def _f(concept, value, period, *, dims=None):
    return Fact(concept, Decimal(value), period, Source.XBRL,
                XbrlProv(tag=concept, context_ref="c", decimals=-6),
                decimals=-6, dimensions=make_dims(dims))


def test_propagation_cascades_with_audit_trail():
    # Filing states revenue, cogs, operating income, but NOT gross profit/margin.
    s = FactStore()
    s.add(_f("revenue.total", "100000000", DUR))
    s.add(_f("cogs.total", "60000000", DUR))
    s.add(_f("operating_income.total", "25000000", DUR))

    eng = PropagatingEngine(REGISTRY)
    eng.run(s, [DUR])
    derived = {f.concept: f for f in eng.derived_facts}

    # gross_profit = revenue - cogs = 40M  (was never reported)
    assert "gross_profit.total" in derived
    assert derived["gross_profit.total"].value == Decimal("40000000")
    # gross_margin = gross_profit / revenue = 0.40  (cascaded off a derived fact)
    assert "gross_margin.ratio" in derived
    assert abs(derived["gross_margin.ratio"].value - Decimal("0.4")) < Decimal("0.001")
    # opex = gross_profit - operating_income = 15M  (inverted operand)
    assert "opex.total" in derived
    assert derived["opex.total"].value == Decimal("15000000")
    # audit trail: derived gross margin cites the constraint + inputs
    prov = derived["gross_margin.ratio"].provenance
    assert prov.constraint_id == "margin.gross"
    assert len(prov.input_fact_ids) == 2


def test_localization_exonerates_the_corroborated_total():
    # revenue.total is corroborated by the gross-profit identity (and the derived
    # margins), so when the segment roll-up breaks, suspicion must shift OFF the
    # total and ONTO the segment members. (Honest limit: with only one roll-up
    # constraint touching them, the individual members can't be told apart —
    # that needs an independent signal, e.g. cross-period. We assert the property
    # that IS identifiable: the total is exonerated, segments are the suspects.)
    s = FactStore()
    s.add(_f("revenue.total", "100000000", DUR))
    s.add(_f("revenue.segment", "60000000", DUR, dims={"segment": "A"}))
    s.add(_f("revenue.segment", "30000000", DUR, dims={"segment": "B"}))  # breaks sum
    s.add(_f("cogs.total", "60000000", DUR))
    s.add(_f("gross_profit.total", "40000000", DUR))  # corroborates revenue.total

    eng = PropagatingEngine(REGISTRY)
    results = eng.run(s, [DUR])
    seg = next(r for r in results if r.template_id == "rev.segments_sum")
    assert seg.status is Status.VIOLATED

    score = dict(eng.localizations[seg.inst_id])
    rev_fid = eng.store.query("revenue.total", DUR, dimensions={})[0].fact_id
    seg_fids = [f.fact_id for f in eng.store.query("revenue.segment", DUR)]
    # every segment member is more suspect than the corroborated total
    assert all(score[sf] > score[rev_fid] for sf in seg_fids)
    # and the top-ranked suspect is a segment, not the total
    assert eng.localizations[seg.inst_id][0][0] in seg_fids
