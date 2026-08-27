"""The whole extraction path, composed: PDF -> text -> extract (+retry) -> cross-check.

Kept separate from the FastAPI route so the pipeline can be run and tested without a
web server, and so Phase 4's route stays what it should be - auth, rate limiting,
status codes - rather than business logic wearing a decorator.
"""

import pathlib
import time

from pydantic import BaseModel, ConfigDict

from confidence import Finding, verify
from documents import pdf_to_text
from extraction import extract_contract
from models import ExtractedContract


class ExtractionResult(BaseModel):
    """Everything one document produced, including how it was arrived at.

    The pre-cross-check contract is kept alongside the adjusted one because the
    request log and the admin page need to show what the second pass actually changed;
    a findings list without the original leaves that unanswerable.
    """

    model_config = ConfigDict(extra="forbid")

    contract: ExtractedContract
    contract_before_cross_check: ExtractedContract
    findings: list[Finding]
    characters: int
    elapsed_ms: int

    @property
    def lowered_fields(self) -> list[Finding]:
        return [f for f in self.findings if f.lowered]


def process_text(text: str) -> ExtractionResult:
    """Extract and cross-check already-extracted text."""
    started = time.perf_counter()
    extracted = extract_contract(text)
    adjusted, findings = verify(text, extracted)
    return ExtractionResult(
        contract=adjusted,
        contract_before_cross_check=extracted,
        findings=findings,
        characters=len(text),
        elapsed_ms=int((time.perf_counter() - started) * 1000),
    )


def process_pdf(source: str | pathlib.Path | bytes) -> ExtractionResult:
    """Full path from an uploaded PDF to a cross-checked contract.

    DocumentError and ExtractionError are allowed to propagate: both already carry the
    structured detail the 422 handler needs, and flattening them into a generic failure
    here would throw that away.
    """
    return process_text(pdf_to_text(source))
