"""Real provider adapters (Claude, Gemini). Constructed lazily; need API keys.

Kept out of the import path of the offline scaffolding so Phase 3 plumbing tests
run with zero spend. Decoding is pinned to temperature/seed for reproducibility.
"""

from __future__ import annotations

from .cache import DecodingParams


class ClaudeModel:
    def __init__(self, model_id: str = "claude-opus-4-8") -> None:
        self.model_id = model_id
        self._client = None

    def _get_client(self):
        # Construct lazily so a fully-cached run needs no API key at all.
        if self._client is None:
            from anthropic import Anthropic  # reads ANTHROPIC_API_KEY
            self._client = Anthropic()
        return self._client

    def complete(self, rendered_prompt: str, params: DecodingParams) -> str:
        # Opus 4.8 deprecates `temperature`; omit it (the model is low-variance,
        # and responses are cached for reproducibility regardless).
        msg = self._get_client().messages.create(
            model=self.model_id,
            max_tokens=params.max_tokens,
            messages=[{"role": "user", "content": rendered_prompt}],
        )
        return "".join(b.text for b in msg.content if getattr(b, "type", "") == "text")


class GeminiModel:
    def __init__(self, model_id: str = "gemini-2.5-pro") -> None:
        from google import genai  # lazy; reads GEMINI_API_KEY / GOOGLE_API_KEY

        self.model_id = model_id
        self._client = genai.Client()

    def complete(self, rendered_prompt: str, params: DecodingParams) -> str:
        resp = self._client.models.generate_content(
            model=self.model_id,
            contents=rendered_prompt,
            config={"temperature": params.temperature,
                    "max_output_tokens": params.max_tokens},
        )
        return resp.text or ""
