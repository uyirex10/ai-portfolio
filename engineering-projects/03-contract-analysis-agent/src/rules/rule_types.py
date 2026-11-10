"""Plain input/output types for the rule engine. Deliberately not
imported from src/llm/schemas.py -- src/rules/ stays decoupled from the
LLM package's import graph entirely, not just from LLM client packages,
so it can never accidentally gain a path to one.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import List, Optional


class Verdict(str, Enum):
    GREEN = "green"
    AMBER = "amber"
    RED = "red"
    NEEDS_REVIEW = "needs_review"


@dataclass
class ClauseInput:
    """Everything a rule is allowed to look at for one clause type. Any
    field left as None is either genuinely absent or was ungrounded and
    nulled by src/llm/extract_values.py's grounding check before this
    ever reaches a rule -- a rule cannot tell the difference, and by
    design it shouldn't need to: both cases fail closed the same way."""

    present: bool
    amount: Optional[float] = None
    currency: Optional[str] = None
    notice_days: Optional[int] = None
    jurisdiction: Optional[str] = None
    date: Optional[str] = None


@dataclass
class RuleResult:
    rule_id: str
    clause_type: str
    verdict: Verdict
    reason: str


@dataclass
class ClauseVerdicts:
    clause_id: str
    results: List[RuleResult] = field(default_factory=list)
