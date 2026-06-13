"""Provider-agnostic chat-model interface + the cached wrapper.

Real providers (Claude, Gemini) are constructed lazily and need API keys; the
EchoModel lets the whole text-extraction pipeline be exercised offline with a
canned response, so Phase 3 plumbing is testable with zero spend.
"""

from __future__ import annotations

from typing import Protocol

from .cache import DecodingParams, ResponseCache, request_key


class ChatModel(Protocol):
    model_id: str

    def complete(self, rendered_prompt: str, params: DecodingParams) -> str:
        ...


class EchoModel:
    """Offline stand-in: returns a fixed canned response. For pipeline tests."""

    def __init__(self, canned: str, model_id: str = "echo") -> None:
        self.model_id = model_id
        self._canned = canned

    def complete(self, rendered_prompt: str, params: DecodingParams) -> str:
        return self._canned


class CachedModel:
    """Wraps a ChatModel with the content-addressed cache + provenance keys."""

    def __init__(self, model: ChatModel, cache: ResponseCache, *,
                 prompt_version: str, adapter_version: str,
                 params: DecodingParams | None = None) -> None:
        self.model = model
        self.cache = cache
        self.prompt_version = prompt_version
        self.adapter_version = adapter_version
        self.params = params or DecodingParams()

    def complete(self, rendered_prompt: str) -> tuple[str, str, bool]:
        """Return (response_text, cache_key, was_hit)."""
        key = request_key(
            model_id=self.model.model_id, params=self.params,
            prompt_version=self.prompt_version,
            adapter_version=self.adapter_version, rendered_prompt=rendered_prompt,
        )
        rec = self.cache.get(key)
        if rec is not None:
            return rec["response"], key, True
        text = self.model.complete(rendered_prompt, self.params)
        self.cache.put(key, {
            "model_id": self.model.model_id,
            "prompt_version": self.prompt_version,
            "adapter_version": self.adapter_version,
            "params": self.params.__dict__,
            "response": text,
        })
        return text, key, False


def claude_model(model_id: str = "claude-opus-4-8"):
    """Construct a Claude-backed ChatModel (lazy import; needs ANTHROPIC_API_KEY)."""
    from .providers import ClaudeModel  # lazy

    return ClaudeModel(model_id)


def gemini_model(model_id: str = "gemini-2.5-pro"):
    """Construct a Gemini-backed ChatModel (lazy import; needs GEMINI_API_KEY)."""
    from .providers import GeminiModel  # lazy

    return GeminiModel(model_id)
