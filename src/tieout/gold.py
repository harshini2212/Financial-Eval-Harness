"""Gold-set schema and loader.

The gold set is the credibility line: every answer must be hand-verified against
the source filing before it counts. The loader therefore treats `verified` as
False until a human marks it True, and `verified_strict()` refuses to hand back
unverified questions — so an eval can never silently score against unconfirmed
answers.

Draft questions (machine-proposed, awaiting human verification) carry
`draft_confidence` so the reviewer can triage the least-certain ones first.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from decimal import Decimal
from enum import Enum
from pathlib import Path

from .facts import FiscalPeriod


class AnswerType(str, Enum):
    SCALAR = "scalar"  # a single reported line item
    DERIVED = "derived"  # computed via an identity (margin, growth, etc.)
    ENUMERATION = "enumeration"  # a set (e.g. list of segment revenues)


class Category(str, Enum):
    EXTRACTION = "extraction"
    SINGLE_IDENTITY = "single_identity"
    MULTI_STEP = "multi_step"


class Difficulty(str, Enum):
    EASY = "easy"
    MEDIUM = "medium"
    HARD = "hard"


@dataclass(frozen=True)
class FilingRef:
    cik: str
    accession: str
    fiscal_year: int
    issuer: str = ""


@dataclass(frozen=True)
class GoldAnswer:
    value: Decimal
    unit: str
    fiscal_year: int
    fiscal_period: FiscalPeriod = FiscalPeriod.FY
    dimensions: tuple[tuple[str, str], ...] = ()


@dataclass
class GoldQuestion:
    question_id: str
    filing_ref: FilingRef
    prompt: str
    answer_type: AnswerType
    category: Category
    difficulty: Difficulty
    gold_answer: GoldAnswer
    derivation_template_id: str | None = None  # which identity computes it
    input_concepts: tuple[str, ...] = ()
    citation: str = ""  # page/section + snippet in the filing
    # --- verification gate ---
    verified: bool = False
    verified_by: str = ""
    verified_date: str = ""
    draft_confidence: str = ""  # "high" | "medium" | "low" — triage hint


def _question_from_dict(d: dict) -> GoldQuestion:
    fr = d["filing_ref"]
    ga = d["gold_answer"]
    return GoldQuestion(
        question_id=d["question_id"],
        filing_ref=FilingRef(**fr),
        prompt=d["prompt"],
        answer_type=AnswerType(d["answer_type"]),
        category=Category(d["category"]),
        difficulty=Difficulty(d["difficulty"]),
        gold_answer=GoldAnswer(
            value=Decimal(str(ga["value"])),
            unit=ga["unit"],
            fiscal_year=ga["fiscal_year"],
            fiscal_period=FiscalPeriod(ga.get("fiscal_period", "FY")),
            dimensions=tuple(tuple(p) for p in ga.get("dimensions", [])),
        ),
        derivation_template_id=d.get("derivation_template_id"),
        input_concepts=tuple(d.get("input_concepts", [])),
        citation=d.get("citation", ""),
        verified=bool(d.get("verified", False)),
        verified_by=d.get("verified_by", ""),
        verified_date=d.get("verified_date", ""),
        draft_confidence=d.get("draft_confidence", ""),
    )


class GoldSet:
    def __init__(self, questions: list[GoldQuestion]) -> None:
        self.questions = questions

    @classmethod
    def load(cls, path: str | Path) -> "GoldSet":
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        return cls([_question_from_dict(d) for d in data["questions"]])

    def verified_strict(self) -> list[GoldQuestion]:
        """Only human-verified questions — what an eval is allowed to score on."""
        return [q for q in self.questions if q.verified]

    def unverified(self) -> list[GoldQuestion]:
        return [q for q in self.questions if not q.verified]

    def triage_order(self) -> list[GoldQuestion]:
        """Unverified questions, least-confident first (verify these first)."""
        rank = {"low": 0, "medium": 1, "high": 2, "": 1}
        return sorted(self.unverified(), key=lambda q: rank.get(q.draft_confidence, 1))
