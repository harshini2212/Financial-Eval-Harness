"""Extraction adapters behind one interface.

Every adapter turns a located filing into a list of provenanced Facts:
  * XbrlDirectExtractor — structured ground truth (arelle).         [Phase 0]
  * LlmTextExtractor     — figures pulled from prose (under test).  [Phase 3]
  * BaselineExtractor    — regex/heuristic (discrimination floor).  [Phase 3]

A common interface lets the eval runner pit them against identical constraints.
The LLM path is provider-agnostic (Claude/Gemini) and cached for reproducibility.
"""

from .base import Extractor
from .baseline import BaselineExtractor
from .cache import DecodingParams, ResponseCache, request_key
from .llm import CachedModel, ChatModel, EchoModel, claude_model, gemini_model
from .llm_text import LlmTextExtractor
from .xbrl_direct import XbrlDirectExtractor

__all__ = [
    "Extractor",
    "XbrlDirectExtractor",
    "LlmTextExtractor",
    "BaselineExtractor",
    "ResponseCache",
    "DecodingParams",
    "request_key",
    "ChatModel",
    "EchoModel",
    "CachedModel",
    "claude_model",
    "gemini_model",
]
