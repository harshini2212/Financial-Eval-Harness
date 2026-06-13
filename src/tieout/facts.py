"""The provenanced Fact object and the FactStore (deterministic snapshot).

A Fact is an extracted-or-derived figure plus everything needed to (a) reconcile
it numerically and (b) point a finger when a constraint fails. Provenance is a
discriminated union keyed by `source`; a *derived* fact records which constraint
and which inputs produced it, which is what turns the constraint graph into an
audit trail (and is exactly the citation requirement an autonomous analyst has).

The FactStore is a pure in-memory snapshot. LLM non-determinism is quarantined
upstream (extraction outputs are frozen before they land here), so everything
from here rightward is a pure deterministic function of the store.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from decimal import Decimal
from enum import Enum

from .intervals import ROUNDING_BAND, Interval
from .ontology import PeriodType


class Source(str, Enum):
    XBRL = "xbrl"  # structured ground truth (arelle)
    TEXT = "text"  # LLM extraction from filing prose — the thing under test
    DERIVED = "derived"  # produced by propagation through the constraint graph
    GOLD = "gold"  # human-attested


class Scale(str, Enum):
    ONES = "ones"
    THOUSANDS = "thousands"
    MILLIONS = "millions"


class FiscalPeriod(str, Enum):
    FY = "FY"
    Q1 = "Q1"
    Q2 = "Q2"
    Q3 = "Q3"
    Q4 = "Q4"


@dataclass(frozen=True)
class Period:
    type: PeriodType
    fiscal_year: int
    fiscal_period: FiscalPeriod = FiscalPeriod.FY
    start: str | None = None  # ISO date; duration only
    end: str | None = None  # ISO date; instant uses end only

    def key(self) -> tuple:
        return (self.type.value, self.fiscal_year, self.fiscal_period.value)


# --- Provenance (discriminated by Source) -----------------------------------


@dataclass(frozen=True)
class XbrlProv:
    tag: str
    context_ref: str
    decimals: int | None = None
    linkbase_ref: str | None = None


@dataclass(frozen=True)
class TextProv:
    doc_id: str
    model: str
    prompt_version: str
    snippet: str = ""
    char_span: tuple[int, int] | None = None
    page: int | None = None
    raw_response_ref: str | None = None  # -> response cache, for reproducibility


@dataclass(frozen=True)
class DerivedProv:
    constraint_id: str
    input_fact_ids: tuple[str, ...]
    op: str  # human-readable, e.g. "revenue.total - cogs.total"


@dataclass(frozen=True)
class GoldProv:
    verifier: str
    verified_date: str
    citation: str = ""


Provenance = XbrlProv | TextProv | DerivedProv | GoldProv


@dataclass(frozen=True)
class Fact:
    """A single provenanced figure, normalised to base units (dollars)."""

    concept: str  # canonical concept id
    value: Decimal  # ALWAYS Decimal, in base units
    period: Period
    source: Source
    provenance: Provenance
    unit: str = "USD"
    reported_scale: Scale = Scale.ONES  # original presentation scale (text path)
    decimals: int | None = None  # XBRL rounding precision (e.g. -6 = millions)
    band: Decimal | None = None  # explicit uncertainty half-width (derived facts)
    dimensions: tuple[tuple[str, str], ...] = ()  # sorted; () == consolidated
    confidence: Decimal | None = None  # populated by LLM / factor-graph engine
    extractor_version: str = "0"

    @property
    def fact_id(self) -> str:
        """Content hash — stable across runs, collision-safe across sources."""
        payload = {
            "concept": self.concept,
            "value": str(self.value),
            "period": self.period.key(),
            "dims": list(self.dimensions),
            "source": self.source.value,
            "unit": self.unit,
        }
        blob = json.dumps(payload, sort_keys=True).encode()
        return hashlib.sha256(blob).hexdigest()[:16]

    @property
    def rounding_band(self) -> Decimal:
        """Half-unit ambiguity of the reported figure.

        Prefer XBRL's precise `decimals` (e.g. decimals=-6 -> rounded to the
        nearest million -> a 500,000 half-band). Fall back to the presentation
        `reported_scale` for text-extracted facts that carry no decimals.
        """
        if self.decimals is not None and self.decimals <= 0:
            return Decimal(10) ** (-self.decimals) / 2
        if self.unit != "USD":
            return Decimal(0)  # ratios/shares: no monetary rounding band
        return ROUNDING_BAND[self.reported_scale.value]

    def as_interval(self) -> Interval:
        """The figure as a band around its value.

        Derived facts carry an explicit propagated `band`; reported facts use the
        rounding band implied by their precision.
        """
        half = self.band if self.band is not None else self.rounding_band
        return Interval.exact(self.value).widen(half)

    def dims_dict(self) -> dict[str, str]:
        return dict(self.dimensions)


def make_dims(d: dict[str, str] | None) -> tuple[tuple[str, str], ...]:
    """Canonicalise a dimensions dict into the sorted tuple Facts store."""
    if not d:
        return ()
    return tuple(sorted(d.items()))


class FactStore:
    """In-memory, queryable snapshot of all facts for one or more filings.

    Indexed by (concept, period-key) for the binder's hot path. A `source`
    filter lets the engine ask specifically for ground-truth (xbrl/gold) facts
    when doing violation attribution.
    """

    def __init__(self) -> None:
        self._facts: dict[str, Fact] = {}
        self._by_concept_period: dict[tuple[str, tuple], list[str]] = {}

    def add(self, fact: Fact) -> str:
        fid = fact.fact_id
        if fid not in self._facts:
            self._facts[fid] = fact
            self._by_concept_period.setdefault(
                (fact.concept, fact.period.key()), []
            ).append(fid)
        return fid

    def add_all(self, facts) -> None:
        for f in facts:
            self.add(f)

    def get(self, fact_id: str) -> Fact:
        return self._facts[fact_id]

    def all_facts(self) -> list[Fact]:
        return list(self._facts.values())

    def has(self, concept: str, period: Period,
            dimensions: dict[str, str] | None = None) -> bool:
        return bool(self.query(concept, period, dimensions=dimensions))

    def query(
        self,
        concept: str,
        period: Period,
        *,
        dimensions: dict[str, str] | None = None,
        source: Source | None = None,
    ) -> list[Fact]:
        """Facts matching concept+period, optionally filtered by exact dims/source.

        `dimensions=None`  -> any dimensional binding (used for aggregation).
        `dimensions={}`    -> consolidated only (no dimensions).
        """
        ids = self._by_concept_period.get((concept, period.key()), [])
        out = [self._facts[i] for i in ids]
        if source is not None:
            out = [f for f in out if f.source is source]
        if dimensions is not None:
            want = make_dims(dimensions)
            out = [f for f in out if f.dimensions == want]
        return out

    def __len__(self) -> int:
        return len(self._facts)
