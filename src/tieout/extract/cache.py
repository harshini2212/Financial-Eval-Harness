"""Content-addressed response cache — the reproducibility backbone.

The key is a SHA-256 of the *fully-rendered request*, so a cache hit can only
occur for an input the model actually received: change the chunking, prompt
template, decoding params, or model and the key changes, forcing a re-fetch.
With a populated cache the entire eval is free and bit-identical on re-run.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from pathlib import Path


@dataclass(frozen=True)
class DecodingParams:
    temperature: float = 0.0
    top_p: float = 1.0
    max_tokens: int = 8192  # a full-statements extraction emits many facts
    seed: int = 0


def request_key(*, model_id: str, params: DecodingParams, prompt_version: str,
                adapter_version: str, rendered_prompt: str) -> str:
    payload = {
        "model_id": model_id,
        "params": asdict(params),
        "prompt_version": prompt_version,
        "adapter_version": adapter_version,
        "rendered_prompt": rendered_prompt,
    }
    blob = json.dumps(payload, sort_keys=True, ensure_ascii=False).encode("utf-8")
    return hashlib.sha256(blob).hexdigest()


class ResponseCache:
    def __init__(self, root: str | Path = ".cache/llm") -> None:
        self.root = Path(root)

    def _path(self, key: str) -> Path:
        return self.root / key[:2] / f"{key}.json"

    def get(self, key: str) -> dict | None:
        p = self._path(key)
        if p.exists():
            return json.loads(p.read_text(encoding="utf-8"))
        return None

    def put(self, key: str, record: dict) -> None:
        p = self._path(key)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(record, ensure_ascii=False, indent=2),
                     encoding="utf-8")
