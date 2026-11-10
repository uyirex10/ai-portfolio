# Engineering notes

## Pinned PDF extractor: PyMuPDF

**Decision: use PyMuPDF (`pymupdf`/`fitz`) for all PDF text extraction. Do not use pdfplumber.**

### Why

Measured on a fixed seed-42 random sample of 30 PDF-only CUAD contracts
(`data_splits/sample_30_contracts.txt`):

- **Speed: pdfplumber is ~32x slower.** 363.5s total extraction time for
  pdfplumber across the 30-contract sample vs. 11.5s for PyMuPDF. On one
  individual contract (`DigitalCinemaDestinationsCorp...Affiliate
  Agreement.pdf`, 217KB), pdfplumber alone took 47.2s. Extrapolated to
  the full 314 PDF-only contracts, a full pdfplumber pass is impractical
  for routine use (the first attempt at this was killed after ~100/314
  contracts; a second attempt was deliberately capped to a 30-contract
  sample per the next validation stage's explicit instruction).
- **No accuracy advantage found.** Mean top-level clause count was
  nearly identical (24.7 for pdfplumber vs. 24.5 for PyMuPDF on the
  sample), but that aggregate hides large per-document divergence: only
  11/29 contracts produced an *identical* clause count between the two
  extractors, with some differing sharply (e.g. 39 vs. 83, 20 vs. 7, 28
  vs. 16). There's no ground truth in this comparison to say either
  extractor is "more correct" on those cases -- they're just different,
  and divergence this large on over a third of the sample means neither
  extractor's output can be assumed close to the other's.
- Given no demonstrated quality advantage and a 32x speed cost,
  pdfplumber does not clear the bar of "clearly better." PyMuPDF stays
  the default.

### Known PyMuPDF quirks (discovered via span-integrity debugging)

PyMuPDF faithfully extracts whatever codepoint a PDF's font encoding
actually specifies, which is not always the character it visually
resembles. Confirmed in `QuantumGroupIncFl..._Hosting Agreement.pdf`:
that PDF's font maps semicolons to `;` (Greek question mark, which
renders visually identical to `;` in most fonts) and all spaces to
`\xa0` (non-breaking space). This single substitution (`;` -> `;`)
recovered 115 of 116 (99%) of an otherwise-"unexplained" span-matching
failure bucket in the dev-set span-integrity check -- see
`scripts/unexplained_bucket.py` and the Stage 1.6 summary. It has not
yet been added to the matching harness's fold map (out of scope for the
step that discovered it); recommended as the next harness fix.

## Validation methodology notes

- `data_splits/dev_contracts.txt` / `test_contracts.txt`: a seed-42
  50/50 split of the 314 PDF-only CUAD contracts (not the 310 originally
  estimated -- the real count is 314). Only `dev` may be inspected case
  by case; `test` is sealed to aggregate-only reporting, and has not
  been read by any script as of this note.
- The TXT set (200 contracts) was never part of this split -- it's a
  separate population that `segment.py` was tuned against from Stage 1
  onward, so it is not a held-out check on its own; the PDF dev/test
  split exists specifically because the TXT set cannot serve that role.
