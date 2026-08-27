"""Tests for auth, rate limiting, request logging and the /v1/extract contract.

Offline: the model calls are stubbed, so this asserts the API's promises - which status
code means what, what the log records - rather than anything about extraction quality.
Those promises are what an integrating team builds against, so they are the ones that
must not drift silently.

Run directly:  python test_api.py
"""

import os
import pathlib
import sys
import tempfile
import traceback

# Auth reads this per call, but set it before the app imports anything that caches.
os.environ["DOCINTEL_API_KEYS"] = "procurement:sk_test_valid,internal:sk_test_other"
os.environ.setdefault("DOCINTEL_RATE_LIMIT_PER_MINUTE", "10")

from fastapi.testclient import TestClient  # noqa: E402

import confidence  # noqa: E402
import extraction  # noqa: E402
import requestlog  # noqa: E402
import usage  # noqa: E402
from api import MAX_UPLOAD_BYTES, app  # noqa: E402
from ratelimit import RateLimiter, limiter  # noqa: E402
from test_extraction import (  # noqa: E402
    CONTRACT_LINES,
    VALID_JSON,
    FakeGenerator,
    make_pdf,
    with_generator,
)

VALID_KEY = "sk_test_valid"
HEADERS = {"X-API-Key": VALID_KEY}

CANNED_SECOND_PASS = {
    "party_names_as_printed": ["Northwind Logistics Ltd."],
    "key_dates": [
        {"label": "effective_date", "value": "2026-01-15", "as_printed": "15 January 2026"}
    ],
    "payment_figures": {"net_days": 30},
    "renewal_date": None,
}


class Stubs:
    """Stub both model calls and point the request log at a throwaway database."""

    def __init__(self, generator=None):
        self.generator = generator or FakeGenerator(VALID_JSON)

    def __enter__(self):
        self._tmp = tempfile.TemporaryDirectory()
        self._db = requestlog.DB_PATH
        requestlog.DB_PATH = pathlib.Path(self._tmp.name) / "requests.db"
        requestlog.init()

        self._second = confidence.second_pass
        confidence.second_pass = lambda text: confidence.SecondPass.model_validate(
            CANNED_SECOND_PASS
        )
        self._generate = extraction._generate
        extraction._generate = self.generator
        limiter.reset()
        return self

    def __exit__(self, *exc):
        confidence.second_pass = self._second
        extraction._generate = self._generate
        requestlog.DB_PATH = self._db
        self._tmp.cleanup()
        limiter.reset()


def pdf_upload():
    return {"file": ("contract.pdf", make_pdf(CONTRACT_LINES), "application/pdf")}


# ------------------------------------------------------------------------ auth ---


def test_missing_api_key_is_rejected():
    with Stubs():
        response = TestClient(app).post("/v1/extract", files=pdf_upload())
    assert response.status_code == 401
    assert response.json()["detail"]["error"] == "unauthorized"


def test_wrong_api_key_is_rejected():
    with Stubs():
        response = TestClient(app).post(
            "/v1/extract", files=pdf_upload(), headers={"X-API-Key": "sk_test_wrong"}
        )
    assert response.status_code == 401


def test_a_service_with_no_keys_configured_rejects_everything():
    """The safe failure. An unconfigured service that accepted all callers would be an
    open, billable endpoint."""
    original = os.environ["DOCINTEL_API_KEYS"]
    os.environ["DOCINTEL_API_KEYS"] = ""
    try:
        with Stubs():
            response = TestClient(app).post(
                "/v1/extract", files=pdf_upload(), headers=HEADERS
            )
    finally:
        os.environ["DOCINTEL_API_KEYS"] = original
    assert response.status_code == 401


def test_error_bodies_never_echo_the_key():
    with Stubs():
        response = TestClient(app).post(
            "/v1/extract", files=pdf_upload(), headers={"X-API-Key": "sk_test_wrong"}
        )
    assert "sk_test_wrong" not in response.text
    assert VALID_KEY not in response.text


# ----------------------------------------------------------------- happy path ---


def test_valid_request_returns_contract_findings_and_meta():
    with Stubs():
        response = TestClient(app).post(
            "/v1/extract", files=pdf_upload(), headers=HEADERS
        )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["contract"]["parties"][0]["name"] == "Northwind Logistics Ltd."
    assert [f["outcome"] for f in body["cross_check"]]
    assert body["meta"]["latency_ms"] >= 0
    assert body["meta"]["document_chars"] > 50


# ---------------------------------------------------------------- rate limits ---


def test_rate_limit_returns_429_with_retry_after():
    with Stubs():
        client = TestClient(app)
        limiter._limit = 2
        try:
            codes = [
                client.post("/v1/extract", files=pdf_upload(), headers=HEADERS).status_code
                for _ in range(3)
            ]
            last = client.post("/v1/extract", files=pdf_upload(), headers=HEADERS)
        finally:
            limiter._limit = None
    assert codes[:2] == [200, 200]
    assert codes[2] == 429
    assert last.headers.get("Retry-After")
    assert last.json()["error"] == "rate_limited"


def test_rate_limit_is_per_client():
    """One client exhausting its quota must not lock out another."""
    with Stubs():
        client = TestClient(app)
        limiter._limit = 1
        try:
            first = client.post("/v1/extract", files=pdf_upload(), headers=HEADERS)
            blocked = client.post("/v1/extract", files=pdf_upload(), headers=HEADERS)
            other = client.post(
                "/v1/extract",
                files=pdf_upload(),
                headers={"X-API-Key": "sk_test_other"},
            )
        finally:
            limiter._limit = None
    assert (first.status_code, blocked.status_code, other.status_code) == (200, 429, 200)


def test_rejected_requests_do_not_extend_the_lockout():
    """Counting rejections would push the window forward on every retry, turning a
    rate limit into a ban."""
    limiter_ = RateLimiter(limit=2, window=60)
    assert limiter_.check("c", now=0.0)[0]
    assert limiter_.check("c", now=1.0)[0]
    assert not limiter_.check("c", now=2.0)[0]
    assert not limiter_.check("c", now=3.0)[0]
    # The window still expires relative to the first ACCEPTED hit, not the last refusal.
    assert limiter_.check("c", now=61.0)[0]


def test_window_slides_rather_than_resetting_on_the_minute():
    limiter_ = RateLimiter(limit=2, window=60)
    limiter_.check("c", now=0.0)
    limiter_.check("c", now=59.0)
    assert not limiter_.check("c", now=59.5)[0]
    # 0.0 has aged out; 59.0 has not, so exactly one slot frees up.
    assert limiter_.check("c", now=60.5)[0]
    assert not limiter_.check("c", now=60.6)[0]


# --------------------------------------------------------------------- errors ---


def test_a_file_that_is_not_a_pdf_is_a_422_with_a_reason():
    with Stubs():
        response = TestClient(app).post(
            "/v1/extract",
            files={"file": ("notes.txt", b"just some text", "text/plain")},
            headers=HEADERS,
        )
    assert response.status_code == 422
    assert response.json()["reason"] == "unreadable_pdf"


def test_a_scan_with_no_text_layer_is_a_422_with_its_own_reason():
    with Stubs():
        response = TestClient(app).post(
            "/v1/extract",
            files={"file": ("scan.pdf", make_pdf([]), "application/pdf")},
            headers=HEADERS,
        )
    assert response.status_code == 422
    assert response.json()["reason"] == "no_text_layer"


def test_unfixable_model_output_is_a_422_carrying_the_validation_errors():
    """Never a raw crash - the client gets a structured explanation of what failed."""
    bad = '{"parties": [], "payment_terms": [], "payment_terms_confidence": 1.0}'
    with Stubs(generator=FakeGenerator(bad, bad)):
        response = TestClient(app).post(
            "/v1/extract", files=pdf_upload(), headers=HEADERS
        )
    assert response.status_code == 422
    body = response.json()
    assert body["error"] == "extraction_failed"
    assert body["validation_errors"][0]["loc"] == ["parties"]


def test_an_oversized_upload_is_refused_before_extraction():
    with Stubs():
        response = TestClient(app).post(
            "/v1/extract",
            files={"file": ("big.pdf", b"x" * (MAX_UPLOAD_BYTES + 10), "application/pdf")},
            headers=HEADERS,
        )
    assert response.status_code == 413
    assert response.json()["error"] == "upload_too_large"


# ---------------------------------------------------------------------- logging ---


def test_a_successful_request_is_logged_with_latency_and_client():
    with Stubs():
        TestClient(app).post("/v1/extract", files=pdf_upload(), headers=HEADERS)
        rows = requestlog.recent()
    assert len(rows) == 1
    row = rows[0]
    assert row["client"] == "procurement"
    assert row["status_code"] == 200
    assert row["endpoint"] == "/v1/extract"
    assert row["latency_ms"] >= 0
    assert row["document_chars"] > 50
    assert row["filename"] == "contract.pdf"


def test_failures_are_logged_too():
    """A 422 still burned model calls; a cost figure counting only successes would
    understate what the service costs to run."""
    with Stubs():
        TestClient(app).post(
            "/v1/extract",
            files={"file": ("notes.txt", b"not a pdf", "text/plain")},
            headers=HEADERS,
        )
        rows = requestlog.recent()
    assert len(rows) == 1
    assert rows[0]["status_code"] == 422
    assert rows[0]["error_kind"] == "unreadable_pdf"


def test_rate_limited_requests_are_logged():
    with Stubs():
        client = TestClient(app)
        limiter._limit = 1
        try:
            client.post("/v1/extract", files=pdf_upload(), headers=HEADERS)
            client.post("/v1/extract", files=pdf_upload(), headers=HEADERS)
        finally:
            limiter._limit = None
        rows = requestlog.recent()
    assert [r["status_code"] for r in rows] == [429, 200]
    assert rows[0]["error_kind"] == "rate_limited"


def test_summary_aggregates_latency_and_retries():
    with Stubs():
        client = TestClient(app)
        for _ in range(3):
            client.post("/v1/extract", files=pdf_upload(), headers=HEADERS)
        report = requestlog.summary()
    assert report["requests"] == 3
    assert report["succeeded"] == 3
    assert report["p95_latency_ms"] is not None
    assert report["p50_latency_ms"] is not None


def test_logging_failure_does_not_break_the_response():
    """The client's result is already computed and paid for; a dropped metric row is a
    better outcome than a dropped response."""
    with Stubs():
        broken = pathlib.Path("/nonexistent-dir-xyz/requests.db")
        original = requestlog.DB_PATH
        requestlog.DB_PATH = broken
        try:
            response = TestClient(app).post(
                "/v1/extract", files=pdf_upload(), headers=HEADERS
            )
        finally:
            requestlog.DB_PATH = original
    assert response.status_code == 200


# ----------------------------------------------------------------------- usage ---


class FakeResponse:
    class usage_metadata:  # noqa: N801 - mirrors the SDK's attribute name
        prompt_token_count = 120
        candidates_token_count = 300


def test_usage_accumulates_across_every_model_call():
    with usage.collect() as spent:
        usage.record(FakeResponse())
        usage.record(FakeResponse())
    assert spent.calls == 2
    assert spent.prompt_tokens == 240
    assert spent.output_tokens == 600
    assert spent.total_tokens == 840


def test_cost_is_none_until_rates_are_configured():
    """A plausible-looking cost that was never checked is worse than no cost: it would
    be wrong silently, and it would be wrong in the README."""
    for var in ("DOCINTEL_PRICE_INPUT_PER_MTOK", "DOCINTEL_PRICE_OUTPUT_PER_MTOK"):
        os.environ.pop(var, None)
    with usage.collect() as spent:
        usage.record(FakeResponse())
    assert spent.cost_usd is None


def test_cost_is_computed_when_rates_are_configured():
    os.environ["DOCINTEL_PRICE_INPUT_PER_MTOK"] = "0.10"
    os.environ["DOCINTEL_PRICE_OUTPUT_PER_MTOK"] = "0.40"
    try:
        with usage.collect() as spent:
            usage.record(FakeResponse())
        # 120 * 0.10/1e6 + 300 * 0.40/1e6
        assert abs(spent.cost_usd - (0.000012 + 0.00012)) < 1e-12
    finally:
        for var in ("DOCINTEL_PRICE_INPUT_PER_MTOK", "DOCINTEL_PRICE_OUTPUT_PER_MTOK"):
            os.environ.pop(var, None)


def test_recording_outside_a_collect_block_is_a_no_op():
    """The extraction functions stay callable from a script or a test with no request
    context to record into."""
    usage.record(FakeResponse())


# ---------------------------------------------------------------------- openapi ---


def test_openapi_documents_the_versioned_route_and_its_errors():
    spec = app.openapi()
    assert "/v1/extract" in spec["paths"]
    responses = spec["paths"]["/v1/extract"]["post"]["responses"]
    for code in ("200", "401", "413", "422", "429"):
        assert code in responses, code


# ----------------------------------------------------------------------- runner ---


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
