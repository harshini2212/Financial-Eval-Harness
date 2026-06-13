"""Phase 0 walking-skeleton check: facts -> constraints -> engine, end to end.

No network, no XBRL, no LLMs — a synthetic in-memory filing proves the engine is
correct on known inputs before real EDGAR data is plumbed in. Three cases:
  1. clean filing            -> every identity SATISFIED (no false positives)
  2. one wrong segment       -> rev.segments_sum VIOLATED (true positive)
  3. missing cogs            -> is.gross_profit INDETERMINATE (not a violation)
"""

from __future__ import annotations

from decimal import Decimal

from tieout.constraints import Status
from tieout.engine import CheckerEngine
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
from tieout.gold import GoldSet
from tieout.ontology import PeriodType
from tieout.registry import REGISTRY

FY23_DUR = Period(PeriodType.DURATION, 2023, FiscalPeriod.FY)
FY23_INST = Period(PeriodType.INSTANT, 2023, FiscalPeriod.FY)


def _xbrl(concept, value, period, *, dims=None, scale=Scale.MILLIONS):
    return Fact(
        concept=concept,
        value=Decimal(value),
        period=period,
        source=Source.XBRL,
        provenance=XbrlProv(tag=concept, context_ref="c-1"),
        reported_scale=scale,
        dimensions=make_dims(dims),
    )


def _clean_store() -> FactStore:
    s = FactStore()
    # Balance sheet (instant): 100 = 60 + 40
    s.add(_xbrl("assets.total", "100000000", FY23_INST))
    s.add(_xbrl("liabilities.total", "60000000", FY23_INST))
    s.add(_xbrl("equity.total", "40000000", FY23_INST))
    # Income (duration): revenue 100 = segments 60 + 40; gross profit 100 - 60 = 40
    s.add(_xbrl("revenue.total", "100000000", FY23_DUR))
    s.add(_xbrl("revenue.segment", "60000000", FY23_DUR, dims={"segment": "A"}))
    s.add(_xbrl("revenue.segment", "40000000", FY23_DUR, dims={"segment": "B"}))
    s.add(_xbrl("cogs.total", "60000000", FY23_DUR))
    s.add(_xbrl("gross_profit.total", "40000000", FY23_DUR))
    return s


def _status_by_template(results):
    return {r.template_id: r.status for r in results}


def test_clean_filing_all_satisfied():
    engine = CheckerEngine(REGISTRY)
    results = engine.run(_clean_store(), [FY23_DUR, FY23_INST])
    by = _status_by_template(results)
    assert by["bs.balance"] is Status.SATISFIED
    assert by["rev.segments_sum"] is Status.SATISFIED
    assert by["is.gross_profit"] is Status.SATISFIED


def test_wrong_segment_is_violation():
    s = _clean_store()
    # Overwrite segment B with a wrong value: 60 + 30 = 90 != 100.
    s.add(_xbrl("revenue.segment", "30000000", FY23_DUR, dims={"segment": "B"}))
    # Note: FactStore keeps both B facts (content-hashed); aggregate now sums
    # 60 + 40 + 30 = 130 -> still a violation. Use a fresh store to isolate.
    s2 = FactStore()
    for c, v, dims in [
        ("revenue.total", "100000000", None),
        ("revenue.segment", "60000000", {"segment": "A"}),
        ("revenue.segment", "30000000", {"segment": "B"}),
    ]:
        s2.add(_xbrl(c, v, FY23_DUR, dims=dims))
    results = CheckerEngine(REGISTRY).run(s2, [FY23_DUR])
    by = _status_by_template(results)
    assert by["rev.segments_sum"] is Status.VIOLATED


def test_missing_input_is_indeterminate():
    s = FactStore()
    s.add(_xbrl("revenue.total", "100000000", FY23_DUR))
    s.add(_xbrl("gross_profit.total", "40000000", FY23_DUR))
    # cogs.total absent -> gross-profit identity cannot be evaluated.
    results = CheckerEngine(REGISTRY).run(s, [FY23_DUR])
    by = _status_by_template(results)
    assert by["is.gross_profit"] is Status.INDETERMINATE


def test_rounding_tolerance_absorbs_subtotal_drift():
    # Components reported in millions: 60.4 + 39.5 rounds to 60 + 40 = 100,
    # but true total 99.9M vs reported 100M must NOT trip the identity.
    s = FactStore()
    s.add(_xbrl("revenue.total", "100000000", FY23_DUR, scale=Scale.MILLIONS))
    s.add(_xbrl("revenue.segment", "60000000", FY23_DUR, dims={"segment": "A"}))
    s.add(_xbrl("revenue.segment", "39000000", FY23_DUR, dims={"segment": "B"}))
    results = CheckerEngine(REGISTRY).run(s, [FY23_DUR])
    by = _status_by_template(results)
    # 60 + 39 = 99 vs 100: 1M gap, but two millions-scale inputs carry a ~1M
    # combined rounding band -> within tolerance, SATISFIED.
    assert by["rev.segments_sum"] is Status.SATISFIED
