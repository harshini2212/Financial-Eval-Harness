"""BaselineExtractor — the deliberately-dumb floor (Phase 3).

Regex/heuristic extraction of a few consolidated line items by their text
aliases. It exists to prove the harness *discriminates*: a real model should
clear this floor by a wide margin on the constraint layer. No API, no cost.
"""

from __future__ import annotations

import re
from decimal import Decimal
from typing import Callable

from ..facts import Fact, FiscalPeriod, Period, Scale, Source, TextProv, make_dims
from ..ontology import ONTOLOGY, DataType, PeriodType

_SCALE_FACTOR = {"ones": Decimal(1), "thousands": Decimal(1000),
                 "millions": Decimal(1_000_000)}
_NUM = r"\$?\s*\(?([0-9][0-9,]*(?:\.[0-9]+)?)\)?"


def _detect_scale(text: str) -> str:
    head = text[:5000].lower()
    if "in millions" in head:
        return "millions"
    if "in thousands" in head:
        return "thousands"
    return "ones"


class BaselineExtractor:
    name = "baseline"
    version = "baseline/0"

    def __init__(self, text_provider: Callable[[object], str]) -> None:
        self.text_provider = text_provider

    def extract(self, filing) -> list[Fact]:
        text = self.text_provider(filing)
        scale = _detect_scale(text)
        factor = _SCALE_FACTOR[scale]
        fy = getattr(filing, "fiscal_year", 0)
        facts: list[Fact] = []
        for concept in ONTOLOGY.values():
            if concept.data_type is DataType.RATIO or not concept.aliases:
                continue
            value = self._first_match(text, concept.aliases)
            if value is None:
                continue
            ptype = concept.period_type
            facts.append(Fact(
                concept=concept.id,
                value=value * factor,
                period=Period(ptype, fy, FiscalPeriod.FY),
                source=Source.TEXT,
                provenance=TextProv(doc_id="baseline", model="baseline-regex",
                                    prompt_version=self.version),
                reported_scale=Scale(scale),
                dimensions=make_dims({}),
                extractor_version=self.version,
            ))
        return facts

    @staticmethod
    def _first_match(text: str, aliases: tuple[str, ...]) -> Decimal | None:
        for alias in aliases:
            m = re.search(re.escape(alias) + r"[^0-9\n]{0,40}?" + _NUM,
                          text, re.IGNORECASE)
            if m:
                try:
                    return Decimal(m.group(1).replace(",", ""))
                except Exception:
                    continue
        return None
