"""XbrlDirectExtractor — the structured ground-truth adapter (Phase 0).

Loads a filing's XBRL through arelle and returns Facts with Source.XBRL. This is
the disambiguator the attribution layer trusts: when a text-extracted figure
disagrees with the same concept here, that's an extraction error rather than a
filing inconsistency.
"""

from __future__ import annotations

from ..facts import Fact
from ..ingest.edgar import DEFAULT_USER_AGENT, FilingLocator
from ..ingest.xbrl import XbrlLoader


class XbrlDirectExtractor:
    name = "xbrl_direct"
    version = "0"

    def __init__(self, loader: XbrlLoader | None = None,
                 user_agent: str = DEFAULT_USER_AGENT) -> None:
        # Lazily construct the loader (and thus arelle) only when first used.
        self._loader = loader
        self._user_agent = user_agent

    def _get_loader(self) -> XbrlLoader:
        if self._loader is None:
            self._loader = XbrlLoader(user_agent=self._user_agent)
        return self._loader

    def extract(self, filing: FilingLocator) -> list[Fact]:
        return self._get_loader().load_facts(filing.url, doc_id=filing.primary_doc)
