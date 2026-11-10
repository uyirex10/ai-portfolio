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

## Done (continued)
- **Stage B (complete):** sealed test run, once. contain% 98.3%, cut% 1.1% -- consistent with dev, no tuning after seeing it. `reports/splitter_test_results.md`.
- **Stage D (code complete, live calls blocked):** `src/llm/provider.py` (Gemini default/Anthropic pluggable, disk cache, backoff, quota split), `classify.py` (batched multi-label), `extract_values.py` (pydantic schema + grounding check). All mocked-provider tests pass (27 tests across provider/classify/extract_values).
- **Stage E (complete):** `playbook.yaml` (1 rule per clause type, placeholder thresholds labeled as such), `src/rules/` (engine.py, rules.py, rule_types.py -- pure code, zero LLM imports, enforced by tests/test_llm_isolation.py). 30 tests incl. a hypothesis property test: no absent/all-None input ever yields green.

- **Stage F (complete):** `src/memo.py` (quote-by-offset with a `(None, None)` "missing clause" case added after discovering the gap while building the demo; redlines LLM-generated and cached, clearly labeled as suggestions). `src/pipeline.py` orchestrates segment->classify->extract->rules->memo for one contract. `scripts/demo.py` runs one dev contract fully offline from a hand-seeded cache (`scripts/seed_demo_cache.py`, clearly disclosed as hand-authored stand-in content, not real model output). 2 sample memos written to `reports/sample_memos/`.
- Found via real demo data (not fixed -- segment.py is frozen per Stage A): in the TransMontaigne contract, a lettered sub-clause list "(a)...(b)...(c)...(d)" is followed later by "401(k)" wrapped across a line break as "401\n(k)", and the splitter's strictly-increasing-rank check accepts "(k)" as a continuation of the same list (k's rank > d's) even though it's actually a 401(k) plan reference, not a list item. Noted for the README's known limitations.

## Next
- Stage G (eval) -> H (ship).

## Stage C (done)
8 clause types chosen by pre-registered mechanical rule: Cap On Liability, Termination For Convenience, Notice Period To Terminate Renewal, Governing Law (must-include), Agreement Date, Expiration Date, Effective Date, Audit Rights (fill by frequency). See DECISIONS.md for the full candidate table and the "3 date fields" observation.

## Stage D (in progress)
- `src/llm/provider.py`: LLMProvider ABC, GeminiProvider (default), AnthropicProvider (pluggable), disk cache at `.cache/llm/` (hash of model+prompt, NOT gitignored so demo.py can run offline from committed cache entries), exponential backoff, QuotaExceededError vs RateLimitedError split.
- `tests/test_llm_isolation.py`: global-rule enforcement test (src/rules/ may not import anthropic/google/openai/requests). Passes trivially until src/rules/ exists (Stage E).
- Not yet done: classify/extract pydantic schemas, batching, grounding check, mocked-provider tests.

## Known blocker (confirmed, not guessed)
- Confirmed by actually instantiating `GeminiProvider` and calling `.complete()`: raises `ValueError: No API key was provided`. `GEMINI_API_KEY` and `ANTHROPIC_API_KEY` are both unset. No real LLM call has succeeded or will succeed this session. Code, caching, and mocked-provider tests proceed regardless (all passing). Every stage from here that needs a live call (Stage D real classify/extract on real contracts, Stage F real redlines, Stage G real precision/recall) will be built in full but will report this blocker explicitly rather than fabricating numbers. scripts/demo.py will use hand-authored, clearly-labeled synthetic cache entries (not real model output) so the pipeline wiring is still demonstrable end to end.

## Verified vs guessed (running log)
See DECISIONS.md for pre-registered choices and their measured outcomes -- all Stage A/C numbers above are VERIFIED (measured, logs retained under cuad_data/*.log).
