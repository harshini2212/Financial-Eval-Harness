"""Verify a FelixAgent answer: do its cited numbers match the official XBRL data,
and does its stated value follow from those numbers? This is the deterministic
trust layer applied to a generated answer (no LLM judge involved).
"""

from __future__ import annotations

from dataclasses import dataclass, field

from ..facts import FactStore, FiscalPeriod, Period, Source
from ..ontology import ONTOLOGY, concept as get_concept


@dataclass
class NumberCheck:
    label: str
    concept: str | None
    fiscal_year: int | None
    stated: float | None
    truth: float | None
    ok: bool | None      # True/False, or None when not verifiable (e.g. ratios)
    note: str = ""


@dataclass
class Verdict:
    retrieval_ok: bool
    calculation_ok: bool | None
    trusted: bool
    checks: list = field(default_factory=list)
    notes: list = field(default_factory=list)


def _money_match(a: float, b: float) -> bool:
    return abs(a - b) <= max(abs(b) * 0.01, 1_000_000)


def _ratio_match(a: float, b: float) -> bool:
    return abs(a - b) <= 0.005


def _truth_value(store: FactStore, concept: str, fy: int) -> float | None:
    if concept not in ONTOLOGY:
        return None
    c = get_concept(concept)
    facts = store.query(concept, Period(c.period_type, int(fy), FiscalPeriod.FY),
                        dimensions={}, source=Source.XBRL)
    return float(facts[0].value) if facts else None


def _calc_consistent(value: float, nums: list[float]) -> bool | None:
    """Could the stated value follow from the cited numbers via a basic op?"""
    if value is None or len(nums) < 2:
        return None
    cands = [value] + ([value / 100] if abs(value) > 1.5 else [])  # decimal or percent
    for v in cands:
        for i in range(len(nums)):
            for j in range(len(nums)):
                if i == j:
                    continue
                a, b = nums[i], nums[j]
                if abs(v) < 1.5:  # a ratio: margin a/b, or growth (a-b)/b
                    if b and (_ratio_match(v, a / b)
                              or (a and _ratio_match(v, (a - b) / a))
                              or _ratio_match(v, (a - b) / b)):
                        return True
                elif _money_match(v, a - b) or _money_match(v, a + b):
                    return True
    return False


def verify_answer(answer, store: FactStore) -> Verdict:
    checks, notes = [], []
    for n in answer.numbers_used:
        concept = n.get("concept")
        fy = n.get("fiscal_year", answer.fiscal_year)
        stated = n.get("value")
        stated = float(stated) if isinstance(stated, (int, float)) else None
        truth = _truth_value(store, concept, fy) if concept else None
        if not concept:
            ok, note = None, "no source concept cited"
        elif truth is None:
            ok, note = None, "not in official data (derived/untagged)"
        elif stated is None:
            ok, note = False, "no value stated"
        else:
            ok = _money_match(stated, truth)
            note = "" if ok else f"stated {stated:,.0f} vs official {truth:,.0f}"
        checks.append(NumberCheck(str(n.get("label", "")), concept, fy, stated, truth, ok, note))

    graded = [c for c in checks if c.ok is not None]
    retrieval_ok = bool(graded) and all(c.ok for c in graded)
    if not graded:
        notes.append("No cited number could be matched to official data.")

    nums = [c.stated for c in checks if isinstance(c.stated, (int, float))]
    calc_ok = _calc_consistent(answer.value, nums)

    trusted = retrieval_ok and (calc_ok is not False)
    return Verdict(retrieval_ok, calc_ok, trusted, checks, notes)
