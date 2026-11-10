# Dev-set error analysis (Stage G)

## Gold-label support (computed from real data, no LLM needed -- VERIFIED)

Dev contracts with gold labels computed: 149 / 157 in split
Total leaf clauses across dev set: 16617

| Clause type | Gold support (clauses) |
|---|---|
| Cap On Liability | 95 |
| Termination For Convenience | 39 |
| Notice Period To Terminate Renewal | 39 |
| Governing Law | 56 |
| Agreement Date | 0 |
| Expiration Date | 98 |
| Effective Date | 15 |

**Agreement Date's support of 0 is a real, investigated finding, not a bug.** Checked directly: Agreement
Date spans are consistently tiny (13-26 characters, e.g. "October 1, 2019") and are always embedded deep
inside a much larger preamble/intro clause (100-1900+ characters) that also contains the parties' names,
recitals, etc. Sample measured overlaps (span length / containing clause length): 0.009, 0.016, 0.018,
0.019, 0.024, 0.034, 0.132, 0.164 -- every single one far below the 50% gold threshold. This means the
pre-registered "50% of clause overlap" gold rule can **structurally never** produce a positive gold label
for Agreement Date given how segment.py's clauses are shaped, regardless of how good a classifier is --
it is a mismatch between the gold rule and this clause type's "point-like metadata buried in a structural
clause" shape, not a measurement of anything. Effective Date's much lower support (15) relative to its
~76% raw frequency in the full CUAD corpus is the same effect, partially. Expiration Date and Governing
Law are less affected because their labeled spans are usually whole sentences (e.g. a full "this Agreement
is governed by..." clause) rather than a short embedded date/name. **This is flagged as a methodology
limitation for the README, not acted on this session** (Stage A's splitter is frozen; changing the gold
rule itself was out of scope for Stage G as written).
| Audit Rights | 58 |

## Precision / recall / F1 -- BLOCKED

**No real LLM classification predictions could be obtained this session.** Error on first attempted call: `ValueError: No API key was provided. Please pass a valid API key. Learn how to create an API key at https://aistudio.google.com/docs/api-key.`. No `GEMINI_API_KEY` or `ANTHROPIC_API_KEY` was available (confirmed by direct instantiation attempt, not just an env-var check -- see STATUS.md). Precision, recall, F1, and the 10 false-positive / 10 false-negative examples per type this section is supposed to contain cannot be produced without real predictions, and are **GUESSED-NOT-PRESENT rather than fabricated.** The gold-label support counts above are real and independent of this blocker -- they describe the data, not a model's performance on it.

Per clause type, the required skeleton (to fill in once a real run is possible):

### Cap On Liability

- Precision: BLOCKED (no predictions)
- Recall: BLOCKED (no predictions)
- F1: BLOCKED (no predictions)
- Support: 95 (real)
- 10 false positives: BLOCKED (no predictions)
- 10 false negatives: BLOCKED (no predictions)
- Rex's hypothesis: 

### Termination For Convenience

- Precision: BLOCKED (no predictions)
- Recall: BLOCKED (no predictions)
- F1: BLOCKED (no predictions)
- Support: 39 (real)
- 10 false positives: BLOCKED (no predictions)
- 10 false negatives: BLOCKED (no predictions)
- Rex's hypothesis: 

### Notice Period To Terminate Renewal

- Precision: BLOCKED (no predictions)
- Recall: BLOCKED (no predictions)
- F1: BLOCKED (no predictions)
- Support: 39 (real)
- 10 false positives: BLOCKED (no predictions)
- 10 false negatives: BLOCKED (no predictions)
- Rex's hypothesis: 

### Governing Law

- Precision: BLOCKED (no predictions)
- Recall: BLOCKED (no predictions)
- F1: BLOCKED (no predictions)
- Support: 56 (real)
- 10 false positives: BLOCKED (no predictions)
- 10 false negatives: BLOCKED (no predictions)
- Rex's hypothesis: 

### Agreement Date

- Precision: BLOCKED (no predictions)
- Recall: BLOCKED (no predictions)
- F1: BLOCKED (no predictions)
- Support: 0 (real)
- 10 false positives: BLOCKED (no predictions)
- 10 false negatives: BLOCKED (no predictions)
- Rex's hypothesis: 

### Expiration Date

- Precision: BLOCKED (no predictions)
- Recall: BLOCKED (no predictions)
- F1: BLOCKED (no predictions)
- Support: 98 (real)
- 10 false positives: BLOCKED (no predictions)
- 10 false negatives: BLOCKED (no predictions)
- Rex's hypothesis: 

### Effective Date

- Precision: BLOCKED (no predictions)
- Recall: BLOCKED (no predictions)
- F1: BLOCKED (no predictions)
- Support: 15 (real)
- 10 false positives: BLOCKED (no predictions)
- 10 false negatives: BLOCKED (no predictions)
- Rex's hypothesis: 

### Audit Rights

- Precision: BLOCKED (no predictions)
- Recall: BLOCKED (no predictions)
- F1: BLOCKED (no predictions)
- Support: 58 (real)
- 10 false positives: BLOCKED (no predictions)
- 10 false negatives: BLOCKED (no predictions)
- Rex's hypothesis: 
