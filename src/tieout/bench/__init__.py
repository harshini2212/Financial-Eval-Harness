"""tieout-FB — a small BFB-style, derivation-graded benchmark.

Runs the Felix agent over a question set and grades each answer on a rubric whose
Retrieval / Calculation line items are auto-graded (fact store + the constraint
layer), reproducing Rogo's "graded on the audit trail, not just the bottom line"
methodology — and surfacing the money metric: answers an LLM-judge rubber-stamps
that derivation-grading catches as wrong.
"""

from .grade import grade_one, llm_judge
from .run import run_benchmark

__all__ = ["grade_one", "llm_judge", "run_benchmark"]
