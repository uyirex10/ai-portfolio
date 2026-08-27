"""The extraction contract.

Everything downstream is built on these models: Gemini's structured output is
constrained to them, the retry loop feeds *their* validation errors back into the
prompt, and the OpenAPI page the client's engineers integrate against is generated
from them. A field's type and its required-vs-optional status are the two decisions
that actually reach the caller, so both are made deliberately below rather than
inherited from whatever the model happened to return.

The rule for required vs optional throughout: a field is optional when the *concept*
can legitimately be absent from a contract, not when extraction happens to fail. A
list field being optional means it comes back empty, never null.
"""

import re
from datetime import date
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, field_validator

# Cross-checked by the cheap second pass in Phase 3; disagreement lowers confidence.
# These are the fields where being wrong costs real money or a missed deadline -
# paying the wrong entity, missing an auto-renewal window, missing a discount cutoff.
# penalty_clauses stays out: it is the one money-adjacent field whose value is a whole
# negotiated condition, too long and too variably phrased for a cheap pass to compare
# usefully.
#
# NOTE for Phase 3: payment_terms cannot be cross-checked by string equality. It is
# free prose, so two extractions can both be correct and share almost no characters -
# "Net 30" against "payment due within 30 days" is agreement, not disagreement, and a
# string comparison would read it as the latter and wrongly drop the confidence. The
# comparison has to be on meaning: normalize both passes to the underlying obligation
# (net days, discount percent and window, currency) and compare that, or have the
# second pass judge equivalence directly. The score it moves is the field-level
# payment_terms_confidence, since the terms themselves are bare strings.
CRITICAL_FIELDS = ("parties", "key_dates", "payment_terms", "renewal_date")

# Defined once rather than repeated on four fields, so the bounds cannot drift apart.
# Every confidence below is required with no default: a default would let the model
# skip self-scoring and have the schema quietly invent a number on its behalf, which
# is the opposite of what a confidence signal is for.
Confidence = Annotated[
    float,
    Field(
        ge=0.0,
        le=1.0,
        description=(
            "How confident the extractor is in this value, 0.0 to 1.0. Lowered when "
            "the second-pass cross-check disagrees with the first pass."
        ),
    ),
]


def _strip_required(value: object) -> object:
    """Strip a required text field *before* its constraints are checked.

    Runs in "before" mode so that min_length still sees the stripped string: a
    whitespace-only value then fails as a proper ValidationError the retry loop can
    feed back to the model, rather than slipping through as an empty string.
    Non-strings pass through untouched so type validation reports them itself.
    """
    return value.strip() if isinstance(value, str) else value


def _strip_optional(value: str | None) -> str | None:
    """Strip an optional text field, collapsing a now-empty one to None.

    None-tolerant on purpose: an optional field is explicitly null in the model's
    output - it is nullable in the generated schema, so it is emitted rather than
    omitted - and that null reaches this validator. An empty string after stripping
    is not a value either, so it becomes None too rather than a second falsy case the
    caller has to test for.
    """
    if value is None:
        return None
    return value.strip() or None


class Party(BaseModel):
    """An entity bound by the contract."""

    model_config = ConfigDict(extra="forbid")

    name: str = Field(
        min_length=1,
        description="Legal name of the party as written in the document.",
    )
    # Optional because a contract can legitimately name a party without ever stating
    # what side of the deal they are on.
    role: str | None = Field(
        default=None,
        description='Role in the agreement, e.g. "buyer", "supplier", "guarantor".',
    )
    confidence: Confidence

    _clean_name = field_validator("name", mode="before")(_strip_required)
    _clean_role = field_validator("role")(_strip_optional)


class LabeledDate(BaseModel):
    """A single calendar date plus what the contract calls it."""

    model_config = ConfigDict(extra="forbid")

    label: str = Field(
        min_length=1,
        description=(
            "What this date represents, lowercase snake_case. Prefer the canonical "
            'labels "effective_date", "signing_date", "expiration_date" and '
            "renewal_date where they apply."
        ),
    )
    # A strict date, not a string. Contracts do express dates as prose ("thirty days
    # after the Effective Date"), and that prose fails validation here on purpose:
    # that failure is exactly what the Phase 2 retry loop exists to catch and what
    # the structured 422 exists to report. Accepting a bare string instead would push
    # the parsing onto the caller and break the brief's promise of clean JSON.
    value: date = Field(description="The date itself, ISO 8601 (YYYY-MM-DD).")
    confidence: Confidence

    @field_validator("label", mode="before")
    @classmethod
    def normalize_label(cls, value: object) -> object:
        """Fold label spelling variants together.

        Left as a free string rather than an enum - contracts carry more kinds of date
        than can be enumerated up front, and an enum would turn an unanticipated but
        perfectly good date into a hard failure. Normalizing instead means
        "Effective Date", "effective date" and "effective_date" all key the same way
        for the caller, without closing the set.

        Before-mode, like the other text cleaners, so min_length still judges the
        normalized string and a whitespace-only label cannot normalize its way to "".
        """
        if not isinstance(value, str):
            return value
        return re.sub(r"[\s-]+", "_", value.strip().lower())


class PenaltyClause(BaseModel):
    """A stated consequence and the condition that triggers it."""

    model_config = ConfigDict(extra="forbid")

    trigger: str = Field(
        min_length=1,
        description="The condition or breach that activates the penalty.",
    )
    penalty: str = Field(
        min_length=1,
        description="The consequence that follows, quoted or closely paraphrased.",
    )
    confidence: Confidence

    _clean_text = field_validator("trigger", "penalty", mode="before")(_strip_required)


class ExtractedContract(BaseModel):
    """The full result of one extraction - the payload /v1/extract returns."""

    model_config = ConfigDict(
        extra="forbid",
        json_schema_extra={
            "example": {
                "parties": [
                    {"name": "Northwind Logistics Ltd.", "role": "supplier", "confidence": 0.97},
                    {"name": "Acme Procurement GmbH", "role": "buyer", "confidence": 0.95},
                ],
                "key_dates": [
                    {"label": "effective_date", "value": "2026-01-15", "confidence": 0.96},
                    {"label": "expiration_date", "value": "2028-01-14", "confidence": 0.91},
                ],
                "payment_terms": [
                    "Net 30 days from date of invoice",
                    "2% discount if paid within 10 days",
                ],
                "payment_terms_confidence": 0.89,
                "penalty_clauses": [
                    {
                        "trigger": "Delivery more than 5 business days late",
                        "penalty": "1.5% of the order value per week, capped at 10%",
                        "confidence": 0.83,
                    }
                ],
                "renewal_date": {
                    "label": "renewal_date",
                    "value": "2027-11-15",
                    "confidence": 0.74,
                },
            }
        },
    )

    # At least one party and at least one date: a document with neither is not a
    # contract, so an empty list here means the extraction was wrong, not that the
    # document was unusual. Letting it through would hand the caller a technically
    # valid response that is useless.
    parties: list[Party] = Field(
        min_length=1,
        description="Every entity bound by the agreement. At least one.",
    )
    key_dates: list[LabeledDate] = Field(
        min_length=1,
        description=(
            "Dates the agreement turns on - effective, signing, expiration, and any "
            "other dated milestone. At least one."
        ),
    )
    # Required, but legitimately empty: plenty of agreements (NDAs, MSAs) state no
    # payment terms at all. Empty list, never null - the caller should be able to
    # iterate this unconditionally.
    payment_terms: list[str] = Field(
        description=(
            "Payment obligations as stated - schedules, net terms, discounts, "
            "currencies. Empty if the contract states none."
        ),
    )
    # Plain strings have nowhere to hang a per-item confidence, so the field carries
    # one score covering the extraction as a whole.
    payment_terms_confidence: Confidence

    # Genuinely absent from many contracts, so it defaults to empty rather than being
    # required. default_factory, not default=[], to avoid the shared-mutable trap.
    penalty_clauses: list[PenaltyClause] = Field(
        default_factory=list,
        description="Stated penalties and what triggers them. Empty if none.",
    )
    # Reuses LabeledDate rather than a date/confidence pair of scalars, so the date
    # and its score are atomically either both present or both absent and cannot
    # desync. Null when the contract has no renewal provision.
    renewal_date: LabeledDate | None = Field(
        default=None,
        description=(
            "The next renewal or auto-renewal date, if the contract provides for one. "
            "Null when it does not."
        ),
    )

    @field_validator("payment_terms")
    @classmethod
    def clean_payment_terms(cls, value: list[str]) -> list[str]:
        """Strip each term and drop the blanks.

        The model tends to pad a list toward a plausible length with empty strings.
        An empty string is not a payment term, and shipping one makes the caller
        write a guard we can just as easily write once here.
        """
        return [term.strip() for term in value if term.strip()]
