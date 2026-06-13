"""Violation attribution: WHY did a constraint fail?

Three-way label, disambiguated by XBRL ground truth:
  * extraction_error      — ground truth satisfies the identity, but a text
                            figure disagrees with it (the model got it wrong).
  * filing_inconsistency  — the ground-truth figures THEMSELVES break the
                            identity (the filing doesn't tie out).
  * constraint_model_error— text matches ground truth yet the identity fires
                            (our template is wrong / too strict).
  * undetermined          — no complete ground truth to decide.
"""

from .attribute import Attribution, Label, attribute_violation, attribute_run

__all__ = ["Attribution", "Label", "attribute_violation", "attribute_run"]
