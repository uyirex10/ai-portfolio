# TEST-split pipeline evaluation results (Stage G)

Test split was opened once for this pipeline evaluation, aggregates only; no case-level inspection, no tuning against it.

Test contracts with gold labels computed: 146 / 157 in split
Total leaf clauses: 16131

## Gold-label support (real, no LLM needed)

| Clause type | Gold support (clauses) |
|---|---|
| Cap On Liability | 108 |
| Termination For Convenience | 35 |
| Notice Period To Terminate Renewal | 34 |
| Governing Law | 66 |
| Agreement Date | 0 |
| Expiration Date | 97 |
| Effective Date | 13 |
| Audit Rights | 38 |

## Precision / recall / F1 / grounding rate -- BLOCKED

No real LLM classification predictions could be obtained this session (`ValueError: No API key was provided. Please pass a valid API key. Learn how to create an API key at https://aistudio.google.com/docs/api-key.`). No `GEMINI_API_KEY` or `ANTHROPIC_API_KEY` was available. These numbers are NOT fabricated as a substitute.

## Value-extraction accuracy

Not measured, by design, in this project: CUAD's labels are clause SPANS, not structured values, so there is no ground truth to check an extracted amount, date, or jurisdiction against. Only whether an extracted value is grounded in its own clause text (src/llm/extract_values.py's ground_check) is measured, and that too requires a real extraction call this session did not have.