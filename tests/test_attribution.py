"""Phase 4: three-way attribution, disambiguated by XBRL ground truth."""

from __future__ import annotations

from decimal import Decimal

from tieout.attribution import Label, attribute_violation
from tieout.facts import (Fact, FactStore, FiscalPeriod, Period, Source,
                          XbrlProv, make_dims)
from tieout.ontology import PeriodType
from tieout.registry import REGISTRY

DUR = Period(PeriodType.DURATION, 2023, FiscalPeriod.FY)
SEG = next(t for t in REGISTRY if t.template_id == "rev.segments_sum")


def _fact(concept, value, source, *, dims=None):
    return Fact(concept, Decimal(value), DUR, source,
                XbrlProv(tag=concept, context_ref="c", decimals=-6),
                decimals=-6, dimensions=make_dims(dims))


def test_extraction_error_when_truth_reconciles_but_text_does_not():
    # Ground truth: segments sum to total. Text: a segment is wrong/missing.
    gt = FactStore()
    gt.add(_fact("revenue.total", "100000000", Source.XBRL))
    gt.add(_fact("revenue.segment", "60000000", Source.XBRL, dims={"segment": "A"}))
    gt.add(_fact("revenue.segment", "40000000", Source.XBRL, dims={"segment": "B"}))

    text = FactStore()
    text.add(_fact("revenue.total", "100000000", Source.TEXT))
    text.add(_fact("revenue.segment", "60000000", Source.TEXT, dims={"segment": "A"}))
    # segment B missing -> roll-up breaks

    a = attribute_violation(SEG, DUR, text, gt)
    assert a is not None and a.label is Label.EXTRACTION_ERROR


def test_filing_inconsistency_when_ground_truth_itself_breaks():
    # The XBRL ground truth itself doesn't tie out; text faithfully mirrors it.
    gt = FactStore()
    gt.add(_fact("revenue.total", "100000000", Source.XBRL))
    gt.add(_fact("revenue.segment", "60000000", Source.XBRL, dims={"segment": "A"}))
    gt.add(_fact("revenue.segment", "30000000", Source.XBRL, dims={"segment": "B"}))

    text = FactStore()
    text.add(_fact("revenue.total", "100000000", Source.TEXT))
    text.add(_fact("revenue.segment", "60000000", Source.TEXT, dims={"segment": "A"}))
    text.add(_fact("revenue.segment", "30000000", Source.TEXT, dims={"segment": "B"}))

    a = attribute_violation(SEG, DUR, text, gt)
    assert a is not None and a.label is Label.FILING_INCONSISTENCY
