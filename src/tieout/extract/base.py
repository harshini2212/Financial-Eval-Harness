"""The Extractor interface all adapters implement."""

from __future__ import annotations

from typing import Protocol

from ..facts import Fact
from ..ingest.edgar import FilingLocator


class Extractor(Protocol):
    """Turns a located filing into provenanced facts.

    `name` and `version` are recorded into provenance / cache keys so runs are
    attributable and reproducible.
    """

    name: str
    version: str

    def extract(self, filing: FilingLocator) -> list[Fact]:
        ...
