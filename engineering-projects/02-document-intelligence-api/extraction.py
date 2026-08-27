"""The main extraction pass, with a bounded validation-feedback retry.

Self-reported confidence is scored on a four-value discrete scale rather than a free
float. That is not a stylistic choice - it came out of a measured trial. Given a
continuous scale the model parks on one value regardless of input quality: an anchored
rubric moved every score from 1.0 to 0.95 and left it there, scoring a clean contract
and an OCR-mangled one identically. Removing the hedge value is what produced
discrimination (clean 1.00 / ambiguous 0.88 / degraded 0.83, stable across repeats).

On a validation failure the fix is not to give up and not to retry blindly: the actual
Pydantic error is fed back into the prompt so the next attempt is told exactly what was
wrong with the last one. Bounded, because a model that cannot satisfy the schema twice
will not satisfy it on the fifth attempt either - it will just cost five times as much.
"""


from google.genai import types
from pydantic import ValidationError

import usage
from config import MAIN_MODEL, TEMPERATURE, get_client
from models import ExtractedContract

# One initial attempt plus one repair. A second repair was not worth its cost in
# testing: failures that survive the first repair are structural (the document does not
# contain a required concept at all), and no rephrasing fixes those.
MAX_ATTEMPTS = 2

# Four values, no intermediates. The forbidden-value line is load-bearing: without it
# the model reintroduces 0.95 and the signal collapses back to a constant.
DISCRETE_BANDS = """
Each confidence score MUST be exactly one of these four values. No other value is
permitted, and intermediate values such as 0.95 are forbidden:

  1.0  verbatim in the document, one possible reading, nothing inferred or reformatted
  0.8  clearly stated, but you normalized the form (rewrote a date, cleaned a name)
  0.5  stated indirectly, or you picked between readings that could reasonably differ
  0.2  inferred, guessed, or read out of damaged / unclear text
"""

EXTRACTION_PROMPT = f"""\
Extract the structured contract data from the document below.

Extract only what the document supports. Do not invent a party, a date, or a term that
is not there - an absent penalty clause is an empty list, not a guess.
{DISCRETE_BANDS}
---
"""

REPAIR_PROMPT = """\
Your previous response failed validation. Correct it.

This is what you returned:
{previous}

These are the exact validation errors it produced:
{errors}

Fix precisely these problems and return the corrected JSON. Do not change values that
were not implicated in an error. If an error says a date is invalid, the document
probably expresses it in prose ("thirty days after signing") - a real calendar date is
required, so use the one the document implies, and score your confidence accordingly.
If a required list is empty, re-read the document for what belongs in it.

The document again:
---
{document}
"""


class ExtractionError(Exception):
    """The model could not produce output satisfying the schema.

    Carries the structured detail the API layer turns into a 422 body: which attempt
    failed, what the validator objected to, and what the model actually said. Never
    let this surface as a raw crash.
    """

    def __init__(self, message: str, *, attempts: int, errors: list[dict], raw: str):
        super().__init__(message)
        self.attempts = attempts
        self.errors = errors
        self.raw = raw


def _generate(prompt: str) -> str:
    """One constrained generation call, returning raw JSON text.

    Isolated as its own function so the retry loop above it can be exercised with
    deliberately malformed output without touching the network.
    """
    response = get_client().models.generate_content(
        model=MAIN_MODEL,
        contents=prompt,
        config=types.GenerateContentConfig(
            response_mime_type="application/json",
            # response_json_schema, not response_schema: the Developer API rejects the
            # additionalProperties:false that extra="forbid" emits, with a 400, on the
            # response_schema path only. Verified against the live API.
            response_json_schema=ExtractedContract.model_json_schema(),
            temperature=TEMPERATURE,
        ),
    )
    usage.record(response)
    return (response.text or "").strip()


def _readable_errors(exc: ValidationError) -> str:
    """Render validation errors as instructions rather than as a Python repr.

    The model is the audience here. "key_dates.0.value: Input should be a valid date"
    is actionable; a pasted ValidationError object is noise wrapped around the same
    sentence.
    """
    lines = []
    for err in exc.errors():
        location = ".".join(str(part) for part in err["loc"]) or "(root)"
        lines.append(f"- {location}: {err['msg']}")
    return "\n".join(lines)


def extract_contract(text: str, max_attempts: int = MAX_ATTEMPTS) -> ExtractedContract:
    """Run the main pass over already-extracted document text.

    Takes text, not a PDF: pdfplumber lives in documents.py, and keeping this boundary
    at text means extraction is testable without a binary fixture.

    Raises ExtractionError when every attempt fails validation.
    """
    prompt = EXTRACTION_PROMPT + text
    raw = ""
    errors: list[dict] = []

    for attempt in range(1, max_attempts + 1):
        raw = _generate(prompt)
        try:
            return ExtractedContract.model_validate_json(raw)
        except ValidationError as exc:
            # This also covers malformed JSON, including a response truncated mid-object
            # by the token limit: model_validate_json reports that as a validation error
            # of type json_invalid rather than raising JSONDecodeError, so the same
            # feedback path handles it and no separate parser branch is needed.
            errors = exc.errors()
            detail = _readable_errors(exc)

        if attempt < max_attempts:
            prompt = REPAIR_PROMPT.format(
                previous=raw[:4000], errors=detail, document=text
            )

    raise ExtractionError(
        f"The model's output failed schema validation after {max_attempts} attempts.",
        attempts=max_attempts,
        errors=[{"loc": list(e["loc"]), "msg": e["msg"]} for e in errors],
        raw=raw[:4000],
    )
