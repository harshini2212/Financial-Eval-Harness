"""PropagatingEngine — the Phase 2 (B) backend, the headline.

Two capabilities the checker lacks:

  1. PROPAGATION. A constraint with exactly one missing slot is *solved* for that
     slot (target = expr, or expr inverted for a missing operand), emitting a
     `Source.DERIVED` fact whose DerivedProv records the constraint and the input
     facts. Runs to fixpoint, so derivations cascade (revenue-cogs -> gross
     profit -> gross margin). This turns the "graph" into an audit trail and a
     gap-filler: the filing never stated gross margin, but the graph computes it
     with full provenance.

  2. LOCALIZATION. When a fact sits in several constraints and one fails, the
     facts it shares with *satisfied* constraints are vouched-for; the suspect is
     the one with the fewest vouches. Each violation carries a ranked suspect
     list — an actionable "this is the figure most likely wrong".

Determinism: propagation only fills genuinely-missing slots and never overwrites
an existing fact, so the augmented store is a pure function of the inputs.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from ..constraints import (
    Add,
    Binder,
    Binding,
    ConceptRef,
    ConstraintTemplate,
    Div,
    Expr,
    InstantiatedConstraint,
    Mul,
    Ref,
    Status,
    Sub,
    _interval_div,
    _interval_mul,
    is_aggregable,
)
from ..facts import DerivedProv, Fact, FactStore, Period, Source
from ..intervals import Interval
from ..ontology import DataType, concept as get_concept

_MAX_PASSES = 12


@dataclass
class Solved:
    concept: str
    interval: Interval
    input_fact_ids: list[str]
    op: str


def _expr_str(e: Expr) -> str:
    if isinstance(e, Ref):
        r = e.ref
        return f"sum({r.concept}[{r.aggregate_dim}])" if r.binding is Binding.AGGREGATE else r.concept
    if isinstance(e, Add):
        return " + ".join(_expr_str(t) for t in e.terms)
    if isinstance(e, Sub):
        return f"{_expr_str(e.left)} - {_expr_str(e.right)}"
    if isinstance(e, Div):
        return f"{_expr_str(e.num)} / {_expr_str(e.den)}"
    if isinstance(e, Mul):
        return f"{_expr_str(e.left)} * {_expr_str(e.right)}"
    return "?"


class PropagatingEngine:
    name = "propagating"

    def __init__(self, templates, *, ground_truth: bool = True) -> None:
        self.templates: tuple[ConstraintTemplate, ...] = tuple(templates)
        self.ground_truth = ground_truth
        # populated by run():
        self.derived_facts: list[Fact] = []
        self.localizations: dict[str, list[tuple[str, float]]] = {}
        self.store: FactStore | None = None

    # --- low-level resolution (consolidated + aggregate), returns ids ---
    @staticmethod
    def _resolve(store, ref: ConceptRef, period, source):
        if ref.binding is Binding.AGGREGATE:
            facts = [f for f in store.query(ref.concept, period, source=source)
                     if is_aggregable(f.dims_dict(), ref.aggregate_dim)]
            if not facts:
                return None
            acc = Interval.exact(Decimal(0))
            ids = []
            for f in facts:
                acc = acc + f.as_interval()
                ids.append(f.fact_id)
            return acc, ids
        for cid in (ref.concept, *ref.fallbacks):
            facts = store.query(cid, period, dimensions={}, source=source)
            if facts:
                return facts[0].as_interval(), [facts[0].fact_id]
        if ref.optional_zero:
            return Interval.exact(Decimal(0)), []
        return None

    def _operand_refs(self, expr: Expr) -> list[ConceptRef] | None:
        """Flatten a depth-1 expr into its operand ConceptRefs (registry shape)."""
        if isinstance(expr, Ref):
            return [expr.ref]
        if isinstance(expr, Add) and all(isinstance(t, Ref) for t in expr.terms):
            return [t.ref for t in expr.terms]
        if isinstance(expr, (Sub, Div, Mul)):
            a = expr.left if isinstance(expr, (Sub, Mul)) else expr.num
            b = expr.right if isinstance(expr, (Sub, Mul)) else expr.den
            if isinstance(a, Ref) and isinstance(b, Ref):
                return [a.ref, b.ref]
        return None

    def _try_solve(self, tmpl: ConstraintTemplate, period, store) -> Solved | None:
        ops = self._operand_refs(tmpl.expr)
        if ops is None:
            return None
        tgt = self._resolve(store, tmpl.target, period, None)
        opres = [self._resolve(store, r, period, None) for r in ops]

        unknown_ops = [i for i, r in enumerate(opres) if r is None]
        n_unknown = (0 if tgt is not None else 1) + len(unknown_ops)
        if n_unknown != 1:
            return None

        # Case 1: target is the unknown -> evaluate expr forward.
        if tgt is None:
            iv = tmpl.expr.eval(lambda r, _s=store, _p=period:
                                (self._resolve(_s, r, _p, None) or (None,))[0])
            if iv is None:
                return None
            ids = [i for r in opres if r for i in r[1]]
            return Solved(tmpl.target.concept, iv, ids,
                          f"{tmpl.target.concept} = {_expr_str(tmpl.expr)}")

        # Case 2: one operand is the unknown -> invert. (Aggregate unknown can't
        # be split into members.)
        ui = unknown_ops[0]
        if ops[ui].binding is Binding.AGGREGATE:
            return None
        tiv, tids = tgt
        known = {i: r for i, r in enumerate(opres) if r is not None}
        ids = list(tids) + [i for r in known.values() for i in r[1]]

        iv = self._invert(tmpl.expr, ui, tiv, opres)
        if iv is None:
            return None
        return Solved(ops[ui].concept, iv, ids,
                      f"{ops[ui].concept} (from {tmpl.target.concept} = {_expr_str(tmpl.expr)})")

    @staticmethod
    def _invert(expr, ui, tiv, opres):
        if isinstance(expr, Ref):  # target = x  -> x = target
            return tiv
        if isinstance(expr, Add):  # x_i = target - sum(others)
            acc = tiv
            for i, r in enumerate(opres):
                if i != ui:
                    acc = acc - r[0]
            return acc
        if isinstance(expr, Sub):  # target = a - b
            a, b = opres
            return tiv + b[0] if ui == 0 else a[0] - tiv
        if isinstance(expr, Div):  # target = n / d
            n, d = opres
            return _interval_mul(tiv, d[0]) if ui == 0 else _interval_div(n[0], tiv)
        if isinstance(expr, Mul):  # target = a * b
            a, b = opres
            other = b[0] if ui == 0 else a[0]
            return _interval_div(tiv, other)
        return None

    def _propagate(self, store: FactStore, periods) -> list[Fact]:
        derived: list[Fact] = []
        for _ in range(_MAX_PASSES):
            added = 0
            for tmpl in self.templates:
                ptype = get_concept(tmpl.target.concept).period_type
                for period in periods:
                    if period.type is not ptype:
                        continue
                    sol = self._try_solve(tmpl, period, store)
                    if sol is None:
                        continue
                    if store.has(sol.concept, period, dimensions={}):
                        continue  # never overwrite an existing fact
                    is_ratio = get_concept(sol.concept).data_type is DataType.RATIO
                    f = Fact(
                        concept=sol.concept,
                        value=sol.interval.midpoint,
                        period=period,
                        source=Source.DERIVED,
                        provenance=DerivedProv(tmpl.template_id,
                                               tuple(sol.input_fact_ids), sol.op),
                        unit="ratio" if is_ratio else "USD",
                        band=sol.interval.width / 2,
                    )
                    store.add(f)
                    derived.append(f)
                    added += 1
            if added == 0:
                break
        return derived

    def _localize(self, results: list[InstantiatedConstraint]) -> dict:
        # Identifiability note: a fact shared with SATISFIED constraints is
        # vouched-for, so suspicion concentrates on facts that appear (almost)
        # only in failing ones. This reliably separates "the total is wrong" from
        # "a component is wrong", but cannot distinguish sibling members of a
        # single roll-up (they share no other constraint) — that needs an
        # independent signal such as cross-period continuity.
        satisfied_touch: dict[str, int] = {}
        for r in results:
            if r.status is Status.SATISFIED:
                for fid in r.involved_fact_ids:
                    satisfied_touch[fid] = satisfied_touch.get(fid, 0) + 1
        loc: dict[str, list[tuple[str, float]]] = {}
        for r in results:
            if r.status is not Status.VIOLATED:
                continue
            ranked = sorted(
                r.involved_fact_ids,
                key=lambda fid: (satisfied_touch.get(fid, 0), fid),
            )
            # suspicion score: fewer "vouches" from satisfied constraints = higher
            loc[r.inst_id] = [
                (fid, round(1.0 / (1 + satisfied_touch.get(fid, 0)), 3))
                for fid in ranked
            ]
        return loc

    def run(self, store: FactStore, periods) -> list[InstantiatedConstraint]:
        work = FactStore()
        work.add_all(store.all_facts())

        self.derived_facts = self._propagate(work, periods)
        self.store = work

        binder = Binder(work, source=None, ground_truth=self.ground_truth)
        results: list[InstantiatedConstraint] = []
        for tmpl in self.templates:
            ptype = get_concept(tmpl.target.concept).period_type
            for period in periods:
                if period.type is ptype:
                    results.append(binder.bind(tmpl, period))
        self.localizations = self._localize(results)
        return results
