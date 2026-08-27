"""The public API.

Route naming and status codes are the contract here, since the consumer is another
team's codebase rather than a person who can ask what a response meant. Each code is a
promise: 200 the extraction ran and the body is a full result, 401 the key was missing
or wrong, 413 the upload was too large to accept, 422 the request was understood but
the document could not be turned into a valid result, 429 slow down, 500 a bug on our
side and never a leaked stack trace.

Everything under /v1/. A breaking change to the schema goes out as /v2/ and leaves
existing integrations working, which is the entire reason the prefix is there on day
one rather than added when it is already too late.
"""

import logging
import os
import time
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, File, Request, UploadFile, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field

import config
import requestlog
import usage
from auth import require_api_key
from confidence import Finding
from documents import DocumentError
from extraction import ExtractionError
from models import ExtractedContract
from pipeline import process_pdf
from ratelimit import limiter

logger = logging.getLogger("docintel.api")

ENDPOINT = "/v1/extract"

# Contracts are text, not media. Anything past this is either not a contract or is a
# scan we cannot read anyway, and reading it into memory first to find that out is how
# a service gets taken down by a single upload.
MAX_UPLOAD_BYTES = int(os.environ.get("DOCINTEL_MAX_UPLOAD_BYTES", 10 * 1024 * 1024))


# ------------------------------------------------------------------- responses ---


class RequestMeta(BaseModel):
    """What this request cost and how long it took.

    Returned to the caller, not just logged: an integrator sizing their own batch job
    should not have to ask us what a document costs.
    """

    model_config = ConfigDict(extra="forbid")

    latency_ms: int = Field(description="Wall-clock time for the whole request.")
    model_calls: int = Field(
        description="Model calls made. Two is the baseline - one extraction, one "
        "cross-check; three means the retry fired."
    )
    prompt_tokens: int
    output_tokens: int
    cost_usd: float | None = Field(
        description="Cost in USD, or null when the service has no pricing configured."
    )
    document_chars: int = Field(description="Characters of text extracted from the PDF.")


class ExtractResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    contract: ExtractedContract = Field(
        description="The extracted contract, with confidence adjusted by the cross-check."
    )
    cross_check: list[Finding] = Field(
        description="What the independent second pass found, field by field. A "
        "confidence_after below confidence_before means the two passes disagreed."
    )
    meta: RequestMeta


class ErrorResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    error: str = Field(description="Stable machine-readable code.")
    detail: str = Field(description="Human-readable explanation.")
    reason: str | None = Field(
        default=None, description="Sub-code for 422s: why the document failed."
    )
    validation_errors: list[dict] | None = Field(
        default=None,
        description="For a 422 after failed extraction: what the schema objected to.",
    )


ERROR_RESPONSES = {
    401: {"model": ErrorResponse, "description": "Missing or invalid API key."},
    413: {"model": ErrorResponse, "description": "Upload too large."},
    422: {"model": ErrorResponse, "description": "Document could not be extracted."},
    429: {"model": ErrorResponse, "description": "Rate limit exceeded."},
}


# ------------------------------------------------------------------------- app ---


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Before anything serves a request. Auth, rate limits and pricing all read
    # os.environ directly, and get_client() loading .env lazily would leave them
    # reading an empty environment until the first model call - by which point the
    # auth check they configure has already run.
    config.load_env()
    requestlog.init()
    yield


app = FastAPI(
    title="Document Intelligence API",
    version="1.0.0",
    lifespan=lifespan,
    description=(
        "POST a contract PDF, get back typed JSON with a confidence score per field.\n\n"
        "Authenticate with an `X-API-Key` header. Confidence is scored on four bands "
        "(1.0 / 0.8 / 0.5 / 0.2) by the extraction pass, then lowered wherever an "
        "independent second pass disagrees.\n\n"
        "**Confidence is not a correctness guarantee.** It detects unverified rewriting "
        "and values only one pass could see. Two passes reading the same damaged text "
        "can share a misreading and agree, so a high score means 'nothing contradicted "
        "this', not 'this was verified'."
    ),
)


def _error(status_code: int, payload: dict, headers: dict | None = None) -> JSONResponse:
    return JSONResponse(status_code=status_code, content=payload, headers=headers or {})


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    """A consistent JSON 500 instead of FastAPI's plain-text one.

    The traceback goes to the server log only. The response carries no exception type
    or message: those leak file paths, model names and library internals to whoever is
    calling.
    """
    logger.exception("Unhandled exception on %s %s", request.method, request.url.path)
    return _error(
        500,
        {
            "error": "internal_error",
            "detail": "An internal error occurred while processing the request.",
        },
    )


@app.get("/health", tags=["operations"], summary="Liveness check")
def health():
    return {"status": "ok"}


@app.post(
    ENDPOINT,
    response_model=ExtractResponse,
    responses=ERROR_RESPONSES,
    tags=["extraction"],
    summary="Extract structured data from a contract PDF",
)
def extract(
    file: UploadFile = File(description="The contract, as a PDF."),
    client: str = Depends(require_api_key),
):
    allowed, retry_after = limiter.check(client)
    if not allowed:
        # Logged, because a client hitting the limit is exactly the operational fact
        # the request log exists to surface. No model call was made, so it cost nothing.
        requestlog.log_request(
            client=client, endpoint=ENDPOINT, status_code=429, latency_ms=0,
            error_kind="rate_limited", filename=file.filename,
        )
        return _error(
            status.HTTP_429_TOO_MANY_REQUESTS,
            {
                "error": "rate_limited",
                "detail": (
                    f"Limit of {limiter.limit} requests per minute exceeded. "
                    f"Retry in {retry_after}s."
                ),
            },
            headers={"Retry-After": str(retry_after)},
        )

    started = time.perf_counter()

    def elapsed_ms() -> int:
        return int((time.perf_counter() - started) * 1000)

    payload = file.file.read(MAX_UPLOAD_BYTES + 1)
    if len(payload) > MAX_UPLOAD_BYTES:
        requestlog.log_request(
            client=client, endpoint=ENDPOINT, status_code=413,
            latency_ms=elapsed_ms(), error_kind="upload_too_large",
            filename=file.filename,
        )
        return _error(
            status.HTTP_413_CONTENT_TOO_LARGE,
            {
                "error": "upload_too_large",
                "detail": f"The upload exceeds the {MAX_UPLOAD_BYTES} byte limit.",
            },
        )

    # The collect() block spans the failures too: a 422 still made model calls, and a
    # cost figure that counted only successes would understate what this actually costs
    # to run.
    with usage.collect() as spent:
        try:
            result = process_pdf(payload)
        except DocumentError as exc:
            requestlog.log_request(
                client=client, endpoint=ENDPOINT, status_code=422,
                latency_ms=elapsed_ms(), model_calls=spent.calls,
                prompt_tokens=spent.prompt_tokens, output_tokens=spent.output_tokens,
                cost_usd=spent.cost_usd, error_kind=exc.reason, filename=file.filename,
            )
            return _error(
                status.HTTP_422_UNPROCESSABLE_CONTENT,
                {"error": "document_error", "detail": str(exc), "reason": exc.reason},
            )
        except ExtractionError as exc:
            logger.warning(
                "Extraction failed for %s after %d attempts", file.filename, exc.attempts
            )
            requestlog.log_request(
                client=client, endpoint=ENDPOINT, status_code=422,
                latency_ms=elapsed_ms(), model_calls=spent.calls,
                prompt_tokens=spent.prompt_tokens, output_tokens=spent.output_tokens,
                cost_usd=spent.cost_usd, error_kind="schema_validation_failed",
                filename=file.filename,
            )
            return _error(
                status.HTTP_422_UNPROCESSABLE_CONTENT,
                {
                    "error": "extraction_failed",
                    "detail": str(exc),
                    "reason": "schema_validation_failed",
                    "validation_errors": exc.errors,
                },
            )

        latency = elapsed_ms()
        requestlog.log_request(
            client=client, endpoint=ENDPOINT, status_code=200, latency_ms=latency,
            model_calls=spent.calls, prompt_tokens=spent.prompt_tokens,
            output_tokens=spent.output_tokens, cost_usd=spent.cost_usd,
            document_chars=result.characters,
            fields_lowered=len(result.lowered_fields), filename=file.filename,
        )
        return ExtractResponse(
            contract=result.contract,
            cross_check=result.findings,
            meta=RequestMeta(
                latency_ms=latency,
                model_calls=spent.calls,
                prompt_tokens=spent.prompt_tokens,
                output_tokens=spent.output_tokens,
                cost_usd=spent.cost_usd,
                document_chars=result.characters,
            ),
        )
