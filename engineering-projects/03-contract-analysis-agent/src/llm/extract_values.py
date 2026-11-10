"""Per-clause operative value extraction, with a grounding check: any
extracted field (including the verbatim evidence substring) that
doesn't actually appear in the clause's own text after normalization is
nulled out and recorded in `ungrounded_fields`, rather than trusted. This
is the "code decides" half of grounding -- the LLM proposes a value, a
plain substring check (no LLM involved) either confirms or discards it.
"""

from __future__ import annotations

import json
from typing import Optional

from provider import LLMProvider
from schemas import ClauseExtraction, ExtractedValues

_VALUE_FIELDS = (
    "amount", "currency", "duration_value", "duration_unit",
    "notice_days", "jurisdiction", "date", "evidence",
)


def build_extraction_prompt(clause_type: str, clause_text: str) -> str:
    return (
        f'Extract operative values from this "{clause_type}" contract clause. Return ONLY a JSON '
        "object with these fields, using null for any that don't apply to this clause:\n"
        "- amount (number, e.g. a dollar cap)\n"
        "- currency (e.g. \"USD\")\n"
        "- duration_value (number)\n"
        "- duration_unit (\"day\", \"month\", or \"year\")\n"
        "- notice_days (integer, if the clause specifies a notice period in days)\n"
        "- jurisdiction (e.g. a US state or country name)\n"
        "- date (ISO 8601 string, if the clause names a specific date)\n"
        '- evidence (an EXACT verbatim substring copied from the clause text below, not a '
        "paraphrase, supporting the values above)\n\n"
        f"Clause text:\n{clause_text}"
    )


def _normalize(s: str) -> str:
    return " ".join(str(s).split()).lower()


def _value_variants(value) -> list[str]:
    if value is None:
        return []
    if isinstance(value, bool):
        return [str(value)]
    if isinstance(value, float):
        variants = [str(value)]
        if value == int(value):
            variants.append(str(int(value)))
            variants.append(f"{int(value):,}")
        else:
            variants.append(f"{value:,}")
        return variants
    if isinstance(value, int):
        return [str(value), f"{value:,}"]
    return [str(value)]


def ground_check(values: ExtractedValues, clause_text: str) -> ExtractedValues:
    norm_clause = _normalize(clause_text)
    ungrounded = []

    def is_grounded(value) -> bool:
        return any(_normalize(v) in norm_clause for v in _value_variants(value))

    for field in _VALUE_FIELDS:
        val = getattr(values, field)
        if val is None:
            continue
        if not is_grounded(val):
            ungrounded.append(field)
            setattr(values, field, None)

    values.ungrounded_fields = ungrounded
    values.grounded = len(ungrounded) == 0
    return values


def parse_extraction_response(response: str) -> ExtractedValues:
    try:
        data = json.loads(response)
        if not isinstance(data, dict):
            data = {}
    except (json.JSONDecodeError, TypeError):
        data = {}

    kwargs = {}
    for field in _VALUE_FIELDS:
        val = data.get(field)
        kwargs[field] = val if val != "" else None
    return ExtractedValues(**kwargs)


def extract_clause_values(
    clause_id: str, clause_type: str, clause_text: str, provider: LLMProvider,
) -> ClauseExtraction:
    prompt = build_extraction_prompt(clause_type, clause_text)
    response = provider.complete(prompt)
    values = parse_extraction_response(response)
    values = ground_check(values, clause_text)
    return ClauseExtraction(clause_id=clause_id, clause_type=clause_type, values=values)
