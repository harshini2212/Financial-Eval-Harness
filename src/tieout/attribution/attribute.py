"""Three-way attribution of a constraint violation, using XBRL as disambiguator."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from enum import Enum

from ..constraints import (Binder, Binding, ConceptRef, ConstraintTemplate,
                           Severity, Status, is_aggregable)
from ..facts import FactStore, Period, Source
from ..intervals import Interval


class Label(str, Enum):
    EXTRACTION_ERROR = "extraction_error"
    FILING_INCONSISTENCY = "filing_inconsistency"
    CONSTRAINT_MODEL_ERROR = "constraint_model_error"
    UNDETERMINED = "undetermined"


@dataclass
class Attribution:
    template_id: str
    period: Period
    label: Label
    evidence: str
    text_residual: Decimal | None
    gt_status: Status


def _band(gt: Decimal) -> Decimal:
    return max(abs(gt) * Decimal("0.002"), Decimal("1000000"))


def _resolve_value(store, ref: ConceptRef, period, source) -> Decimal | None:
    if ref.binding is Binding.AGGREGATE:
        facts = [f for f in store.query(ref.concept, period, source=source)
                 if is_aggregable(f.dims_dict(), ref.aggregate_dim)]
        if not facts:
            return None
        return sum((f.value for f in facts), Decimal(0))
    for cid in (ref.concept, *ref.fallbacks):
        facts = store.query(cid, period, dimensions={}, source=source)
        if facts:
            return facts[0].value
    if ref.optional_zero:
        return Decimal(0)
    return None


def _disagreements(template, period, text_store, gt_store) -> list[str]:
    out: list[str] = []
    for ref in template.all_refs():
        tv = _resolve_value(text_store, ref, period, None)
        gv = _resolve_value(gt_store, ref, period, Source.XBRL)
        if tv is None or gv is None:
            continue
        if abs(tv - gv) > _band(gv):
            tag = (f"{ref.concept}[{ref.aggregate_dim}]"
                   if ref.binding is Binding.AGGREGATE else ref.concept)
            out.append(f"{tag}: text={tv:,.0f} vs xbrl={gv:,.0f} (delta {tv - gv:,.0f})")
    return out


def attribute_violation(template: ConstraintTemplate, period: Period,
                        text_store: FactStore, gt_store: FactStore
                        ) -> Attribution | None:
    """Attribute a single (template, period) — returns None if text isn't violated.

    Soft identities (approximate bridges) are advisory and not attributed as
    errors — only hard-identity violations carry an attribution.
    """
    if template.severity is Severity.SOFT:
        return None
    t = Binder(text_store, source=None, ground_truth=False).bind(template, period)
    if t.status is not Status.VIOLATED:
        return None
    g = Binder(gt_store, source=Source.XBRL, ground_truth=True).bind(template, period)

    if g.status is Status.VIOLATED:
        return Attribution(template.template_id, period, Label.FILING_INCONSISTENCY,
                           "ground-truth XBRL figures also break this identity",
                           t.residual, g.status)
    if g.status is Status.INDETERMINATE:
        return Attribution(template.template_id, period, Label.UNDETERMINED,
                           "no complete XBRL ground truth to disambiguate",
                           t.residual, g.status)
    diffs = _disagreements(template, period, text_store, gt_store)
    if diffs:
        return Attribution(template.template_id, period, Label.EXTRACTION_ERROR,
                           "; ".join(diffs), t.residual, g.status)
    return Attribution(template.template_id, period, Label.CONSTRAINT_MODEL_ERROR,
                       "extracted figures match ground truth, yet the identity fires",
                       t.residual, g.status)


def attribute_run(templates, periods, text_store, gt_store) -> list[Attribution]:
    """Attribute every text-side violation across templates × periods."""
    out: list[Attribution] = []
    for tmpl in templates:
        for period in periods:
            a = attribute_violation(tmpl, period, text_store, gt_store)
            if a is not None:
                out.append(a)
    return out
