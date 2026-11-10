"""End-to-end orchestration: segment -> classify -> extract -> rules ->
memo, for one contract's text. Used by scripts/demo.py, the sample-memo
generator, and (Stage H) the FastAPI endpoint, so there is exactly one
place that wires these stages together.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Optional

_SRC = Path(__file__).resolve().parent
for sub in ("llm", "rules"):
    p = str(_SRC / sub)
    if p not in sys.path:
        sys.path.insert(0, p)
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from segment import segment_contract, flatten  # noqa: E402
from classify import classify_clauses  # noqa: E402
from extract_values import extract_clause_values  # noqa: E402
from schemas import CLAUSE_TYPES  # noqa: E402
from engine import evaluate_all, load_playbook  # noqa: E402
from rule_types import ClauseInput  # noqa: E402
import memo as memo_mod  # noqa: E402


def analyze_contract(text: str, provider) -> dict:
    leaves = flatten(segment_contract(text))
    id_to_clause = {}
    pairs = []
    for i, c in enumerate(leaves):
        cid = f"clause_{i}"
        id_to_clause[cid] = c
        pairs.append((cid, c.text))

    classifications = classify_clauses(pairs, provider)

    clauses_by_type = {t: [] for t in CLAUSE_TYPES}
    for cl in classifications:
        for label in cl.labels:
            if label in clauses_by_type:
                clauses_by_type[label].append(cl.clause_id)

    clause_inputs = {}
    extraction_records = []  # (clause_id, Clause, clause_type, ClauseExtraction)
    for clause_type, cids in clauses_by_type.items():
        if not cids:
            clause_inputs[clause_type] = ClauseInput(present=False)
            continue
        cid = cids[0]  # demo simplicity: first matching clause backs this type's rule input
        clause = id_to_clause[cid]
        extraction = extract_clause_values(cid, clause_type, clause.text, provider)
        extraction_records.append((cid, clause, clause_type, extraction))
        v = extraction.values
        clause_inputs[clause_type] = ClauseInput(
            present=True, amount=v.amount, currency=v.currency, notice_days=v.notice_days,
            jurisdiction=v.jurisdiction, date=v.date,
        )

    rule_results = evaluate_all(clause_inputs)

    clause_finding_inputs = []
    for rr in rule_results:
        rec = next((r for r in extraction_records if r[2] == rr.clause_type), None)
        if rec:
            cid, clause, ctype, extraction = rec
            clause_finding_inputs.append(memo_mod.ClauseFindingInput(
                clause_type=rr.clause_type, rule_id=rr.rule_id, verdict=rr.verdict.value, reason=rr.reason,
                clause_start=clause.start, clause_end=clause.end, evidence=extraction.values.evidence,
            ))
        else:
            clause_finding_inputs.append(memo_mod.ClauseFindingInput(
                clause_type=rr.clause_type, rule_id=rr.rule_id, verdict=rr.verdict.value, reason=rr.reason,
            ))

    memo_findings = memo_mod.build_memo_findings(text, clause_finding_inputs, provider=provider)

    return {
        "leaves": leaves,
        "classifications": classifications,
        "extraction_records": extraction_records,
        "rule_results": rule_results,
        "memo_findings": memo_findings,
    }
