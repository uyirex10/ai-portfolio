<title>Contract Analysis Agent</title>

## Problem

Reviewing a commercial contract for a handful of specific risk points
(is liability capped, what's the governing law, is there an audit
right, when does it expire) is slow, repetitive, and easy to get wrong
by skimming. This project builds a pipeline that reads a contract PDF,
splits it into clauses without losing or rewriting a single character
of the source, classifies clauses against 8 CUAD-grounded clause
types, extracts the operative values a playbook rule actually needs,
and produces a review memo whose every quote is a verbatim slice of the
real document -- never a paraphrase, never the model's word for it.

## Results (real numbers only)

### Splitter (frozen as `splitter-v1`, see DECISIONS.md)

| Split | Contracts | Contain % | Cut % | Not-found % |
|---|---|---|---|---|
| TXT (tuned on this set) | 199 | 99.9% | 0.1% | 0.0% |
| PDF dev | 151-157 | 98.3% | 1.6% | 0.1% |
| PDF **test** (sealed, opened once) | 148-154 | 98.3% | 1.1% | 0.0% |

Test is not worse than dev on either headline number. Cap On
Liability's cut rate specifically: 28 cases (pre-fix) -> 23 (ALL-CAPS
fix alone) -> 10 (+ character map fix, dev) -> 1.6% cut rate on test.

### Clause-type gold-label support (real, computed from CUAD labels, no LLM needed)

| Clause type | Dev support | Test support |
|---|---|---|
| Cap On Liability | 95 | 108 |
| Termination For Convenience | 39 | 35 |
| Notice Period To Terminate Renewal | 39 | 34 |
| Governing Law | 56 | 66 |
| Agreement Date | 0 | 0 |
| Expiration Date | 98 | 97 |
| Effective Date | 15 | 13 |
| Audit Rights | 58 | 38 |

Agreement Date's 0 is real and investigated, not a bug -- see Known
Limitations.

### Classifier precision / recall / F1, grounding rate, value-extraction accuracy

**BLOCKED this session.** No `GEMINI_API_KEY` or `ANTHROPIC_API_KEY`
was available (confirmed by directly instantiating the provider and
calling it, not just checking the environment). These numbers are not
fabricated as a placeholder -- see `reports/error_analysis_dev.md` and
`reports/eval_test_results.md` for exactly what was attempted and the
error each attempt produced. Everything else in this project (the
splitter, the rule engine, the memo generator, the API) is built,
tested with mocked providers, and demonstrated end to end offline (see
`scripts/demo.py`) using hand-authored, clearly-labeled stand-in LLM
responses -- not real model output.

### pdfplumber vs PyMuPDF (pinned: PyMuPDF)

| | pdfplumber | PyMuPDF |
|---|---|---|
| Time, 30-contract sample | 363.5s | 11.5s (32x faster) |
| Identical clause count vs. the other | 11/29 contracts | |

No accuracy edge was found for pdfplumber to justify the 32x cost.

## Architecture: LLM perceives, code decides

```
PDF -> extract_pdf_text (PyMuPDF + 1:1 char map)
    -> segment_contract (offset-exact clause splitter, frozen)
    -> classify_clauses (LLM: multi-label over 8 types, batched)
    -> extract_clause_values (LLM: proposes values) -> ground_check (CODE: keeps only values that literally appear in the clause)
    -> src/rules/ (CODE: fail-closed verdicts -- green/amber/red/needs_review; no LLM import, enforced by a test)
    -> src/memo.py (quote sliced from the SOURCE by offset, never from the LLM's self-report; redline is LLM output, explicitly labeled a suggestion)
```

The LLM's only job anywhere in this pipeline is to turn free-form legal
text into a small number of structured values. Every decision after
that (is this grounded, is this a risk, what does the memo say) is
plain Python, independently testable, and fail-closed: `src/rules/`
cannot return "green" for `None` or ungrounded input (property-tested).

## Tools

Python 3.11, FastAPI, pydantic, PyMuPDF, pyyaml, pytest + hypothesis,
`google-genai` (default provider) with Anthropic as a pluggable
alternative, Docker, Render.

## Key decisions (pre-registered, logged in DECISIONS.md)

- **Splitter frozen (`splitter-v1`)**: a bake-off between the ALL-CAPS
  heading fallback's context-based rule (A) and a verb/modal-based rule
  (B) picked A -- B's dev cut rate rose +3.23 points, driven almost
  entirely by Cap On Liability (6.6% -> 26.5%), the opposite of what it
  was meant to fix.
- **PyMuPDF over pdfplumber**: 32x faster, no measured accuracy
  advantage.
- **8 clause types chosen mechanically**: must-include (Cap On
  Liability, Termination For Convenience, Notice Period To Terminate
  Renewal, Governing Law) plus the 4 highest-frequency value-carrying
  categories at >=15% frequency (Agreement Date, Expiration Date,
  Effective Date, Audit Rights) -- picked by a rule written down before
  the ranking was computed, not hand-curated for variety.
- **Gold rule**: a clause counts as positive for type T if it overlaps
  >=50% of any labeled T span.

## Known limitations

- **Test-split leak statement**: the TEST split (`data_splits/test_contracts.txt`)
  was opened exactly once for the splitter (Stage B) and once for the
  pipeline-level gold-label counts (Stage G), both aggregates-only, no
  case-level inspection, no tuning in response. It has never been read
  by any other script this session (verified: it is only ever *written*
  by `scripts/build_splits.py`, never read, outside those two call sites).
- **ALL-CAPS allowlist compromise**: the frozen heading-fallback rule
  rejects a caps candidate if the text before it is itself mostly
  uppercase, with a small hardcoded allowlist (GOVERNING LAW,
  TERMINATION, etc.) as an override for the case where a real heading
  immediately follows another clause's all-caps tail with nothing
  mixed-case in between. A real heading using wording not on that list,
  in that same position, would still be wrongly suppressed.
- **Pinned extractor**: PyMuPDF, not pdfplumber (see Results). Not
  revisited if a future PDF corpus looks very different from CUAD's.
- **U+037E fix**: some PDFs' fonts encode `;` as U+037E (a Greek
  character that renders identically to a semicolon); `src/extract.py`
  folds it back (and U+00A0 to a plain space) as a 1:1 character
  substitution, never a deletion or expansion, so offsets never shift.
  Found by tracing a single "not found" span by hand; recovers 115/116
  of a dev-set matching-failure bucket once applied.
- **Merge measure**: the splitter's dotted/lettered hierarchy can bury
  a short labeled span inside a much larger clause (low "fill ratio").
  This isn't separately re-measured post-freeze, but it's exactly the
  mechanism behind the Agreement Date finding below.
- **Agreement Date gold support is 0 on both dev and test**: not a bug.
  Its labeled spans (13-26 characters) are always embedded inside a
  much larger preamble clause (100-1900+ characters; measured overlaps
  0.009-0.164), so the 50%-overlap gold rule can structurally never mark
  it positive, independent of classifier quality. A future gold rule
  for "point-like" metadata categories should probably use span-side
  overlap (how much of the labeled span is inside the clause) rather
  than clause-side overlap.
- **Ungrounded values are nulled, not corrected**: `ground_check` has no
  way to recover the right value once it rejects a wrong one -- a
  rejected extraction becomes `None` (amber in the rule engine), not a
  second attempt.
- **Sampling fallback was not exercised**: the project's global rule
  describes a seeded-sample fallback for when quota (not a missing key)
  blocks a full eval; this session's blocker was a completely absent
  key, not a quota limit, so the fallback path exists in spec but was
  never actually triggered or tested against real quota behavior.
- **Value-extraction accuracy against labels is NOT measured, by
  design**: CUAD's labels are clause spans, not structured values, so
  there is no ground truth to check an extracted amount, date, or
  jurisdiction against. Only groundedness (does the value appear in its
  own clause) is measured, and even that needs a real extraction call
  this session didn't have.
- **A splitter quirk found via real demo data, not fixed (frozen)**: in
  one dev contract, a line-wrapped "401\n(k)" gets accepted as a
  continuation of an earlier (a)(b)(c)(d) lettered list, since "k"'s
  rank exceeds "d"'s.

## Testing summary

101 tests, all passing: splitter (15), extraction char-map (4), LLM
provider/cache/backoff (6), classify (7), extract_values (7), rules
engine incl. a hypothesis property test (30), memo quote-integrity (10),
eval metrics (15), API endpoints with a mocked provider (6), LLM
isolation enforcement (1). Run `pytest tests/ -v` from the project root
with the venv active.

## How to run

```
py -3.11 -m venv venv
venv\Scripts\pip install -r requirements.txt
```

Set `GEMINI_API_KEY` (or `ANTHROPIC_API_KEY` with `LLM_PROVIDER=anthropic`)
in a `.env` file (see `.env.example`) for real LLM calls, or run fully
offline from the committed demo cache:

```
venv\Scripts\python scripts\demo.py
```

Run the test suite:

```
venv\Scripts\python -m pytest tests/ -v
```

Run the API locally:

```
venv\Scripts\uvicorn src.api.app:app --reload
```

`CONTRACT_AGENT_API_KEYS=yourname:sk_whatever_you_want` in the
environment, then:

```
curl -X POST http://localhost:8000/v1/analyze \
  -H "X-API-Key: sk_whatever_you_want" \
  -F "file=@your_contract.pdf"
```

CUAD data (`cuad_data/`, gitignored) and the fixed dev/test split
(`data_splits/`, committed) are described in `NOTES.md`.
