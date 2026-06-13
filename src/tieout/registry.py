"""Hand-authored constraint registry (Phase 1).

~16 universal accounting identities spanning the balance sheet, income statement,
segment roll-ups, and derived ratios. Each is a structured template the engine
binds per filing/period. The XBRL calculation-linkbase harvester (stretch) will
later layer filing-specific constraints on top of these.
"""

from __future__ import annotations

from decimal import Decimal

from .constraints import (
    Add,
    Binding,
    ConceptRef,
    ConstraintKind,
    ConstraintTemplate,
    Div,
    Ref,
    Severity,
    Sub,
)
from .intervals import Tolerance

# Monetary default: tight for ground-truth (rel_ground_truth=0), 0.5% for text.
MONEY = Tolerance(abs=Decimal("1"), rel=Decimal("0.005"))
# Ratios live on a 0..1 scale; bands are absolute-small + relative.
RATIO = Tolerance(abs=Decimal("0.0005"), rel=Decimal("0.01"),
                  rel_ground_truth=Decimal("0.0005"))


def _c(concept: str, *fallbacks: str) -> ConceptRef:
    return ConceptRef(concept, Binding.CONSOLIDATED, fallbacks=tuple(fallbacks))


def _opt(concept: str) -> ConceptRef:
    """A term that contributes 0 when the filing doesn't tag it."""
    return ConceptRef(concept, Binding.CONSOLIDATED, optional_zero=True)


def _agg(concept: str, dim: str) -> Ref:
    return Ref(ConceptRef(concept, Binding.AGGREGATE, aggregate_dim=dim))


def _eq(tid, desc, target, expr, kind=ConstraintKind.EQUALITY, tol=MONEY,
        **kw) -> ConstraintTemplate:
    return ConstraintTemplate(tid, kind, desc, target, expr, tolerance=tol, **kw)


# equity.total falls back to equity.parent for filers without NCI.
EQUITY = _c("equity.total", "equity.parent")

REGISTRY: tuple[ConstraintTemplate, ...] = (
    # --- Balance sheet ---
    _eq("bs.balance", "Assets = Liabilities + Total equity + Mezzanine equity",
        _c("assets.total"),
        Add((Ref(_c("liabilities.total")), Ref(EQUITY), Ref(_opt("equity.temporary"))))),
    _eq("bs.lse_crosscheck", "Total liabilities & equity = Total assets",
        _c("liabilities_and_equity.total"), Ref(_c("assets.total"))),
    _eq("bs.lse_decomp", "Total liabilities & equity = Liabilities + Equity + Mezzanine",
        _c("liabilities_and_equity.total"),
        Add((Ref(_c("liabilities.total")), Ref(EQUITY), Ref(_opt("equity.temporary"))))),
    _eq("bs.assets_split", "Assets = Current + Non-current assets",
        _c("assets.total"),
        Add((Ref(_c("assets.current")), Ref(_c("assets.noncurrent"))))),
    _eq("bs.liabilities_split", "Liabilities = Current + Non-current liabilities",
        _c("liabilities.total"),
        Add((Ref(_c("liabilities.current")), Ref(_c("liabilities.noncurrent"))))),
    _eq("bs.equity_attribution", "Total equity = Parent equity + NCI",
        _c("equity.total"),
        Add((Ref(_c("equity.parent")), Ref(_c("equity.nci"))))),

    # --- Income statement ---
    _eq("is.gross_profit", "Gross profit = Revenue - Cost of revenue",
        _c("gross_profit.total"),
        Sub(Ref(_c("revenue.total")), Ref(_c("cogs.total")))),
    _eq("is.operating_income", "Operating income = Gross profit - Operating expenses",
        _c("operating_income.total"),
        Sub(Ref(_c("gross_profit.total")), Ref(_c("opex.total")))),
    # SOFT: the pretax->net bridge has a long tail of filing-specific items
    # (equity-method, discontinued ops, and minor others); small residuals are
    # advisory, not hard violations.
    _eq("is.pretax_to_net",
        "Consolidated net income = Pretax - Tax + Equity-method + Discontinued ops",
        _c("net_income.consolidated", "net_income.parent"),
        Add((Sub(Ref(_c("pretax_income.total")), Ref(_c("income_tax.total"))),
             Ref(_opt("income.equity_method")), Ref(_opt("income.discontinued")))),
        severity=Severity.SOFT),
    _eq("is.net_income_attribution", "Consolidated net income = Parent + NCI",
        _c("net_income.consolidated"),
        Add((Ref(_c("net_income.parent")), Ref(_c("net_income.nci"))))),

    # --- Segment roll-ups ---
    _eq("rev.segments_sum", "Sum of segment revenue = Total revenue",
        _c("revenue.total"), _agg("revenue.segment", "segment"),
        kind=ConstraintKind.SUM),
    _eq("opinc.segments_sum", "Sum of segment operating income = Operating income",
        _c("operating_income.total"), _agg("operating_income.segment", "segment"),
        kind=ConstraintKind.SUM),

    # --- Derived ratios (definition checks) ---
    _eq("margin.gross", "Gross margin = Gross profit / Revenue",
        _c("gross_margin.ratio"),
        Div(Ref(_c("gross_profit.total")), Ref(_c("revenue.total"))),
        kind=ConstraintKind.RATIO_DEF, tol=RATIO),
    _eq("margin.operating", "Operating margin = Operating income / Revenue",
        _c("operating_margin.ratio"),
        Div(Ref(_c("operating_income.total")), Ref(_c("revenue.total"))),
        kind=ConstraintKind.RATIO_DEF, tol=RATIO),
    _eq("margin.net", "Net margin = Net income (parent) / Revenue",
        _c("net_margin.ratio"),
        Div(Ref(_c("net_income.parent")), Ref(_c("revenue.total"))),
        kind=ConstraintKind.RATIO_DEF, tol=RATIO),
    _eq("tax.effective_rate", "Effective tax rate = Income tax / Pretax income",
        _c("effective_tax_rate.ratio"),
        Div(Ref(_c("income_tax.total")), Ref(_c("pretax_income.total"))),
        kind=ConstraintKind.RATIO_DEF, tol=RATIO),
)
