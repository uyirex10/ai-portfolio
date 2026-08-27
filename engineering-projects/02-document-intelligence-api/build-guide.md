# Project 5 (E2): Document Intelligence API

**Track:** AI Engineering
**Estimated time:** ~2 weeks
**Position in roadmap:** A2's extraction experience, grown into a real product. First project where the consumer is another engineer, not an end user or a business owner.

---

## Client Brief

A procurement team.

> "Give us one endpoint. We POST a contract or purchase order, we get back clean JSON, parties, dates, payment terms, penalty clauses, renewal dates, with a confidence score per field. Our engineers will integrate it, so give us a spec they can build against tomorrow."

The deliverable isn't a working demo, it's a contract other software can depend on. That distinction shapes everything below.

---

## Before You Touch Code: Concepts

**REST API design (new).** Endpoints, status codes, versioning. The core discipline: a status code is a promise about what happened, 200 means it worked,
422 means the request was understood but the content was invalid, 401 means bad credentials, 429 means slow down. A route under `/v1/` means you can change the contract later under `/v2/` without breaking anyone already integrated against `/v1/`. This matters more here than in any prior project, since the actual customer is a stranger's codebase, not a person reading a Slack message.

**Pydantic as a contract (recognize from A2).** A2 validated extracted data by hand, a Code node checking line items against a stated total. Pydantic formalizes that same instinct into something enforced automatically: a typed schema that rejects anything that doesn't match, before your code ever has to think about it. Every field's type, and whether it's required or optional, is a decision with real consequences, an optional field the client actually needed breaks their integration silently, a required field that's sometimes genuinely absent breaks every document that doesn't have it.

**Structured outputs plus the retry loop (recognize from A3, extend).** A3's classifier already used schema-constrained generation. What's new here: when the model's output fails validation anyway, the fix isn't to fail immediately, it's to feed the actual validation error back into a retry prompt, bounded to one or two attempts, not unbounded. Malformed output becomes a handled case, not a crash.

**Per-field confidence, two passes (extends E1 and A3).** A single self-reported confidence score is only one signal. This project cross-checks critical fields with a second, cheaper pass, and when the two passes disagree, confidence drops. Same underlying principle as E1's reranking recovering chunking failures, and A3's confidence gate, a lone number is weaker evidence than two independent signals agreeing.

**Production wrapper (new).** API-key auth doesn't need to be complex, a header check against known keys is enough at this scale. Rate limiting protects you from cost blowup, not just abuse. Request logging with cost and latency per call is what turns "it works" into "I know what this costs to run," which the brief explicitly wants for pricing later.

**Docker (real, not deferred this time).** Image versus container, a Dockerfile, port mapping. If Docker Desktop is still unreliable on your machine, that needs a real resolution now, not another documented-and-abandoned attempt, since a working container is an explicit deliverable this time, not a nice-to-have.

**OpenAPI/Swagger.** FastAPI generates this automatically from your Pydantic models and route definitions. Your job is polishing it, descriptions, examples, not building it from scratch.

---

## Tools

Python, FastAPI, Pydantic, **Gemini structured outputs** (staying with Gemini rather than switching to Claude/GPT as the brief suggests, same reasoning as every prior project, it's the already-validated, already-free-tier stack, switching now adds cost and integration risk for no real gain), pdfplumber for PDF-to-text, Docker.

---

## Architecture

```
Client --> POST /v1/extract (PDF upload)
    --> API key check --> rate limit check
    --> pdfplumber: PDF -> raw text
    --> Gemini structured-output call, constrained to your Pydantic schema
    --> Pydantic validation
         PASS --> second cheap pass cross-checks critical fields
                  --> disagreement lowers confidence
                  --> log cost + latency
                  --> return 200, full JSON
         FAIL --> retry once, validation error fed back into the prompt
                  --> validate again
                       PASS --> continue as above
                       FAIL --> log it --> return 422 with structured
                                error detail, never a raw crash
    --> admin page: recent extractions, cost, latency, confidence summary,
        pulled from the request log
```

---

## Build It, Step by Step

**Phase 1: Schema first.** Define the Pydantic model, every field typed, every field's required-vs-optional status a deliberate call, a confidence float alongside each one. Decide which fields count as "critical" for the second-pass cross-check in Phase 3, this is genuinely yours to design, the brief says so directly.

**Schema decision, finalized:**

```
ExtractedContract
├── parties: list[Party]                    required, at least 1
│     Party: { name, role (optional), confidence }
├── key_dates: list[LabeledDate]             required, at least 1
│     LabeledDate: { label, value, confidence }
│     (e.g. "effective_date", "signing_date", "expiration_date")
├── payment_terms: list[str]                 required
├── penalty_clauses: list[PenaltyClause]     optional, defaults to []
│     PenaltyClause: { trigger, penalty, confidence }
└── renewal_date: Optional[date]             optional, single value, own confidence
```

Required vs optional decided by whether the concept can legitimately be absent from the document itself, not by whether extraction happened to succeed. A list field being "optional" means it can come back empty, not `None`.

**Phase 2: Extraction core.** pdfplumber for text extraction, a Gemini call with structured output enforcing your schema, a bounded retry (one or two attempts) that feeds the actual validation error back into the prompt on failure.

**Phase 3: Per-field confidence.** Self-scored confidence from the main pass, plus a second cheap pass that cross-checks your critical fields specifically. Disagreement between the two lowers confidence on that field.

**Phase 4: Production wrapper.** API-key auth, rate limiting, request logging (cost and latency per call), the versioned `/v1/extract` route.

**Phase 5: Ship like a product.** Dockerfile, polished OpenAPI docs, a README with a real `curl` quickstart, and the thin admin page, built as one more route inside the same FastAPI app (Jinja2 templates, plain HTML), not a separate service. Local Docker Desktop isn't viable on this machine, confirmed through a full diagnostic pass, BIOS, firmware, WSL2 prerequisites, Docker's own backend config, all clean, plus a real RAM constraint that would cause its own problems even if the error resolved. **Deploying to Render** instead, a single Dockerized web service, no local Docker build required, Render builds the image server-side from the Dockerfile in the repo. One real Dockerfile detail this decision changes: bind to the `PORT` environment variable Render injects, not a hardcoded port.

---

## What You Must Do Yourself

- Design the schema, every field decision is a product decision
- Decide which fields are "critical" enough to warrant the second-pass cross-check
- Test the retry loop by deliberately forcing malformed model output
- Track real cost per document, you'll use this number to quote clients later
- Resolve the Docker question for real this time

---

## Testing Checklist

- [ ] Clean, well-formed documents extract correctly with sensible confidence scores
- [ ] Deliberately malformed model output triggers the retry, and the retry actually succeeds when the underlying issue is fixable
- [ ] A genuinely unfixable case returns a clean 422 with structured error detail, never a crash
- [ ] Missing or wrong API key is rejected correctly
- [ ] Rate limiting actually triggers under rapid requests
- [ ] Cost and latency are logged accurately per call
- [ ] Confidence visibly drops when the two passes disagree on a critical field
- [ ] Someone unfamiliar with the code could integrate using only the OpenAPI docs and README, no other explanation needed

---

## README Template

```markdown
# Document Intelligence API

## Problem

[client's situation, in their words]

## Results

- Cost per document: $X.XX
- p95 latency: Xms
- Retry success rate: X%

## Architecture

[diagram + description]

## Key Decisions

[schema design reasoning, what counts as critical, confidence design]

## Tools

FastAPI, Pydantic, Gemini API, pdfplumber, Docker

## Known Limitations

[be honest, same standard as every prior project]

## How to Run

[Docker instructions + curl quickstart]

## API Docs

[link to deployed OpenAPI docs, or local /docs route]
```

---

## X Checkpoints

1. **Teach AI Simply**: "How do you guarantee an LLM's output matches a schema every time?" is a genuinely good explainer, structured output plus the validation-feedback retry loop, visual-friendly as a before/after or a flow.
2. **Learn in Public**: the retry loop actually catching a real malformed output during testing, or Docker finally working this time, a nice callback to the E1 attempt that was correctly abandoned.
3. **Business Positioning**: cost-per-document and "a stranger could integrate using only the docs" are strong proof points, the brief's own "APIs are how AI gets sold B2B" line is close to a ready-made hook.

---

## Before Moving to Project 6

- [ ] A stranger could integrate using only your OpenAPI docs and README
- [ ] Malformed model output triggers a retry, then a clean 422, never a crash
- [ ] You know your real cost and p95 latency per document
