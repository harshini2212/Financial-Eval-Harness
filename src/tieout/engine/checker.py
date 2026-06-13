"""CheckerEngine — the Phase 0/1 (A) backend.

Evaluates every template against every period for which any of its concepts has
facts, and returns the instantiated results. No propagation, no localization —
that is Phase 2's PropagatingEngine, which will subclass this contract.
"""

from __future__ import annotations

from ..constraints import Binder, ConstraintTemplate, InstantiatedConstraint
from ..facts import FactStore, Period, Source
from ..ontology import concept as get_concept


class CheckerEngine:
    name = "checker"

    def __init__(self, templates, *, source: Source | None = None) -> None:
        self.templates: tuple[ConstraintTemplate, ...] = tuple(templates)
        self.source = source

    def run(self, store: FactStore, periods) -> list[InstantiatedConstraint]:
        binder = Binder(store, source=self.source)
        results: list[InstantiatedConstraint] = []
        for tmpl in self.templates:
            # Only evaluate a template for periods matching its concept's period
            # type — a balance-sheet identity has nothing to say about a duration
            # period, and vice versa. This keeps INDETERMINATE meaningful (a
            # genuinely missing input) rather than period-type noise.
            ptype = get_concept(tmpl.target.concept).period_type
            for period in periods:
                if period.type is not ptype:
                    continue
                results.append(binder.bind(tmpl, period))
        return results
