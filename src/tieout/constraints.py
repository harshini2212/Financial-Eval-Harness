"""Constraint templates, the structured expression tree, and the Binder.

A ConstraintTemplate is authored once (an abstract accounting identity). The
Binder explodes it against a specific filing's facts -> InstantiatedConstraints,
which are the nodes the engine evaluates. Keeping the expression a *structured
tree* (not an eval'd string) is what later lets the propagating engine solve a
template for any single missing operand.

Phase 1: full ~20-identity registry, interval mul/div for ratio definitions,
source-aware tolerance, and concept fallbacks (equity.total -> equity.parent for
filers without noncontrolling interest).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from enum import Enum
from typing import Callable

from .facts import Fact, FactStore, Period, Source
from .intervals import Interval, Tolerance


class Binding(str, Enum):
    CONSOLIDATED = "consolidated"  # the single un-dimensioned fact
    AGGREGATE = "aggregate"  # sum over all members of a dimension axis


# Axes that SPLIT a figure into parts (vs. axes that merely SELECT a view, like
# ConsolidationItemsAxis). When summing segment totals we must exclude facts that
# also carry a disaggregating axis, or a segment total gets double-counted by its
# own sub-rows (e.g. 3M's segment x product breakdown).
DISAGGREGATING_AXES = frozenset({"product", "geography"})


def is_aggregable(dims: dict, agg_dim: str) -> bool:
    """True if a fact is a clean total along `agg_dim` (no finer breakdown)."""
    if agg_dim not in dims:
        return False
    return not (set(dims) - {agg_dim}) & DISAGGREGATING_AXES


@dataclass(frozen=True)
class ConceptRef:
    concept: str
    binding: Binding = Binding.CONSOLIDATED
    aggregate_dim: str | None = None  # required iff binding == AGGREGATE
    fallbacks: tuple[str, ...] = ()  # tried in order if `concept` has no fact
    optional_zero: bool = False  # contribute 0 (not missing) when no fact exists
    #   used for line items that are genuinely 0 when untagged: redeemable/
    #   temporary equity, noncontrolling interest, equity-method income.


# --- Structured expression tree --------------------------------------------
Resolver = Callable[[ConceptRef], Interval | None]


def _interval_div(a: Interval, b: Interval) -> Interval | None:
    if b.lo <= 0 <= b.hi:  # denominator spans zero -> undefined
        return None
    pts = [a.lo / b.lo, a.lo / b.hi, a.hi / b.lo, a.hi / b.hi]
    return Interval(min(pts), max(pts))


def _interval_mul(a: Interval, b: Interval) -> Interval:
    pts = [a.lo * b.lo, a.lo * b.hi, a.hi * b.lo, a.hi * b.hi]
    return Interval(min(pts), max(pts))


class Expr:
    def eval(self, resolve: Resolver) -> Interval | None:  # pragma: no cover
        raise NotImplementedError

    def refs(self) -> list[ConceptRef]:  # pragma: no cover
        raise NotImplementedError


@dataclass(frozen=True)
class Ref(Expr):
    ref: ConceptRef

    def eval(self, resolve):
        return resolve(self.ref)

    def refs(self):
        return [self.ref]


@dataclass(frozen=True)
class Const(Expr):
    value: Decimal

    def eval(self, resolve):
        return Interval.exact(self.value)

    def refs(self):
        return []


@dataclass(frozen=True)
class Add(Expr):
    terms: tuple[Expr, ...]

    def eval(self, resolve):
        acc = Interval.exact(Decimal(0))
        for t in self.terms:
            v = t.eval(resolve)
            if v is None:
                return None
            acc = acc + v
        return acc

    def refs(self):
        return [r for t in self.terms for r in t.refs()]


@dataclass(frozen=True)
class Sub(Expr):
    left: Expr
    right: Expr

    def eval(self, resolve):
        a, b = self.left.eval(resolve), self.right.eval(resolve)
        return None if a is None or b is None else a - b

    def refs(self):
        return self.left.refs() + self.right.refs()


@dataclass(frozen=True)
class Div(Expr):
    num: Expr
    den: Expr

    def eval(self, resolve):
        a, b = self.num.eval(resolve), self.den.eval(resolve)
        return None if a is None or b is None else _interval_div(a, b)

    def refs(self):
        return self.num.refs() + self.den.refs()


@dataclass(frozen=True)
class Mul(Expr):
    left: Expr
    right: Expr

    def eval(self, resolve):
        a, b = self.left.eval(resolve), self.right.eval(resolve)
        return None if a is None or b is None else _interval_mul(a, b)

    def refs(self):
        return self.left.refs() + self.right.refs()


# --- Templates --------------------------------------------------------------


class ConstraintKind(str, Enum):
    EQUALITY = "equality"
    SUM = "sum"
    RATIO_DEF = "ratio_def"


class Severity(str, Enum):
    HARD = "hard"
    SOFT = "soft"


@dataclass(frozen=True)
class ConstraintTemplate:
    """An abstract accounting identity:  target  ≈  expr  (within tolerance)."""

    template_id: str
    kind: ConstraintKind
    description: str
    target: ConceptRef
    expr: Expr
    tolerance: Tolerance = field(default_factory=Tolerance)
    severity: Severity = Severity.HARD
    source: str = "hand_authored"

    def all_refs(self) -> list[ConceptRef]:
        return [self.target] + self.expr.refs()


class Status(str, Enum):
    SATISFIED = "satisfied"
    VIOLATED = "violated"
    INDETERMINATE = "indeterminate"


@dataclass
class InstantiatedConstraint:
    inst_id: str
    template_id: str
    period: Period
    target_interval: Interval | None
    expr_interval: Interval | None
    involved_fact_ids: list[str]
    missing_refs: list[str]
    status: Status
    residual: Decimal | None
    band: Decimal | None
    severity: Severity = Severity.HARD


# --- Binder -----------------------------------------------------------------


class Binder:
    """Resolves a template's ConceptRefs against a FactStore for one period.

    If `source` is given, only facts from that source are used (e.g. Source.XBRL
    for the attribution layer's ground-truth check), and tolerance switches to
    its ground-truth (tight) band.
    """

    def __init__(self, store: FactStore, *, source: Source | None = None,
                 ground_truth: bool | None = None) -> None:
        self.store = store
        self.source = source
        # `ground_truth` may be set explicitly (the propagating engine sees both
        # XBRL and derived facts via source=None, but still trusts the chain).
        self.ground_truth = (
            ground_truth if ground_truth is not None
            else source in (Source.XBRL, Source.GOLD)
        )

    def _resolve(self, ref, period, sink, missing):
        if ref.binding is Binding.CONSOLIDATED:
            for concept_id in (ref.concept, *ref.fallbacks):
                facts = self.store.query(concept_id, period, dimensions={},
                                         source=self.source)
                if facts:
                    sink.append(facts[0].fact_id)
                    return facts[0].as_interval()
            if ref.optional_zero:
                return Interval.exact(Decimal(0))
            missing.append(ref.concept)
            return None

        # AGGREGATE: sum the clean segment totals (excluding finer breakdowns).
        facts = [
            f for f in self.store.query(ref.concept, period, source=self.source)
            if is_aggregable(f.dims_dict(), ref.aggregate_dim)
        ]
        if not facts:
            missing.append(f"{ref.concept}[{ref.aggregate_dim}]")
            return None
        acc = Interval.exact(Decimal(0))
        for f in facts:
            acc = acc + f.as_interval()
            sink.append(f.fact_id)
        return acc

    def bind(self, template, period):
        involved: list[str] = []
        missing: list[str] = []

        def resolver(ref):
            return self._resolve(ref, period, involved, missing)

        target_iv = resolver(template.target)
        expr_iv = template.expr.eval(resolver)

        inst_id = f"{template.template_id}@{period.fiscal_year}{period.fiscal_period.value}"
        if target_iv is None or expr_iv is None:
            return InstantiatedConstraint(
                inst_id, template.template_id, period, target_iv, expr_iv,
                involved, missing, Status.INDETERMINATE, None, None,
                template.severity,
            )

        expected = expr_iv.midpoint
        actual = target_iv.midpoint
        residual = actual - expected
        rounding = (target_iv.width + expr_iv.width) / 2
        band = template.tolerance.band(expected, rounding=rounding,
                                       ground_truth=self.ground_truth)
        status = Status.SATISFIED if abs(residual) <= band else Status.VIOLATED
        return InstantiatedConstraint(
            inst_id, template.template_id, period, target_iv, expr_iv,
            involved, missing, status, residual, band, template.severity,
        )
