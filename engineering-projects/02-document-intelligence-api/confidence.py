"""The second-pass cross-check.

Why this exists in the shape it does. A measured trial established that the main
pass's self-reported confidence tracks document quality only coarsely, and does not
track correctness at all: on an OCR-damaged contract the model scored a value it had
silently repaired correctly and a value it had got wrong (an uncorrected "Acrne" for
"Acme") at the identical 0.8. So the cross-check is not refining an existing signal -
it is the only evidence of correctness in the system, and it has to earn that alone.

Two consequences for the design:

1. The second pass never sees the first pass's output. Asking the model to re-score
   its own answer is precisely what was measured failing. second_pass() takes the
   document text and nothing else, enforced by its signature.

2. The second pass extracts VERBATIM - values exactly as printed, uncorrected. The
   main pass normalizes (rewrites dates, cleans names), and silent normalization is
   where its errors hide. Comparing a normalized value against an as-printed one
   surfaces every place the main pass changed something, which is the population the
   errors live in.

Known limit, stated honestly, and measured. Two passes over the same text with the
same model can make the SAME misreading, and an agreement reached that way is not
evidence. On the OCR-damaged fixture both passes read "Acrne" for "Acme", agreed, and
the wrong value kept a high score - while the party the main pass had repaired
CORRECTLY was flagged, because flagging is what a rewrite earns. So on a badly damaged
document this signal can be anti-correlated with correctness at the level of an
individual field.

What it therefore is: a detector of unverified rewriting and of values only one pass
can see. What it is not: a correctness oracle. The README should say so plainly, and
a caller must not read a high score as "verified".
"""

import difflib
import re
from datetime import date

from google.genai import types
from pydantic import BaseModel, ConfigDict, Field

import usage
from config import SECOND_PASS_MODEL, TEMPERATURE, get_client
from models import CRITICAL_FIELDS, ExtractedContract

# Outcomes, and the ceiling each one imposes. Expressed on the same four-value ladder
# the main pass scores against, so a cross-checked score still reads as a band rather
# than an arbitrary decimal.
AGREE = "agree"
REWRITTEN = "rewritten"  # same value, different characters - the main pass normalized it
MISSING = "missing"      # the second pass did not report this item
CONFLICT = "conflict"    # the two passes contradict each other
OMITTED = "omitted"      # the MAIN pass reported nothing where the second pass found something
UNCHECKED = "unchecked"  # the cross-check could not run

# REWRITTEN sits above CONFLICT deliberately. A value the main pass rewrote is
# unverified, not refuted: rewriting "N0rthwind" to "Northwind" is a repair as often
# as it is a corruption, and 0.5 says "nobody has confirmed this" rather than "this is
# probably wrong". A contradiction, or a party that a verbatim transcription never saw
# at all, is a stronger claim and earns the bottom band.
CAPS = {REWRITTEN: 0.5, MISSING: 0.5, CONFLICT: 0.2}

# Above this ratio two names are the same entity spelled differently (the main pass
# corrected or normalized it) rather than a different entity entirely.
SAME_ENTITY_RATIO = 0.6


# --------------------------------------------------------------- second pass ---


class VerbatimDate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    label: str = Field(description="What this date represents, lowercase snake_case.")
    value: date = Field(description="The date in ISO 8601 form.")
    as_printed: str = Field(
        description="The date EXACTLY as it appears in the document, character for "
        "character, including any damage or odd spacing."
    )


class PaymentFigures(BaseModel):
    """Payment terms reduced to numbers.

    payment_terms on the main pass is free prose, so string comparison is useless -
    "Net 30" and "payment due within 30 days" are the same obligation sharing almost
    no characters. Reducing the second pass to the underlying figures makes the
    comparison semantic and deterministic: both phrasings yield 30.
    """

    model_config = ConfigDict(extra="forbid")

    net_days: int | None = Field(
        default=None, description="Days until payment is due. Null if not stated."
    )
    discount_percent: float | None = Field(
        default=None, description="Early-payment discount percentage. Null if none."
    )
    discount_window_days: int | None = Field(
        default=None, description="Days within which the discount applies. Null if none."
    )


class SecondPass(BaseModel):
    """Deliberately narrower than ExtractedContract: only the critical fields."""

    model_config = ConfigDict(extra="forbid")

    party_names_as_printed: list[str] = Field(
        description="Each party's name EXACTLY as printed, character for character. "
        "Do not correct spelling, spacing or obvious scanning errors."
    )
    key_dates: list[VerbatimDate]
    payment_figures: PaymentFigures
    renewal_date: date | None = Field(
        default=None, description="Renewal or auto-renewal date. Null if none."
    )


SECOND_PASS_PROMPT = """\
Read the contract below and report only what is literally printed on the page.

This is a verification pass. Transcribe, do not interpret:
  - Copy party names EXACTLY as printed. If the page reads "N0rthwind", write
    "N0rthwind". Do not repair scanning damage, spacing, or spelling.
  - For each date, give both the ISO form and the characters exactly as printed.
  - Reduce the payment terms to their numbers. Leave a figure null if it is absent.
  - Report nothing the document does not state.

---
"""


def second_pass(text: str) -> SecondPass:
    """Re-extract the critical fields independently.

    Takes only the document text. It cannot be shown the first pass's answer, because
    a model asked to check its own output agrees with it.
    """
    response = get_client().models.generate_content(
        model=SECOND_PASS_MODEL,
        contents=SECOND_PASS_PROMPT + text,
        config=types.GenerateContentConfig(
            response_mime_type="application/json",
            response_json_schema=SecondPass.model_json_schema(),
            temperature=TEMPERATURE,
        ),
    )
    usage.record(response)
    return SecondPass.model_validate_json((response.text or "").strip())


# ---------------------------------------------------------------- comparison ---


class Finding(BaseModel):
    """One field's cross-check result.

    Serializable so it can be returned to the caller, written to the request log, and
    rendered on the operations page.
    """

    model_config = ConfigDict(extra="forbid")

    field: str
    item: str
    outcome: str
    main_pass: str
    second_pass: str
    confidence_before: float
    confidence_after: float

    @property
    def lowered(self) -> bool:
        return self.confidence_after < self.confidence_before


def _norm(value: str) -> str:
    """Alphanumerics only, lowercased - so punctuation and spacing never decide a match."""
    return re.sub(r"[^a-z0-9]", "", value.lower())


# Contracts write numbers in words at least as often as in digits ("forty-five days
# of receipt"), and a digits-only reader scores those as a conflict on a field that was
# extracted perfectly. Live testing hit exactly that, so words are read too. Only up to
# ninety-nine: beyond that contracts use digits, and the parsing gets ambiguous.
_UNIT_WORDS = {
    "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7,
    "eight": 8, "nine": 9, "ten": 10, "eleven": 11, "twelve": 12, "thirteen": 13,
    "fourteen": 14, "fifteen": 15, "sixteen": 16, "seventeen": 17, "eighteen": 18,
    "nineteen": 19,
}
_TENS_WORDS = {
    "twenty": 20, "thirty": 30, "forty": 40, "fifty": 50, "sixty": 60,
    "seventy": 70, "eighty": 80, "ninety": 90,
}


def _spelled_numbers(text: str) -> set[float]:
    """Numbers written as words, including hyphenated compounds like "forty-five"."""
    found: set[float] = set()
    words = re.findall(r"[a-z]+", text.lower())
    index = 0
    while index < len(words):
        word = words[index]
        if word in _TENS_WORDS:
            value = _TENS_WORDS[word]
            # "forty five" and "forty-five" both tokenize to two words here.
            if index + 1 < len(words) and words[index + 1] in _UNIT_WORDS:
                if _UNIT_WORDS[words[index + 1]] < 10:
                    value += _UNIT_WORDS[words[index + 1]]
                    index += 1
            found.add(float(value))
        elif word in _UNIT_WORDS:
            found.add(float(_UNIT_WORDS[word]))
        index += 1
    return found


def _numbers(strings: list[str]) -> set[float]:
    """Every number the prose states, in digits or in words.

    Reading words as well makes the check more permissive, and that is the right
    direction to err: a false conflict strips confidence from a field that was
    extracted correctly, while a false agreement merely leaves a score where the main
    pass already put it. The cross-check can only lower, so permissiveness costs less
    than strictness here.
    """
    numerals = {float(n) for s in strings for n in re.findall(r"\d+(?:\.\d+)?", s)}
    return numerals | _spelled_numbers(" ".join(strings))


def _cap(current: float, outcome: str) -> float:
    """Apply an outcome's ceiling.

    Only ever lowers. Agreement is not positive evidence - two passes can share a
    misreading - so it must never raise a score the main pass set low for its own
    reasons.
    """
    return min(current, CAPS[outcome]) if outcome in CAPS else current


def _check_parties(extracted, second, findings):
    printed = {_norm(n): n for n in second.party_names_as_printed}
    for party in extracted.parties:
        key = _norm(party.name)
        if key in printed:
            outcome, matched = AGREE, printed[key]
        else:
            close = difflib.get_close_matches(key, printed, n=1, cutoff=SAME_ENTITY_RATIO)
            # A near match is the same entity printed differently - the main pass
            # rewrote it, which is unverified rather than wrong. No match at all means
            # a verbatim transcription of the page never saw this party, which is a
            # much stronger signal and is treated as a contradiction.
            outcome = REWRITTEN if close else CONFLICT
            matched = printed[close[0]] if close else "(not found)"
        before = party.confidence
        party.confidence = _cap(before, outcome)
        findings.append(Finding(
            field="parties", item=party.name, outcome=outcome,
            main_pass=party.name, second_pass=matched,
            confidence_before=before, confidence_after=party.confidence,
        ))


def _check_key_dates(extracted, second, findings):
    printed = {_norm(d.label): d for d in second.key_dates}

    # key_dates carries no minimum, so the main pass returning nothing is a valid
    # answer - a purely relative-dated contract has no calendar dates to report. But it
    # is only valid if the second pass agrees there were none. If a verbatim reading
    # DID find dates, the main pass dropped them, and there is no confidence score to
    # lower because there is no field. Report it rather than let an omission be the one
    # failure the cross-check cannot see.
    if not extracted.key_dates:
        if second.key_dates:
            findings.append(Finding(
                field="key_dates", item="(none extracted)", outcome=OMITTED,
                main_pass="(no dates)",
                second_pass="; ".join(
                    f"{d.label}={d.value}" for d in second.key_dates
                )[:200],
                # No score moves: informational, so it must not register as a drop.
                confidence_before=0.0, confidence_after=0.0,
            ))
        return

    for labeled in extracted.key_dates:
        seen = printed.get(_norm(labeled.label))
        if seen is None:
            outcome, other = MISSING, "(not found)"
        elif seen.value == labeled.value:
            outcome, other = AGREE, f"{seen.value} (printed: {seen.as_printed!r})"
        else:
            outcome, other = CONFLICT, f"{seen.value} (printed: {seen.as_printed!r})"
        before = labeled.confidence
        labeled.confidence = _cap(before, outcome)
        findings.append(Finding(
            field="key_dates", item=labeled.label, outcome=outcome,
            main_pass=str(labeled.value), second_pass=other,
            confidence_before=before, confidence_after=labeled.confidence,
        ))


def _check_payment_terms(extracted, second, findings):
    figures = {k: v for k, v in second.payment_figures.model_dump().items() if v is not None}
    stated = _numbers(extracted.payment_terms)
    if not figures:
        # Both silent is agreement; prose on one side and no figures on the other is not.
        outcome = AGREE if not extracted.payment_terms else MISSING
        other = "(no figures found)"
    else:
        unsupported = {k: v for k, v in figures.items() if float(v) not in stated}
        outcome = AGREE if not unsupported else CONFLICT
        other = ", ".join(f"{k}={v}" for k, v in figures.items())
    before = extracted.payment_terms_confidence
    extracted.payment_terms_confidence = _cap(before, outcome)
    findings.append(Finding(
        field="payment_terms", item="(all terms)", outcome=outcome,
        main_pass="; ".join(extracted.payment_terms) or "(none)", second_pass=other,
        confidence_before=before, confidence_after=extracted.payment_terms_confidence,
    ))


def _check_renewal_date(extracted, second, findings):
    main = extracted.renewal_date
    if main is None:
        return  # nothing to score; a date the main pass never claimed needs no check
    if second.renewal_date is None:
        outcome, other = MISSING, "(not found)"
    elif second.renewal_date == main.value:
        outcome, other = AGREE, str(second.renewal_date)
    else:
        outcome, other = CONFLICT, str(second.renewal_date)
    before = main.confidence
    main.confidence = _cap(before, outcome)
    findings.append(Finding(
        field="renewal_date", item=main.label, outcome=outcome,
        main_pass=str(main.value), second_pass=other,
        confidence_before=before, confidence_after=main.confidence,
    ))


# Keyed by CRITICAL_FIELDS, so adding a field to that constant without writing its
# comparison raises immediately instead of silently skipping the check.
CHECKS = {
    "parties": _check_parties,
    "key_dates": _check_key_dates,
    "payment_terms": _check_payment_terms,
    "renewal_date": _check_renewal_date,
}


def cross_check(
    extracted: ExtractedContract, second: SecondPass
) -> tuple[ExtractedContract, list[Finding]]:
    """Lower confidence wherever the two passes disagree.

    Returns a copy - the caller keeps the untouched main-pass result, which the
    request log needs in order to show what the cross-check actually changed.
    """
    adjusted = extracted.model_copy(deep=True)
    findings: list[Finding] = []
    for field in CRITICAL_FIELDS:
        CHECKS[field](adjusted, second, findings)
    # Re-validate rather than trust in-place assignment: confidence was written
    # directly, which bypasses field validation.
    return ExtractedContract.model_validate(adjusted.model_dump()), findings


def verify(
    text: str, extracted: ExtractedContract
) -> tuple[ExtractedContract, list[Finding]]:
    """Run the second pass and apply it, degrading to the main pass if it fails.

    A failed cross-check must not fail the request: the client still gets a usable
    extraction, it just carries unverified confidence, and the findings say so.
    """
    try:
        second = second_pass(text)
    except Exception as exc:
        return extracted, [Finding(
            field="(all)", item="(cross-check)", outcome=UNCHECKED,
            main_pass="", second_pass=f"{type(exc).__name__}: {exc}"[:200],
            confidence_before=0.0, confidence_after=0.0,
        )]
    return cross_check(extracted, second)
