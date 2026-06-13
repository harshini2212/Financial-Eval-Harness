"""Phase 3 offline plumbing: text-extraction pipeline + cache, zero spend.

Uses EchoModel (canned JSON) so the full path runs without any API:
  canned LLM response -> LlmTextExtractor -> Facts -> constraint engine.
Also verifies the response cache makes a re-call free.
"""

from __future__ import annotations

import json
import tempfile
from decimal import Decimal

from tieout.constraints import Status
from tieout.engine import CheckerEngine
from tieout.extract import DecodingParams, EchoModel, LlmTextExtractor, ResponseCache
from tieout.extract.cache import request_key
from tieout.extract.llm import CachedModel
from tieout.facts import FactStore, Source
from tieout.ingest.xbrl import periods_in
from tieout.registry import REGISTRY

# A model that "extracts" revenue and cogs correctly but gross profit WRONG.
_CANNED = json.dumps([
    {"concept": "revenue.total", "value": 275235, "scale": "millions",
     "fiscal_year": 2025, "period_type": "duration", "snippet": "Total revenue"},
    {"concept": "cogs.total", "value": 239886, "scale": "millions",
     "fiscal_year": 2025, "period_type": "duration", "snippet": "Merchandise costs"},
    {"concept": "gross_profit.total", "value": 99999, "scale": "millions",
     "fiscal_year": 2025, "period_type": "duration", "snippet": "(hallucinated)"},
])


def _extractor():
    cache = ResponseCache(tempfile.mkdtemp())
    return LlmTextExtractor(EchoModel(_CANNED), cache,
                            text_provider=lambda _f: "FILING TEXT")


def test_text_pipeline_parses_and_flags_bad_figure():
    facts = _extractor().extract(filing=None)
    by = {f.concept: f for f in facts}
    assert by["revenue.total"].value == Decimal("275235000000")
    assert by["revenue.total"].source is Source.TEXT
    # provenance points back at the cached raw response (reproducibility)
    assert by["revenue.total"].provenance.raw_response_ref

    store = FactStore()
    store.add_all(facts)
    results = CheckerEngine(REGISTRY).run(store, periods_in(facts))
    gp = next(r for r in results if r.template_id == "is.gross_profit")
    # gross profit 99,999M vs revenue-cogs = 35,349M -> caught
    assert gp.status is Status.VIOLATED


def test_cache_makes_recall_free():
    calls = {"n": 0}

    class Counting:
        model_id = "counting"

        def complete(self, prompt, params):
            calls["n"] += 1
            return _CANNED

    cache = ResponseCache(tempfile.mkdtemp())
    cm = CachedModel(Counting(), cache, prompt_version="v1",
                     adapter_version="t/0", params=DecodingParams())
    r1, k1, hit1 = cm.complete("same prompt")
    r2, k2, hit2 = cm.complete("same prompt")
    assert calls["n"] == 1  # model invoked once
    assert (hit1, hit2) == (False, True)
    assert k1 == k2

    # changing the prompt changes the key -> a miss
    _, k3, hit3 = cm.complete("different prompt")
    assert k3 != k1 and hit3 is False
