"""Rule engine: loads playbook.yaml (pure config, no LLM involved),
dispatches to the matching function in rules.py, and wraps every call
so an evaluation error becomes needs_review rather than a crash or a
silent (wrong) green. No LLM client imports here, ever.
"""

from __future__ import annotations

from pathlib import Path
from typing import List

import yaml

from rule_types import ClauseInput, RuleResult, Verdict
from rules import RULE_FUNCS

PLAYBOOK_PATH = Path(__file__).resolve().parents[2] / "playbook.yaml"


def load_playbook(path: Path = PLAYBOOK_PATH) -> List[dict]:
    with open(path, encoding="utf-8") as f:
        data = yaml.safe_load(f)
    return data["rules"]


def evaluate_rule(rule_def: dict, ci: ClauseInput) -> RuleResult:
    rule_id = rule_def["id"]
    clause_type = rule_def["clause_type"]
    fn = RULE_FUNCS.get(rule_id)

    if fn is None:
        return RuleResult(rule_id, clause_type, Verdict.NEEDS_REVIEW,
                           f"No rule implementation registered for {rule_id!r}.")

    try:
        verdict_str, reason = fn(ci, rule_def.get("params", {}))
    except Exception as e:  # a buggy rule must never silently pass as green
        return RuleResult(rule_id, clause_type, Verdict.NEEDS_REVIEW,
                           f"Rule evaluation error in {rule_id!r}: {e}")

    try:
        verdict = Verdict(verdict_str)
    except ValueError:
        return RuleResult(rule_id, clause_type, Verdict.NEEDS_REVIEW,
                           f"Rule {rule_id!r} returned an unknown verdict {verdict_str!r}.")

    return RuleResult(rule_id, clause_type, verdict, reason)


def evaluate_all(clause_inputs: dict, path: Path = PLAYBOOK_PATH) -> List[RuleResult]:
    """`clause_inputs`: clause_type -> ClauseInput. A clause type with no
    entry at all is treated as present=False (the type was never
    classified for this contract)."""
    results = []
    for rule_def in load_playbook(path):
        ci = clause_inputs.get(rule_def["clause_type"], ClauseInput(present=False))
        results.append(evaluate_rule(rule_def, ci))
    return results
