"""LlmTextExtractor — the adapter under test (Phase 3).

Renders the extraction prompt over the filing text, calls a (cached) ChatModel,
and parses the JSON into provenanced Facts with Source.TEXT. Each fact's
provenance points back at the cached raw response, so a run is fully attributable
and reproducible.
"""

from __future__ import annotations

import json
from decimal import Decimal, InvalidOperation
from typing import Callable

from ..facts import Fact, FiscalPeriod, Period, Scale, Source, TextProv, make_dims
from ..ontology import ONTOLOGY, PeriodType
from .cache import DecodingParams, ResponseCache
from .llm import CachedModel, ChatModel
from .prompt import PROMPT_VERSION, render_extraction_prompt

_SCALE_FACTOR = {"ones": Decimal(1), "thousands": Decimal(1000),
                 "millions": Decimal(1_000_000)}

# Text-provider signature: FilingLocator -> filing text (fetch + chunk).
TextProvider = Callable[[object], str]


class LlmTextExtractor:
    name = "llm_text"

    def __init__(self, model: ChatModel, cache: ResponseCache, *,
                 text_provider: TextProvider,
                 prompt_version: str = PROMPT_VERSION,
                 params: DecodingParams | None = None) -> None:
        self.model = model
        self.cache = cache
        self.text_provider = text_provider
        self.prompt_version = prompt_version
        self.params = params or DecodingParams()

    @property
    def version(self) -> str:
        return f"{self.prompt_version}/{self.model.model_id}"

    def extract(self, filing) -> list[Fact]:
        text = self.text_provider(filing)
        prompt = render_extraction_prompt(text)
        cached = CachedModel(self.model, self.cache,
                             prompt_version=self.prompt_version,
                             adapter_version=f"llm_text/{self.model.model_id}",
                             params=self.params)
        response, key, _hit = cached.complete(prompt)
        return self._parse(response, key)

    def _parse(self, response: str, raw_ref: str) -> list[Fact]:
        items = _safe_json_array(_extract_json(response))
        facts: list[Fact] = []
        for it in items:
            f = self._to_fact(it, raw_ref)
            if f is not None:
                facts.append(f)
        return facts

    def _to_fact(self, it: dict, raw_ref: str) -> Fact | None:
        concept = it.get("concept")
        if concept not in ONTOLOGY:
            return None  # ignore hallucinated concept ids
        try:
            raw = Decimal(str(it["value"]))
        except (InvalidOperation, KeyError, TypeError):
            return None
        scale = str(it.get("scale", "ones"))
        value = raw * _SCALE_FACTOR.get(scale, Decimal(1))
        ptype = (PeriodType.INSTANT if it.get("period_type") == "instant"
                 else PeriodType.DURATION)
        period = Period(ptype, int(it["fiscal_year"]),
                        FiscalPeriod(it.get("fiscal_period", "FY")))
        unit = "ratio" if ONTOLOGY[concept].data_type.value == "ratio" else "USD"
        return Fact(
            concept=concept,
            value=value,
            period=period,
            source=Source.TEXT,
            provenance=TextProv(doc_id=raw_ref[:12], model=self.model.model_id,
                                prompt_version=self.prompt_version,
                                snippet=str(it.get("snippet", ""))[:160],
                                raw_response_ref=raw_ref),
            unit=unit,
            reported_scale=Scale(scale) if scale in _SCALE_FACTOR else Scale.ONES,
            dimensions=make_dims(it.get("dimensions") or {}),
            extractor_version=self.version,
        )


def _safe_json_array(s: str) -> list:
    """Parse a JSON array, salvaging a response truncated mid-array."""
    try:
        return json.loads(s)
    except json.JSONDecodeError:
        cut = s.rfind("}")
        if cut != -1:
            try:
                return json.loads(s[:cut + 1] + "]")
            except json.JSONDecodeError:
                return []
        return []


def _extract_json(text: str) -> str:
    """Pull the JSON array out of a response that may have prose and/or fences."""
    t = text.strip()
    if "```" in t:
        after = t[t.find("```") + 3:]
        nl = after.find("\n")
        lang = after[:nl].strip().lower() if nl != -1 else ""
        body = after[nl + 1:] if lang in ("json", "") else after
        end = body.find("```")
        if end != -1:
            return body[:end].strip()
    i, j = t.find("["), t.rfind("]")
    if i != -1 and j > i:
        return t[i:j + 1]
    return t
