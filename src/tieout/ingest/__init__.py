"""Ingestion: locate filings on EDGAR and load their XBRL as ground-truth facts."""

from .edgar import EdgarClient, FilingLocator

__all__ = ["EdgarClient", "FilingLocator"]
