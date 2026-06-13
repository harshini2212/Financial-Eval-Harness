"""Reporting: per-extractor scorecards, attribution breakdown, discrimination."""

from .report import Scorecard, build_scorecard, render_markdown

__all__ = ["Scorecard", "build_scorecard", "render_markdown"]
