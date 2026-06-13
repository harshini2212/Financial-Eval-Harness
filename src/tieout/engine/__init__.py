"""Constraint-engine backends behind one interface.

Phase 0/1:  CheckerEngine   — boolean evaluation of instantiated constraints (A).
Phase 2:    PropagatingEngine — graph propagation + localization (B, headline).
Stretch:    FactorGraphEngine — probabilistic consistency (C, one-case demo).

All backends consume a FactStore + templates and emit a list of
InstantiatedConstraint results, so they are swappable in the eval runner.
"""

from .checker import CheckerEngine
from .propagating import PropagatingEngine

__all__ = ["CheckerEngine", "PropagatingEngine"]
