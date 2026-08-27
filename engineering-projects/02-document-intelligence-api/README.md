# Document Intelligence API

POST a contract PDF, get back typed JSON with a confidence score per field.

## Problem

A procurement team, in their words:

> "Give us one endpoint. We POST a contract or purchase order, we get back clean JSON,
> parties, dates, payment terms, penalty clauses, renewal dates, with a confidence score
> per field. Our engineers will integrate it, so give us a spec they can build against
> tomorrow."

The deliverable is not a demo. It is a contract other software depends on, which is why
the schema came first and the status codes are treated as promises rather than
decoration.

## Results

| | |
|---|---|
| Cost per document | **$0.00077** short agreement · **$0.00124** longer multi-party MSA (~$0.001 mean, ≈995 documents per dollar) |
| Latency | 4.9 s short · 18.5 s longer, over two model calls |
| Tokens | 432 + 441 short · 756 + 701 longer |
| Retry rate | 0 of 12 live extractions needed one |
| Tests | 55, all offline, no API key required |

Measured at $0.25 / $1.50 per million input / output tokens. Output tokens are ~72% of
the bill on a short contract, so **schema verbosity drives cost more than document
length** — every `confidence` field and every `as_printed` string is a line item.

Latency percentiles come from `/admin`; the p95 above is two samples and is labelled as
such on the page rather than quoted as a real percentile.

## Architecture

```
POST /v1/extract  (PDF upload, X-API-Key header)
   │
   ├─ auth.py        API key → client name (constant-time compare)
   ├─ ratelimit.py   sliding window per client
   ├─ documents.py   pdfplumber: PDF → text  (no text layer → 422)
   │
   ├─ extraction.py  MAIN PASS
   │     Gemini structured output, schema-constrained
   │     confidence scored on four discrete bands
   │        ├─ validates → continue
   │        └─ fails → retry once with the actual Pydantic error in the prompt
   │              └─ fails again → 422 with structured detail, never a crash
   │
   ├─ confidence.py  SECOND PASS  (independent, verbatim, never sees pass 1)
   │     re-extracts the critical fields as printed
   │     disagreement lowers that field's confidence
   │
   └─ requestlog.py  SQLite: cost, latency, tokens, outcome — successes and failures
         │
         └─ GET /admin   Jinja2 page over the log
```

## Key decisions

### Schema: required vs optional is a product decision

A field is optional when the *concept* can be absent from a contract, not when
extraction happens to fail. `parties` requires at least one — a document binding nobody
is not a contract. `key_dates` requires none: a contract can express every date
relatively ("forty-five days from signing") and state no calendar date at all. That one
started as `min_length=1`, and the model responded by **inventing** an
`effective_date` to satisfy the schema. An honest empty list beats a plausible
invention.

`LabeledDate.value` is a strict `date`, so prose dates fail loudly — which is exactly
what the retry loop exists to catch.

### Confidence: four bands, because a continuous scale doesn't work

Measured, not assumed. Given a free float the model parks on one value regardless of
input quality. An anchored rubric only moved the pin from 1.00 to 0.95 — it scored a
clean contract and an OCR-mangled one identically. Five prompt strategies were tried:

| Strategy | Clean | Ambiguous | Degraded | Discriminates? |
|---|---|---|---|---|
| Baseline | 1.00 | 0.97 | 1.00 | no |
| Anchored rubric | 0.96 | 0.97 | 0.95 | no |
| Rubric + self-check | 0.95 | 0.96 | 0.95 | no |
| Evidence before score | 1.00 | 1.00 | 0.85 | no |
| Calibration reframe | 1.00 | 0.93 | 0.95 | no |
| **Discrete bands (1.0/0.8/0.5/0.2)** | **1.00** | **0.88** | **0.83** | **yes, 3/3 repeats** |

The fix was not better criteria. It was removing the value the model could hedge on.

### The second pass re-extracts rather than re-scores

A model asked to check its own answer agrees with it, so `second_pass()` takes the
document text and nothing else — enforced by its signature. It transcribes **verbatim**,
uncorrected. The main pass normalises, and silent normalisation is where its errors
hide, so comparing a normalised value against an as-printed one surfaces every place the
main pass changed something.

Critical fields are `parties`, `key_dates`, `payment_terms`, `renewal_date`.
`payment_terms` is compared **on meaning, not characters** — both passes reduce to
figures, so "Net 30" and "payment due within 30 days" agree. Numbers written as words
are read too; a digits-only matcher scored a false conflict on a correctly extracted
field in live testing.

Cross-check outcomes, on the same four-band ladder:

| Outcome | Cap | Meaning |
|---|---|---|
| `agree` | — | both passes match |
| `rewritten` | 0.5 | same value, different characters — the main pass normalised it |
| `missing` | 0.5 | the second pass did not report it |
| `conflict` | 0.2 | the two passes contradict each other |
| `omitted` | — | the main pass reported nothing where the second pass found something |

It **only ever lowers**. Agreement is not positive evidence.

### API keys, limits, cost

Auth is a header check with `secrets.compare_digest`; keys are configured as
`name:secret` so the log records *who* spent without storing the secret. No keys
configured rejects everything — an unconfigured billable endpoint that accepted all
callers is the worse failure.

Rate limiting is a sliding window, not a fixed one: a fixed window lets a caller fire a
full quota either side of the boundary and get double the intended rate exactly when the
limit should bind. Rejected requests are not counted, so retrying does not extend the
lockout into a ban.

Pricing is read from the environment rather than hardcoded, and cost reports `null`
until it is set — tokens are recorded either way.

## Known limitations

**Confidence is not a correctness guarantee.** Two passes reading the same damaged text
can share a misreading and agree. On an OCR-damaged fixture both passes read "Acrne" for
"Acme", agreed, and the wrong value kept a high score — while the party the main pass
had repaired *correctly* was flagged, because flagging is what a rewrite earns. On a
badly damaged document the signal can be **anti-correlated with correctness** at the
level of an individual field. It detects unverified rewriting and one-pass-only values.
It is not an oracle, and a high score means "nothing contradicted this".

**No OCR.** A scanned PDF with no text layer is refused with `reason: no_text_layer`
rather than guessed at.

**Rate limiting is in-process.** Counters live in one worker, reset on restart, and are
not shared between replicas. Accurate for a single Render service; more instances
silently multiply the limit. Redis beyond that.

**The request log is ephemeral.** SQLite on Render's default filesystem resets when the
instance restarts. It is an operational view, not a system of record.

**Spelled-out numbers stop at ninety-nine.** Beyond that contracts use digits and the
parsing gets ambiguous.

**The admin key can travel in a query string**, because a browser cannot set a header.
Query strings land in history and proxy logs, which is why it is a separate low-value
secret that cannot spend money.

**The container has never been built locally.** Docker Desktop is not viable on the
development machine — diagnosed, not assumed: BIOS virtualization, firmware, WSL2
prerequisites and the daemon's backend config all check out, plus a RAM constraint that
would bite regardless. Render builds the image server-side.

## How to run

### Locally

```bash
python -m venv venv && venv/Scripts/pip install -r requirements.txt
cp .env.example .env        # then fill in GEMINI_API_KEY and DOCINTEL_API_KEYS
venv/Scripts/uvicorn api:app --reload
```

### Docker

```bash
docker build -t docintel .
docker run -p 8000:8000 --env-file .env docintel
```

`PORT` is honoured when set and defaults to 8000, so the same image runs locally and on
Render unchanged.

### Deploying to Render

New Web Service → Docker → point at this repo. Set `GEMINI_API_KEY`,
`DOCINTEL_API_KEYS`, the two `DOCINTEL_PRICE_*` values and `DOCINTEL_ADMIN_KEY` in the
dashboard. Do not commit them; `.env` is gitignored.

### Quickstart

```bash
curl -X POST http://localhost:8000/v1/extract \
  -H "X-API-Key: sk_live_your_key" \
  -F "file=@contract.pdf"
```

```json
{
  "contract": {
    "parties": [
      { "name": "Northwind Logistics Ltd.", "role": "supplier", "confidence": 1.0 },
      { "name": "Acme Procurement GmbH", "role": "buyer", "confidence": 1.0 }
    ],
    "key_dates": [
      { "label": "effective_date", "value": "2026-01-15", "confidence": 1.0 },
      { "label": "expiration_date", "value": "2028-01-14", "confidence": 1.0 }
    ],
    "payment_terms": ["Net 30 days from date of invoice", "2% discount within 10 days"],
    "payment_terms_confidence": 1.0,
    "penalty_clauses": [],
    "renewal_date": { "label": "renewal_date", "value": "2027-11-15", "confidence": 1.0 }
  },
  "cross_check": [
    {
      "field": "parties",
      "item": "Northwind Logistics Ltd.",
      "outcome": "agree",
      "confidence_before": 1.0,
      "confidence_after": 1.0
    }
  ],
  "meta": {
    "latency_ms": 4921,
    "model_calls": 2,
    "prompt_tokens": 512,
    "output_tokens": 491,
    "cost_usd": 0.00077,
    "document_chars": 363
  }
}
```

### Status codes

| Code | Meaning |
|---|---|
| 200 | Extracted. Body is a full result. |
| 401 | API key missing or invalid. |
| 413 | Upload above `DOCINTEL_MAX_UPLOAD_BYTES`. |
| 422 | Understood but unprocessable. `reason` says which: `unreadable_pdf`, `no_text_layer`, `schema_validation_failed` (with `validation_errors`). |
| 429 | Rate limited. `Retry-After` header included. |
| 500 | Our bug. Logged server-side; the body carries no internals. |

## API docs

- OpenAPI UI: `/docs` · raw spec: `/openapi.json`
- Operational view: `/admin?key=…` — cost per document, latency percentiles, retry
  count and the last 50 requests. Not in the OpenAPI spec: that document is the contract
  integrators build against, and a page they cannot open is noise in it.

## Tests

```bash
venv/Scripts/python test_confidence.py    # 21  cross-check comparison logic
venv/Scripts/python test_extraction.py    # 11  PDF handling + the retry loop
venv/Scripts/python test_api.py           # 23  auth, limits, status codes, logging
```

All offline — model calls are stubbed and PDF fixtures are assembled by hand, so no API
key is needed and nothing depends on the model behaving. Written as `test_*` functions,
so pytest collects them unchanged if it is ever added.

## Tools

FastAPI, Pydantic, Gemini structured outputs, pdfplumber, Jinja2, SQLite, Docker.

One implementation note worth carrying forward: Gemini's `response_schema` path returns
**400** for the `additionalProperties: false` that Pydantic's `extra="forbid"` emits.
`response_json_schema` accepts the strict model unchanged. Verified against the live
API — the SDK lets the value through on a truthiness check, so the failure only appears
at the server.
