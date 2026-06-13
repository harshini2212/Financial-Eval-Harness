"""tieout — accounting-identity constraint graph for financial-QA correctness.

The package is layered so each module depends only on those to its left in the
spine:  ingest -> ontology -> facts -> extract -> constraints -> engine -> ...

Phase 0 ships the deterministic core (facts, ontology, intervals, constraints,
checker, gold) plus a fixture-driven end-to-end green check. No network, no LLMs,
no XBRL yet — those layer in at Phase 0-tail (arelle) and Phase 3 (adapters).
"""

__version__ = "0.0.0"
