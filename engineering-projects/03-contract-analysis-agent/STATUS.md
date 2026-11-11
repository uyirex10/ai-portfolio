# Status

Last updated: 2026-11-11. **Stage I in progress: live run with a real Gemini key.**
101/101 tests passing.

## Stage I progress
- Step 0 (preflight) DONE: real key confirmed working, live model list
  fetched (27 models), `gemini-3.8-flash` picked and verified with a
  real call. See DECISIONS.md. Demo cache re-seeded under the new
  model string; `scripts/demo.py` reconfirmed fully offline.
- Step 1 (clause-type amendment) DONE: Agreement Date (gold support 0,
  cannot be evaluated) replaced with Post-Termination Services (dev
  support 54, test support 60), the next category in the original
  Stage C ranking. Final 8 types + dev/test support + rule-compared
  value table in DECISIONS.md. Code updated to match (schemas.py,
  rules.py, playbook.yaml, tests, demo cache re-seeded).
- Step 2 (smoke test, 3 dev contracts, real model): NEXT.

## Final results table (real numbers only)

### Splitter (frozen as `splitter-v1`)

| Split | Contracts | Contain % | Cut % | Not-found % |
|---|---|---|---|---|
| TXT (tuned on this set) | 199 | 99.9% | 0.1% | 0.0% |
| PDF dev | 151-157 | 98.3% | 1.6% | 0.1% |
| PDF **test** (sealed, opened once) | 148-154 | 98.3% | 1.1% | 0.0% |

Cap On Liability cut-across, specifically: 28 (pre-fix) -> 23 (ALL-CAPS
fix alone) -> 10 (+ U+037E character map, dev) -> 1.6% cut rate on test.

### Clause-type gold-label support (real; no LLM needed)

| Clause type | Dev | Test |
|---|---|---|
| Cap On Liability | 95 | 108 |
| Termination For Convenience | 39 | 35 |
| Notice Period To Terminate Renewal | 39 | 34 |
| Governing Law | 56 | 66 |
| Agreement Date | 0 | 0 |
| Expiration Date | 98 | 97 |
| Effective Date | 15 | 13 |
| Audit Rights | 58 | 38 |

### Classifier precision/recall/F1, grounding rate, value accuracy

**BLOCKED all session.** No `GEMINI_API_KEY`/`ANTHROPIC_API_KEY` was
ever available (confirmed by direct instantiation + call, not just an
env check). Not fabricated as a substitute -- see
`reports/error_analysis_dev.md` and `reports/eval_test_results.md`.

## What's done, by stage

- **Stage A (frozen):** `src/extract.py` (shared PDF extraction, 1:1
  U+037E/U+00A0 char map). Bake-off chose Variant A for the ALL-CAPS
  heading fallback (B's dev cut rate rose +3.23pts, mostly from Cap On
  Liability 6.6%->26.5%). Tag `splitter-v1`.
- **Stage B:** sealed test run, once, aggregates only.
  `reports/splitter_test_results.md`.
- **Stage C:** 8 clause types chosen by mechanical rule -- see
  DECISIONS.md for the full candidate table.
- **Stage D:** `src/llm/provider.py` (Gemini default, Anthropic
  pluggable, disk cache, backoff, quota split), `classify.py`
  (batched), `extract_values.py` (grounding check). All mocked-provider
  tests pass; no real call ever succeeded.
- **Stage E:** `playbook.yaml` + `src/rules/` -- pure code, zero LLM
  imports (enforced by test), fail-closed by construction and by a
  hypothesis property test.
- **Stage F:** `src/memo.py` (quote sliced from source by offset,
  never the LLM's self-report), `src/pipeline.py`, `scripts/demo.py`
  (runs fully offline from a hand-seeded cache -- see
  `scripts/seed_demo_cache.py` for exactly what's hand-authored and
  why), 2 sample memos in `reports/sample_memos/`.
- **Stage G:** `src/eval_metrics.py` (gold rule, P/R/F1, auto-tagged
  error analysis) -- pure, fully unit-tested. Gold-label support
  computed for real on dev and test; precision/recall/F1/grounding/
  value-accuracy explicitly BLOCKED, not fabricated.
- **Stage H:** `src/api/app.py` + `auth.py` (X-API-Key, pattern from
  the sibling Document Intelligence project), 6 endpoint tests with a
  mocked provider, `Dockerfile`/`.dockerignore`/`render.yaml` (not
  built, not deployed).
- README, LEARN.md (progressive, both core ideas at 5 age levels),
  DECISIONS.md, this file, secrets scan (clean), full test suite: all
  done.

## Real bugs found and fixed along the way (not just features added)

1. Semicolon-count check proved the earlier "2.29x length gap" finding
   was really a 362.9x semicolon-rate artifact, not a length effect.
2. `GeminiProvider`/`AnthropicProvider` built their client in `__init__`,
   which raised immediately with no key -- defeating offline/cached
   operation. Fixed to lazy-init on first real `_call()`.
3. `memo.py` had no path for a "missing clause type" finding (nothing
   to quote) until building the demo surfaced the gap. Fixed with a
   `(None, None)` case that still satisfies `quote == source[start:end]`
   (quote is `""` at `(0, 0)`, not a placeholder string).
4. `scripts/seed_demo_cache.py`'s first attempt seeded one combined
   classification prompt for a 26-clause contract; the real pipeline
   batches at 20 clauses, so it silently fell through to a real
   (failing) API call. Fixed by reusing the real batching function.
5. My own `eval_metrics.classify_error` first draft mis-prioritized
   "boundary problem" ahead of "buried span" so the latter was
   unreachable except in a degenerate case; caught by its own unit
   tests, not inspection.
6. `src/api/app.py` added `src/` and `src/llm/` to `sys.path` but never
   its own directory, so `from auth import ...` only worked by accident
   in tests; would have failed in the real `uvicorn src.api.app:app`
   entrypoint. Caught by actually testing the dotted import path before
   trusting the Dockerfile, not by inspection.
7. Agreement Date's gold support of exactly 0 looked like a bug;
   investigated by hand and confirmed it's a real structural mismatch
   between the 50%-overlap gold rule and "point-like" metadata spans
   buried in large preamble clauses -- not a bug, a methodology
   limitation now documented in the README.

## Known blocker (confirmed, not guessed)

No `GEMINI_API_KEY` or `ANTHROPIC_API_KEY` was available this entire
session. Confirmed by actually instantiating a provider and calling
`.complete()` (raises `ValueError: No API key was provided`), not just
an environment-variable check. Every stage that needed a live call was
still built and tested in full (with mocked providers); every report
that would have needed real predictions says BLOCKED explicitly rather
than substituting a plausible-looking number.

## Verified vs guessed

Every claim with a number in this file and in DECISIONS.md was
measured this session (logs retained in `cuad_data/*.log`, gitignored
but reproducible by re-running the corresponding script). Nothing
numeric in this file is guessed. See README's Known Limitations for
the few places a judgment call (not a number) was made and labeled as
such (the ALL-CAPS allowlist compromise, the pinned extractor choice).
