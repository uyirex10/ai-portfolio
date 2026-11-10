# Status

Last updated: 2026-11-10 (Stage A complete, frozen)

## Done
- Stage 1 / 1.5 / 1.6 (prior session): segment.py splitter, CUAD data, dev/test split (sealed), ALL-CAPS fix v1, PyMuPDF pinned.
- **Stage A (complete, frozen):**
  - `src/extract.py`: shared `extract_pdf_text()`, 1:1 char map (U+037E->';', U+00A0->' '). All duplicate pymupdf extraction code in scripts/ removed, all import from here now.
  - Semicolon-count check: VERIFIED the earlier "2.29x length gap" was really a semicolon-count artifact (not-found spans had 362.9x the semicolon rate of found spans).
  - Dev span integrity after char-map: not-found 11.7%->0.1% (116->1 case). TXT set barely moved (already clean).
  - 2 TXT contracts that lost their only heading: both were the document's own title, not a real section heading (benign).
  - Bake-off (Variant A vs B for ALL-CAPS fallback): **A chosen** (pre-registered rule failed on condition 2 -- B's dev cut rate rose +3.23pts, driven by Cap On Liability 6.6%->26.5%). See DECISIONS.md.
  - Cap On Liability dev cut-across: 28 (pre-any-fix) -> 23 (ALL-CAPS fix alone) -> 10 (+ char-map fix). `reports/cap_liability_cuts_after.md`.
  - Tag: `splitter-v1`. segment.py and extract.py frozen from here on.

## In progress
- Stage B (sealed test run) -- script ready (`scripts/run_sealed_test.py`), not yet executed.

## Next
- Stage B -> C (done, see DECISIONS.md) -> D (LLM provider built, not yet wired to classify/extract) -> E (rules) -> F (memos) -> G (eval) -> H (ship).

## Stage C (done)
8 clause types chosen by pre-registered mechanical rule: Cap On Liability, Termination For Convenience, Notice Period To Terminate Renewal, Governing Law (must-include), Agreement Date, Expiration Date, Effective Date, Audit Rights (fill by frequency). See DECISIONS.md for the full candidate table and the "3 date fields" observation.

## Stage D (in progress)
- `src/llm/provider.py`: LLMProvider ABC, GeminiProvider (default), AnthropicProvider (pluggable), disk cache at `.cache/llm/` (hash of model+prompt, NOT gitignored so demo.py can run offline from committed cache entries), exponential backoff, QuotaExceededError vs RateLimitedError split.
- `tests/test_llm_isolation.py`: global-rule enforcement test (src/rules/ may not import anthropic/google/openai/requests). Passes trivially until src/rules/ exists (Stage E).
- Not yet done: classify/extract pydantic schemas, batching, grounding check, mocked-provider tests.

## Known blocker
- No LLM API key found in `.env` or shell env (checked once; further credential inspection is sandboxed by the harness). Code, caching, and mocked tests proceed regardless; live calls against real contracts will be flagged clearly when/if attempted and blocked.

## Verified vs guessed (running log)
See DECISIONS.md for pre-registered choices and their measured outcomes -- all Stage A/C numbers above are VERIFIED (measured, logs retained under cuad_data/*.log).
