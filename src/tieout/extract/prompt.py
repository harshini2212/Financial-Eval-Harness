"""Extraction prompt templating (versioned).

The prompt is part of the cache key, so its version is explicit. We hand the
model the canonical concept catalogue and require a strict JSON schema back, so
extracted figures land on the same concept ids the constraint graph reasons over.
"""

from __future__ import annotations

from ..ontology import ONTOLOGY, DataType

PROMPT_VERSION = "extract-v1"

# Concepts we ask the model to extract (skip the purely-derived ratios — those
# are the graph's job to recompute and check against any the model volunteers).
_EXTRACT_CONCEPTS = [c for c in ONTOLOGY.values()
                     if c.data_type is not DataType.RATIO]


def _catalogue() -> str:
    lines = []
    for c in _EXTRACT_CONCEPTS:
        dim = " (per-segment; include dimensions)" if c.dimensional else ""
        lines.append(f"- {c.id}: {c.label} [{c.period_type.value}]{dim}")
    return "\n".join(lines)


_TEMPLATE = """You are extracting reported financial figures from a SEC 10-K filing.
Return ONLY a JSON array. Each element:
  {{"concept": <one id from the catalogue>, "value": <number in the unit reported>,
    "scale": "ones"|"thousands"|"millions",
    "fiscal_year": <int>, "fiscal_period": "FY",
    "period_type": "instant"|"duration",
    "dimensions": {{"segment": "<name>"}} or {{}},
    "snippet": "<short source text>"}}

Rules:
- Use ONLY these concept ids:
{catalogue}
- Report each value exactly as printed, with its scale; do not convert.
- Omit a concept entirely if the filing does not report it. Do not guess.
- For segment figures, emit one element per segment with its dimensions.

FILING TEXT:
{filing_text}
"""


def render_extraction_prompt(filing_text: str) -> str:
    return _TEMPLATE.format(catalogue=_catalogue(), filing_text=filing_text)
