"""Tests for PDF text extraction and the validation-feedback retry loop.

Offline. The retry loop is exercised by replacing extraction._generate with canned
responses, which is the point of it being a separate function: forcing malformed model
output is a required test for this project, and waiting for the real model to misbehave
is not a test strategy.

PDF fixtures are assembled by hand rather than pulled from a library, so the suite
needs no dependency beyond pdfplumber itself.

Run directly:  python test_extraction.py
"""

import json
import sys
import traceback

import extraction
from documents import DocumentError, pdf_to_text
from extraction import ExtractionError, extract_contract
from models import ExtractedContract

# ---------------------------------------------------------------- pdf fixtures ---


def make_pdf(lines: list[str]) -> bytes:
    """The smallest PDF that still has a real, extractable text layer."""

    def escape(s: str) -> str:
        return s.replace("\\", r"\\").replace("(", r"\(").replace(")", r"\)")

    content = "BT /F1 11 Tf 50 750 Td 14 TL\n"
    for line in lines:
        content += f"({escape(line)}) Tj T*\n"
    content += "ET"
    stream = content.encode("latin-1")

    objects = [
        b"<</Type/Catalog/Pages 2 0 R>>",
        b"<</Type/Pages/Kids[3 0 R]/Count 1>>",
        b"<</Type/Page/Parent 2 0 R/MediaBox[0 0 612 792]"
        b"/Resources<</Font<</F1 5 0 R>>>>/Contents 4 0 R>>",
        b"<</Length " + str(len(stream)).encode() + b">>stream\n" + stream + b"\nendstream",
        b"<</Type/Font/Subtype/Type1/BaseFont/Helvetica>>",
    ]

    out = bytearray(b"%PDF-1.4\n")
    offsets = []
    for number, body in enumerate(objects, start=1):
        offsets.append(len(out))
        out += f"{number} 0 obj\n".encode() + body + b"\nendobj\n"

    xref_offset = len(out)
    size = len(objects) + 1
    out += f"xref\n0 {size}\n".encode() + b"0000000000 65535 f \n"
    for offset in offsets:
        out += f"{offset:010d} 00000 n \n".encode()
    out += f"trailer\n<</Size {size}/Root 1 0 R>>\nstartxref\n{xref_offset}\n%%EOF\n".encode()
    return bytes(out)


CONTRACT_LINES = [
    "SUPPLY AGREEMENT",
    "Entered into on 15 January 2026 between Northwind Logistics Ltd.",
    "and Acme Procurement GmbH. Payment is net 30 days from invoice.",
    "This agreement expires on 14 January 2028.",
]

VALID_JSON = json.dumps(
    {
        "parties": [{"name": "Northwind Logistics Ltd.", "confidence": 1.0}],
        "key_dates": [
            {"label": "effective_date", "value": "2026-01-15", "confidence": 1.0}
        ],
        "payment_terms": ["Net 30 days from invoice"],
        "payment_terms_confidence": 1.0,
    }
)

# Empty parties list - violates min_length=1, and is fixable by re-reading.
INVALID_JSON = json.dumps(
    {
        "parties": [],
        "key_dates": [
            {"label": "effective_date", "value": "2026-01-15", "confidence": 1.0}
        ],
        "payment_terms": [],
        "payment_terms_confidence": 1.0,
    }
)

# A prose date where a calendar date is required - the case the retry exists for.
PROSE_DATE_JSON = json.dumps(
    {
        "parties": [{"name": "Northwind Logistics Ltd.", "confidence": 1.0}],
        "key_dates": [
            {
                "label": "effective_date",
                "value": "thirty days after signing",
                "confidence": 0.5,
            }
        ],
        "payment_terms": [],
        "payment_terms_confidence": 0.5,
    }
)


class FakeGenerator:
    """Returns canned responses in order, recording the prompts it was given."""

    def __init__(self, *responses: str):
        self.responses = list(responses)
        self.prompts: list[str] = []

    def __call__(self, prompt: str) -> str:
        self.prompts.append(prompt)
        return self.responses[min(len(self.prompts) - 1, len(self.responses) - 1)]


def with_generator(fake: FakeGenerator):
    """Swap extraction._generate for the duration of a call."""

    class Swap:
        def __enter__(self):
            self.original = extraction._generate
            extraction._generate = fake
            return fake

        def __exit__(self, *exc):
            extraction._generate = self.original

    return Swap()


# ------------------------------------------------------------------- pdf tests ---


def test_pdf_text_is_extracted():
    text = pdf_to_text(make_pdf(CONTRACT_LINES))
    assert "SUPPLY AGREEMENT" in text
    assert "Northwind Logistics Ltd." in text
    assert "net 30 days" in text


def test_pdf_without_a_text_layer_is_rejected():
    """A scan has pages but no characters. It needs OCR, which this service does not
    do, so it must fail with that reason rather than be sent to the model."""
    try:
        pdf_to_text(make_pdf([]))
    except DocumentError as exc:
        assert exc.reason == "no_text_layer", exc.reason
    else:
        raise AssertionError("expected DocumentError")


def test_a_file_that_is_not_a_pdf_is_rejected():
    try:
        pdf_to_text(b"this is plainly not a PDF")
    except DocumentError as exc:
        assert exc.reason == "unreadable_pdf", exc.reason
    else:
        raise AssertionError("expected DocumentError")


# ----------------------------------------------------------------- retry tests ---


def test_valid_first_response_makes_exactly_one_call():
    """The retry must cost nothing when nothing is wrong."""
    fake = FakeGenerator(VALID_JSON)
    with with_generator(fake):
        result = extract_contract("some contract text")
    assert isinstance(result, ExtractedContract)
    assert len(fake.prompts) == 1


def test_malformed_output_is_retried_and_the_retry_succeeds():
    fake = FakeGenerator(INVALID_JSON, VALID_JSON)
    with with_generator(fake):
        result = extract_contract("some contract text")
    assert result.parties[0].name == "Northwind Logistics Ltd."
    assert len(fake.prompts) == 2


def test_the_repair_prompt_carries_the_actual_validation_error():
    """Feeding back a generic 'try again' is the thing this loop exists not to do."""
    fake = FakeGenerator(PROSE_DATE_JSON, VALID_JSON)
    with with_generator(fake):
        extract_contract("some contract text")
    repair = fake.prompts[1]
    assert "key_dates.0.value" in repair
    assert "valid date" in repair
    assert "thirty days after signing" in repair  # the model's own output, quoted back


def test_unparseable_json_is_retried_too():
    """Pydantic reports malformed JSON as a validation error, so it takes the same
    feedback path as a schema violation rather than crashing a parser."""
    fake = FakeGenerator("{ this is not json", VALID_JSON)
    with with_generator(fake):
        result = extract_contract("some contract text")
    assert isinstance(result, ExtractedContract)
    assert "Invalid JSON" in fake.prompts[1]


def test_a_genuinely_unfixable_case_raises_structured_detail():
    """The 422 body is built from this exception, so it must carry enough to explain
    the failure without a stack trace."""
    fake = FakeGenerator(INVALID_JSON, INVALID_JSON)
    try:
        with with_generator(fake):
            extract_contract("some contract text")
    except ExtractionError as exc:
        assert exc.attempts == 2
        assert exc.errors and exc.errors[0]["loc"] == ["parties"]
        assert exc.raw
        assert len(fake.prompts) == 2
    else:
        raise AssertionError("expected ExtractionError")


def test_retries_are_bounded():
    """Unbounded retrying on a document the model cannot satisfy is a cost bug."""
    fake = FakeGenerator(INVALID_JSON)
    try:
        with with_generator(fake):
            extract_contract("some contract text", max_attempts=3)
    except ExtractionError:
        pass
    assert len(fake.prompts) == 3


# -------------------------------------------------------------- pipeline tests ---


def test_pipeline_runs_pdf_through_to_cross_checked_result():
    """End to end with both model calls stubbed: PDF -> text -> extract -> cross-check."""
    import confidence
    import pipeline
    from confidence import SecondPass

    canned_second = SecondPass.model_validate(
        {
            "party_names_as_printed": ["Northwind Logistics Ltd."],
            "key_dates": [
                {
                    "label": "effective_date",
                    "value": "2026-01-15",
                    "as_printed": "15 January 2026",
                }
            ],
            "payment_figures": {"net_days": 30},
            "renewal_date": None,
        }
    )
    original_second = confidence.second_pass
    confidence.second_pass = lambda text: canned_second
    try:
        with with_generator(FakeGenerator(VALID_JSON)):
            result = pipeline.process_pdf(make_pdf(CONTRACT_LINES))
    finally:
        confidence.second_pass = original_second

    assert result.contract.parties[0].name == "Northwind Logistics Ltd."
    assert result.characters > 50
    assert all(f.outcome == "agree" for f in result.findings)
    assert result.lowered_fields == []
    # The pre-cross-check result is retained for the request log.
    assert result.contract_before_cross_check.parties[0].confidence == 1.0


# ---------------------------------------------------------------------- runner ---


def main() -> int:
    tests = [(n, f) for n, f in sorted(globals().items()) if n.startswith("test_")]
    failed = []
    for name, fn in tests:
        try:
            fn()
            print(f"  PASS  {name}")
        except Exception:
            failed.append(name)
            print(f"  FAIL  {name}")
            traceback.print_exc()
    print(f"\n{len(tests) - len(failed)}/{len(tests)} passed")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
