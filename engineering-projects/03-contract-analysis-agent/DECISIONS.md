# Decisions log

Pre-registered rules and the measured outcomes that triggered them, in order.

(Entries appended as each stage completes.)

## Stage A: ALL-CAPS fallback bake-off (pre-registered rule, mechanical)

Rule: pick Variant B only if, on dev, it (1) lowers the under-20%-fill
share AND (2) raises overall cut rate by <=0.5 points absolute AND
(3) does not raise zero-heading count. Otherwise keep Variant A.

Measured (full numbers in `cuad_data/bakeoff.log`):
- dev under-20%-fill share: A=30.6%, B=30.4% (condition 1: TRUE)
- dev overall cut rate: A=1.6%, B=4.8%, delta=+3.23 pts (condition 2: FALSE)
- dev zero-heading count: A=10, B=6 (condition 3: TRUE)

Condition 2 fails, so **the rule selects Variant A**.

Why B fails despite 2 of 3 conditions passing: B's cut rate explosion is
concentrated almost entirely in Cap On Liability (6.6% -> 26.5% on PDF
dev), the exact category the ALL-CAPS fix targeted. Cause: a verb/modal
filter wrongly keeps short disclaimer fragments that happen to contain
no verb (e.g. "SUCH DAMAGES", "LOST PROFITS") as if they were headings,
re-fragmenting the same disclaimer clauses Variant A was built to stop
fragmenting -- the opposite failure mode from what A originally fixed,
triggered by the same underlying ambiguity (all-caps text that is
sometimes a label and sometimes just more disclaimer prose).

**segment.py and extract.py are frozen as of this decision. Tag:
`splitter-v1`.**

## Stage B: sealed test run (one time only)

Ran `scripts/run_sealed_test.py` once against `data_splits/test_contracts.txt`
(154 of 157 contracts readable) with the frozen splitter (rule A).
Aggregates only -- no case-level inspection, logged here and in
`reports/splitter_test_results.md`.

Test: contain% 98.3%, cut% 1.1%, median clauses/contract 20.
Dev (for comparison, same harness): contain% 98.3%, cut% 1.6%.

Test is not worse than dev on either headline number -- no sign of
having tuned to dev's idiosyncrasies. Cap On Liability specifically:
test cut% 1.6% vs dev 6.6% (test is better here, not worse). No
re-tuning was done in response to this; the rule says test results are
reported, not acted on.

## Stage C: 8 clause types (pre-registered rule, mechanical)

Rule: must-include Cap On Liability, Termination For Convenience,
Notice Period To Terminate Renewal, Governing Law (all cleared the
>=40-labeled-spans check easily: 275, 183, 111, 437 respectively). Fill
remaining 4 slots by highest frequency among categories that carry a
rule-comparable value (measured: >=50% of that category's raw labeled
spans contain a number/currency/duration/percent token, or -- for the
date/jurisdiction categories where the -Answer column is already a
structured value -- that column counts directly) and appear in >=15%
of contracts (>=77/510).

Ranked candidates (full table in `scripts/choose_clause_types.py`
output): Agreement Date (92.2%), Expiration Date (81.0%), Effective
Date (76.5%), Audit Rights (42.0%), Post-Termination Services (35.7%),
Exclusivity (35.3%), Renewal Term (34.5%), ... down to Volume
Restriction (16.1%).

**Mechanical result: Agreement Date, Expiration Date, Effective Date,
Audit Rights fill the remaining 4 slots.**

Final 8: Cap On Liability, Termination For Convenience, Notice Period
To Terminate Renewal, Governing Law, Agreement Date, Expiration Date,
Effective Date, Audit Rights.

Observation (not a deviation -- the rule was applied as written): 3 of
the 8 are near-duplicate date fields (Agreement/Effective/Expiration
Date), because dates are both extremely frequent and trivially
"value-carrying" by the measurement used. A hand-picked set optimizing
for substantive legal diversity (e.g. swapping in Exclusivity or
Post-Termination Services) would look different, but the pre-registered
rule says highest frequency among value-carrying categories, not most
diverse, so the mechanical result stands.
