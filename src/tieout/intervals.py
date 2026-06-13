"""Tolerance and rounding-aware interval arithmetic.

Filings round to thousands/millions, so "segments sum to total" almost never
holds to the dollar. Every reconciliation therefore happens over *intervals*,
never `==`. This module is a leaf (no intra-package deps) so both `constraints`
and `engine` can use it without import cycles.

Two ideas:
  * Interval  — a closed band [lo, hi] in base units (dollars), with exact
                Decimal arithmetic. Sums of rounded inputs widen predictably.
  * Tolerance — the policy that turns an expected value into an acceptance band:
                effective band = max(abs, rel * |expected|, rounding band).
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal


@dataclass(frozen=True)
class Interval:
    """A closed band [lo, hi] in base units. lo <= hi always holds."""

    lo: Decimal
    hi: Decimal

    def __post_init__(self) -> None:
        if self.lo > self.hi:
            # normalise rather than raise: callers build these from arithmetic
            object.__setattr__(self, "lo", min(self.lo, self.hi))
            object.__setattr__(self, "hi", max(self.lo, self.hi))

    @classmethod
    def exact(cls, value: Decimal) -> "Interval":
        return cls(value, value)

    @property
    def midpoint(self) -> Decimal:
        return (self.lo + self.hi) / 2

    @property
    def width(self) -> Decimal:
        return self.hi - self.lo

    def __add__(self, other: "Interval") -> "Interval":
        return Interval(self.lo + other.lo, self.hi + other.hi)

    def __sub__(self, other: "Interval") -> "Interval":
        return Interval(self.lo - other.hi, self.hi - other.lo)

    def scale(self, k: Decimal) -> "Interval":
        a, b = self.lo * k, self.hi * k
        return Interval(min(a, b), max(a, b))

    def widen(self, band: Decimal) -> "Interval":
        """Grow the interval symmetrically by `band` on each side."""
        return Interval(self.lo - band, self.hi + band)

    def contains(self, value: Decimal) -> bool:
        return self.lo <= value <= self.hi

    def overlaps(self, other: "Interval") -> bool:
        return self.lo <= other.hi and other.lo <= self.hi


# Rounding bands by reported scale: a figure presented in thousands carries a
# half-unit of ambiguity = 500 base-unit dollars on each side, etc.
ROUNDING_BAND: dict[str, Decimal] = {
    "ones": Decimal("0.5"),
    "thousands": Decimal("500"),
    "millions": Decimal("500000"),
}


@dataclass(frozen=True)
class Tolerance:
    """Acceptance policy for a constraint.

    Tolerance is *source-aware*: ground-truth XBRL figures are exact to their
    `decimals`, so the band is just abs + rounding (rel_ground_truth defaults to
    0). Text-extracted figures get the looser `rel`, since prose rounds ("$77.1
    billion") and a relative band is the only fair way to accept that.
    """

    abs: Decimal = Decimal("1")  # absolute dollar band
    rel: Decimal = Decimal("0.005")  # relative band for text-extracted figures
    rel_ground_truth: Decimal = Decimal("0")  # relative band for xbrl/gold
    rounding_aware: bool = True  # fold in rounding ambiguity of the inputs

    def band(self, expected: Decimal, rounding: Decimal = Decimal("0"),
             *, ground_truth: bool = False) -> Decimal:
        """Effective half-width of the acceptance band around `expected`."""
        rel = self.rel_ground_truth if ground_truth else self.rel
        candidates = [self.abs, rel * abs(expected)]
        if self.rounding_aware:
            candidates.append(rounding)
        return max(candidates)
