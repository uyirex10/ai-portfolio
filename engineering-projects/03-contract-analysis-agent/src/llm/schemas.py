"""Pydantic schemas for clause classification and value extraction.

Stage C's 8 chosen clause types, exact category names from the CUAD
data (see DECISIONS.md). Amended in Stage I step 1: Agreement Date was
dropped (gold support of 0 under the 50% overlap rule -- its spans are
always buried too deep in a large preamble clause to ever reach 50%
overlap, independent of classifier quality) and replaced with
Post-Termination Services, the next category in the original Stage C
ranking.
"""

from __future__ import annotations

from typing import List, Optional

from pydantic import BaseModel, Field

CLAUSE_TYPES = [
    "Cap On Liability",
    "Termination For Convenience",
    "Notice Period To Terminate Renewal",
    "Governing Law",
    "Post-Termination Services",
    "Expiration Date",
    "Effective Date",
    "Audit Rights",
]


class ClauseClassification(BaseModel):
    clause_id: str
    labels: List[str] = Field(default_factory=list)  # subset of CLAUSE_TYPES; empty = none of the 8


class ExtractedValues(BaseModel):
    """Operative values an LLM might pull out of one labeled clause.
    Every field is optional -- only the ones relevant to the clause's
    type should be non-null. `evidence` is the verbatim substring the
    LLM is claiming supports these values; `grounded` and
    `ungrounded_fields` are set by the grounding check, not the LLM."""

    amount: Optional[float] = None
    currency: Optional[str] = None
    duration_value: Optional[float] = None
    duration_unit: Optional[str] = None  # "day" | "month" | "year"
    notice_days: Optional[int] = None
    jurisdiction: Optional[str] = None
    date: Optional[str] = None  # ISO 8601 string if the LLM extracts one
    evidence: Optional[str] = None

    grounded: bool = False
    ungrounded_fields: List[str] = Field(default_factory=list)


class ClauseExtraction(BaseModel):
    clause_id: str
    clause_type: str
    values: ExtractedValues
