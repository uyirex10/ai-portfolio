# Splitter test-split results (Stage B)

Test split was sealed after aggregate PDF-set statistics were seen; no case-level inspection, no tuning against it.

Frozen caps_fallback_rule: A
Test-set contracts: 154, read errors: 6

## Clause stats
- n = 148
- mean clauses/contract = 25.2
- median clauses/contract = 20.0
- max clauses/contract = 183
- zero-heading contracts = 2
- collapsed (1-clause) contracts = 0

## Span integrity per category

| Category | raw | omitted | drop% | kept | contained | cut | not_found | contain% | cut% | median_fill | under20% |
|---|---|---|---|---|---|---|---|---|---|---|---|
| Governing Law | 137 | 2 | 1.5% | 135 | 135 | 0 | 0 | 100.0% | 0.0% | 0.414 | 28.1% |
| Anti-Assignment | 178 | 9 | 5.1% | 169 | 166 | 2 | 1 | 98.2% | 1.2% | 0.376 | 33.1% |
| Cap On Liability | 203 | 10 | 4.9% | 193 | 190 | 3 | 0 | 98.4% | 1.6% | 0.330 | 36.3% |
| License Grant | 196 | 14 | 7.1% | 182 | 178 | 2 | 2 | 97.8% | 1.1% | 0.285 | 42.1% |
| Termination For Convenience | 68 | 6 | 8.8% | 62 | 59 | 0 | 3 | 95.2% | 0.0% | 0.282 | 40.7% |
| Exclusivity | 126 | 2 | 1.6% | 124 | 121 | 2 | 1 | 97.6% | 1.6% | 0.262 | 39.7% |
| Audit Rights | 188 | 6 | 3.2% | 182 | 181 | 1 | 0 | 99.5% | 0.5% | 0.184 | 53.6% |
| Non-Compete | 64 | 10 | 15.6% | 54 | 52 | 2 | 0 | 96.3% | 3.7% | 0.371 | 36.5% |
| **OVERALL** | 1160 | 59 | 5.1% | 1101 | 1082 | 12 | 7 | 98.3% | 1.1% | n/a | 39.3% |