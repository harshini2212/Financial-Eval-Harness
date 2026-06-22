"""mini-Felix: a Claude tool-use agent that answers financial questions over a
filing and emits a Retrieval -> Definition -> Calculation derivation trace, plus a
verifier that checks every number against ground truth + accounting identities.
"""

from .felix import AgentAnswer, FelixAgent
from .verify import Verdict, verify_answer

__all__ = ["FelixAgent", "AgentAnswer", "verify_answer", "Verdict"]
