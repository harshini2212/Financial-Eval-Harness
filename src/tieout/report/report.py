"""Scorecards + markdown report (fast/demo version).

Per extractor: agreement with XBRL ground truth, constraint pass/fail counts, and
the attribution breakdown of every violation. The headline metric is the count of
extraction errors the constraint layer caught even though *every individually
extracted figure was correct* — exactly what a value-by-value LLM judge misses.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from decimal import Decimal

from ..attribution import Label, attribute_run
from ..constraints import Severity, Status
from ..engine import CheckerEngine
from ..facts import FactStore, Source


def _band(gt: Decimal) -> Decimal:
    return max(abs(gt) * Decimal("0.002"), Decimal("1000000"))


@dataclass
class Scorecard:
    name: str
    fiscal_year: int
    extracted: int
    agree: int
    disagree: int
    satisfied: int
    violated: int  # hard violations only
    indeterminate: int
    soft_violated: int = 0  # advisory (soft identities)
    attributions: list = field(default_factory=list)
    judge_invisible: int = 0  # caught errors where every present figure was correct


def build_scorecard(name, text_store, gt_store, templates, periods, fy) -> Scorecard:
    # Agreement vs ground truth (consolidated USD facts for the fiscal year).
    agree = disagree = 0
    for f in text_store.all_facts():
        if f.period.fiscal_year != fy or f.dimensions or f.unit != "USD":
            continue
        g = gt_store.query(f.concept, f.period, dimensions={}, source=Source.XBRL)
        if not g:
            continue
        (agree, disagree) = ((agree + 1, disagree) if abs(f.value - g[0].value)
                             <= _band(g[0].value) else (agree, disagree + 1))

    # Score on the model's RAW extractions (no propagation), so the table and the
    # attribution agree on what the model actually got right/wrong.
    results = CheckerEngine(templates).run(text_store, periods)
    fy_res = [r for r in results if r.period.fiscal_year == fy]
    counts = Counter(r.status for r in fy_res)
    hard_viol = sum(1 for r in fy_res if r.status is Status.VIOLATED
                    and r.severity is Severity.HARD)
    soft_viol = sum(1 for r in fy_res if r.status is Status.VIOLATED
                    and r.severity is Severity.SOFT)

    attrs = [a for a in attribute_run(templates, periods, text_store, gt_store)
             if a.period.fiscal_year == fy]
    # judge-invisible: extraction errors where no *consolidated* figure disagrees
    judge_invisible = sum(
        1 for a in attrs
        if a.label is Label.EXTRACTION_ERROR and "[" in a.evidence
        and all(part.strip().startswith(("revenue.segment", "operating_income.segment"))
                or "[" in part for part in a.evidence.split(";"))
    )
    return Scorecard(
        name, fy, len([f for f in text_store.all_facts() if f.period.fiscal_year == fy]),
        agree, disagree,
        counts.get(Status.SATISFIED, 0), hard_viol,
        counts.get(Status.INDETERMINATE, 0), soft_viol, attrs, judge_invisible,
    )


def render_markdown(filing, scorecards: list[Scorecard]) -> str:
    fy = scorecards[0].fiscal_year if scorecards else filing.fiscal_year
    L: list[str] = []
    L.append(f"## {filing.issuer} ({filing.ticker}) - 10-K FY{fy}\n")

    L.append("| Extractor | Facts | Agree | Disagree | sat | viol(hard) | soft | indet |")
    L.append("|---|--:|--:|--:|--:|--:|--:|--:|")
    for s in scorecards:
        L.append(f"| {s.name} | {s.extracted} | {s.agree} | {s.disagree} "
                 f"| {s.satisfied} | {s.violated} | {s.soft_violated} | {s.indeterminate} |")
    L.append("")

    for s in scorecards:
        if not s.attributions:
            continue
        by = Counter(a.label.value for a in s.attributions)
        L.append(f"**{s.name}** attribution - "
                 + ", ".join(f"{k}: {v}" for k, v in by.items()))
        for a in s.attributions:
            L.append(f"- `{a.template_id}` -> **{a.label.value}** - {a.evidence}")
        L.append("")

    # One-line takeaway per filing.
    claude = next((s for s in scorecards if "Claude" in s.name), None)
    if claude:
        if claude.violated == 0 and claude.disagree == 0:
            L.append(f"*Verified: Claude's {claude.agree} extracted figures all "
                     "reconcile against ground truth - zero false positives.*")
        elif claude.judge_invisible:
            L.append(f"*Caught: {claude.judge_invisible} extraction error(s) the "
                     "constraint layer flagged despite each figure looking correct.*")
    return "\n".join(L)
