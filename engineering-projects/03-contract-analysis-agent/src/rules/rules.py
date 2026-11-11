"""One function per playbook.yaml rule id. Every function returns
(verdict_str, reason) and must fail closed: missing or ungrounded
input (None) never produces "green". No LLM client imports here, ever
-- see tests/test_llm_isolation.py.
"""

from __future__ import annotations

from typing import Callable, Dict, Tuple

from rule_types import ClauseInput  # noqa: F401 -- re-exported for callers' convenience

RuleFunc = Callable[["ClauseInput", dict], Tuple[str, str]]

RULE_FUNCS: Dict[str, RuleFunc] = {}


def register(rule_id: str):
    def deco(fn: RuleFunc) -> RuleFunc:
        RULE_FUNCS[rule_id] = fn
        return fn
    return deco


@register("cap_on_liability_present_and_reasonable")
def _rule_cap_on_liability(ci, params) -> Tuple[str, str]:
    if not ci.present:
        return "red", "No liability cap clause found -- liability may be uncapped."
    if ci.amount is None:
        return "amber", "Liability cap clause found but the amount could not be grounded."
    threshold = params["min_reasonable_amount"]
    if ci.amount < threshold:
        return "amber", f"Liability cap (${ci.amount:,.0f}) is below the placeholder threshold (${threshold:,.0f})."
    return "green", f"Liability cap (${ci.amount:,.0f}) meets the placeholder threshold (${threshold:,.0f})."


@register("termination_for_convenience_present")
def _rule_termination_for_convenience(ci, params) -> Tuple[str, str]:
    if not ci.present:
        return "amber", "No termination-for-convenience right found."
    return "green", "Termination-for-convenience right present."


@register("renewal_notice_minimum_window")
def _rule_renewal_notice(ci, params) -> Tuple[str, str]:
    if not ci.present:
        return "red", "No renewal-notice period found -- an auto-renewal could lock the party in with no known opt-out window."
    if ci.notice_days is None:
        return "amber", "Renewal-notice clause found but the notice period could not be grounded."
    threshold = params["min_notice_days"]
    if ci.notice_days < threshold:
        return "amber", f"Renewal notice window ({ci.notice_days} days) is below the placeholder minimum ({threshold} days)."
    return "green", f"Renewal notice window ({ci.notice_days} days) meets the placeholder minimum ({threshold} days)."


@register("governing_law_preferred_jurisdiction")
def _rule_governing_law(ci, params) -> Tuple[str, str]:
    if not ci.present:
        return "red", "No governing-law clause found -- the applicable jurisdiction is undetermined."
    if ci.jurisdiction is None:
        return "amber", "Governing-law clause found but the jurisdiction could not be grounded."
    preferred = params["preferred_jurisdictions"]
    if ci.jurisdiction not in preferred:
        return "amber", f"Governing law ({ci.jurisdiction}) is not on the preferred jurisdiction list ({preferred})."
    return "green", f"Governing law ({ci.jurisdiction}) is on the preferred jurisdiction list."


@register("post_termination_services_present")
def _rule_post_termination_services(ci, params) -> Tuple[str, str]:
    if not ci.present:
        return "amber", "No post-termination services clause found -- obligations after termination (wind-down, transition, IP transfer) are undetermined."
    return "green", "Post-termination services clause present."


@register("effective_date_present")
def _rule_effective_date(ci, params) -> Tuple[str, str]:
    if not ci.present or ci.date is None:
        return "amber", "No effective date found, or the extracted date could not be grounded."
    return "green", "Effective date present and grounded."


@register("expiration_date_present")
def _rule_expiration_date(ci, params) -> Tuple[str, str]:
    if not ci.present or ci.date is None:
        return "red", "No expiration date found, or the extracted date could not be grounded -- the contract's term end is undetermined."
    return "green", "Expiration date present and grounded."


@register("audit_rights_present")
def _rule_audit_rights(ci, params) -> Tuple[str, str]:
    if not ci.present:
        return "amber", "No audit-rights clause found -- compliance cannot be independently verified."
    return "green", "Audit-rights clause present."
