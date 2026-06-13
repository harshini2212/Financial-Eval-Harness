"""Fetch and reduce a filing's HTML to text for the text-extraction adapters.

The exact text handed to a model is part of the cache key, so the chunking is
deterministic. v1 is intentionally simple: strip HTML, then window around the
financial-statements section to keep the prompt focused (and cheap).
"""

from __future__ import annotations

from html.parser import HTMLParser

from .edgar import EdgarClient

_SKIP_TAGS = {"script", "style", "head"}
_ANCHORS = ("CONSOLIDATED STATEMENTS OF OPERATIONS",
            "CONSOLIDATED STATEMENTS OF INCOME",
            "CONSOLIDATED STATEMENT OF EARNINGS",
            "CONSOLIDATED BALANCE SHEET", "CONSOLIDATED STATEMENTS OF",
            "CONSOLIDATED STATEMENT OF")

# Default window: large enough to span income statement -> balance sheet -> cash
# flows -> early notes, which can be 150k+ chars apart in a big 10-K.
DEFAULT_WINDOW = 170_000


class _TextExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self._parts: list[str] = []
        self._skip = 0

    def handle_starttag(self, tag, attrs):
        if tag in _SKIP_TAGS:
            self._skip += 1

    def handle_endtag(self, tag):
        if tag in _SKIP_TAGS and self._skip:
            self._skip -= 1

    def handle_data(self, data):
        if not self._skip and data.strip():
            self._parts.append(data.strip())

    def text(self) -> str:
        return " ".join(self._parts)


def html_to_text(html: str) -> str:
    p = _TextExtractor()
    p.feed(html)
    return " ".join(p.text().split())


def financial_window(text: str, *, before: int = 3000,
                     size: int = DEFAULT_WINDOW) -> str:
    """Window the text around the actual financial statements.

    A 10-K names the statements first in its table of contents, so the *first*
    anchor match is usually the TOC. We skip anchors in the first 20% of the
    document and take the earliest real-statements anchor after that.
    """
    upper = text.upper()
    n = len(text)
    positions = sorted(
        i for a in _ANCHORS
        for i in _all_occurrences(upper, a)
    )
    if not positions:
        return text[:size]
    later = [p for p in positions if p >= 0.2 * n]
    pos = later[0] if later else positions[0]
    start = max(0, pos - before)
    return text[start:start + size]


def _all_occurrences(haystack: str, needle: str) -> list[int]:
    out, i = [], haystack.find(needle)
    while i != -1:
        out.append(i)
        i = haystack.find(needle, i + 1)
    return out


def edgar_text_provider(client: EdgarClient | None = None, *,
                        size: int = DEFAULT_WINDOW):
    """Build a TextProvider(filing -> text) that fetches + windows the filing."""
    client = client or EdgarClient()

    def provider(filing) -> str:
        html = client._get(filing.url).decode("utf-8", errors="ignore")
        return financial_window(html_to_text(html), size=size)

    return provider
