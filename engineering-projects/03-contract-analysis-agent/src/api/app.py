"""FastAPI app: POST /v1/analyze (PDF upload) -> clause verdicts + memo,
GET /v1/health. API-key auth via src/api/auth.py (pattern from the
sibling Document Intelligence project).
"""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

from fastapi import Depends, FastAPI, HTTPException, UploadFile, File, status
from fastapi.responses import JSONResponse

_API_DIR = Path(__file__).resolve().parent
_SRC = _API_DIR.parent
for p in (str(_API_DIR), str(_SRC), str(_SRC / "llm")):
    if p not in sys.path:
        sys.path.insert(0, p)

from auth import require_api_key  # noqa: E402
from extract import extract_pdf_text  # noqa: E402
import pipeline  # noqa: E402
import memo as memo_mod  # noqa: E402
from provider import get_provider, QuotaExceededError  # noqa: E402

MAX_UPLOAD_BYTES = 20 * 1024 * 1024  # 20MB

app = FastAPI(
    title="Contract Analysis Agent",
    description="Clause segmentation, classification, rule-based verdicts, and review memos for contracts.",
    version="0.1.0",
)


def _error(status_code: int, payload: dict) -> JSONResponse:
    return JSONResponse(status_code=status_code, content=payload)


@app.exception_handler(Exception)
def _unhandled_exception(request, exc: Exception):
    return _error(status.HTTP_500_INTERNAL_SERVER_ERROR, {"error": "internal_error", "detail": str(exc)})


@app.get("/v1/health", tags=["operations"], summary="Liveness check")
def health():
    return {"status": "ok"}


@app.post("/v1/analyze", tags=["analysis"], summary="Analyze a contract PDF")
def analyze(
    file: UploadFile = File(description="The contract, as a PDF."),
    client: str = Depends(require_api_key),
):
    payload = file.file.read(MAX_UPLOAD_BYTES + 1)
    if len(payload) > MAX_UPLOAD_BYTES:
        return _error(status.HTTP_413_CONTENT_TOO_LARGE,
                      {"error": "upload_too_large", "detail": f"The upload exceeds the {MAX_UPLOAD_BYTES} byte limit."})
    if not payload:
        return _error(422,
                      {"error": "empty_upload", "detail": "The uploaded file is empty."})

    with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
        tmp.write(payload)
        tmp_path = tmp.name

    try:
        text = extract_pdf_text(tmp_path)
    except Exception as e:
        return _error(422,
                      {"error": "extraction_failed", "detail": f"Could not extract text from PDF: {e}"})
    finally:
        try:
            Path(tmp_path).unlink()
        except OSError:
            pass

    if not text.strip():
        return _error(422,
                       {"error": "empty_document", "detail": "No extractable text found in the PDF."})

    try:
        provider = get_provider()
        result = pipeline.analyze_contract(text, provider)
    except QuotaExceededError as e:
        return _error(status.HTTP_503_SERVICE_UNAVAILABLE,
                      {"error": "quota_exceeded", "detail": str(e)})
    except Exception as e:
        return _error(status.HTTP_502_BAD_GATEWAY,
                      {"error": "analysis_failed", "detail": str(e)})

    rule_results = [
        {"rule_id": r.rule_id, "clause_type": r.clause_type, "verdict": r.verdict.value, "reason": r.reason}
        for r in result["rule_results"]
    ]
    memo_json = memo_mod.render_json(file.filename or "uploaded_contract.pdf", result["memo_findings"])

    return {
        "filename": file.filename,
        "clause_count": len(result["leaves"]),
        "rule_verdicts": rule_results,
        "memo": memo_json,
    }
