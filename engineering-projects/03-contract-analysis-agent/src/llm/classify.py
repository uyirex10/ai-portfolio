"""Multi-label clause classification over Stage C's 8 clause types (or
none). Batches clauses by character budget (see batching.py) so there
is roughly 1 LLM call per ~20 clauses, not one call per clause.
"""

from __future__ import annotations

import json
from typing import Dict, List, Tuple

from batching import batch_by_char_budget
from provider import LLMProvider
from schemas import CLAUSE_TYPES, ClauseClassification

ClausePair = Tuple[str, str]  # (clause_id, clause_text)


def build_classification_prompt(batch: List[ClausePair]) -> str:
    type_list = "\n".join(f"- {t}" for t in CLAUSE_TYPES)
    clause_blocks = "\n\n".join(f'Clause "{cid}":\n{text}' for cid, text in batch)
    return (
        "You are classifying contract clauses. For each clause below, decide which of the "
        "following clause types it matches. A clause may match zero, one, or more types.\n\n"
        f"Clause types:\n{type_list}\n\n"
        "Respond with ONLY a JSON object mapping each clause id (as a string) to a list of "
        "matching type names, using the exact names above. Use an empty list if none match. "
        "No text outside the JSON object.\n\n"
        f"{clause_blocks}"
    )


def parse_classification_response(response: str, expected_ids: List[str]) -> Dict[str, List[str]]:
    valid_types = set(CLAUSE_TYPES)
    try:
        data = json.loads(response)
        if not isinstance(data, dict):
            data = {}
    except (json.JSONDecodeError, TypeError):
        # Fail closed: an unparseable response means no labels, not a guess.
        data = {}

    result = {}
    for cid in expected_ids:
        labels = data.get(cid, [])
        if not isinstance(labels, list):
            labels = []
        result[cid] = [label for label in labels if label in valid_types]
    return result


def classify_clauses(clauses: List[ClausePair], provider: LLMProvider) -> List[ClauseClassification]:
    batches = batch_by_char_budget(clauses, text_of=lambda c: c[1])
    results: List[ClauseClassification] = []
    for batch in batches:
        prompt = build_classification_prompt(batch)
        response = provider.complete(prompt)
        ids = [cid for cid, _ in batch]
        parsed = parse_classification_response(response, ids)
        for cid in ids:
            results.append(ClauseClassification(clause_id=cid, labels=parsed[cid]))
    return results
