import sys
from pathlib import Path

import pytest
from hypothesis import given, strategies as st

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src" / "rules"))

from engine import evaluate_rule, load_playbook  # noqa: E402
from rule_types import ClauseInput, Verdict  # noqa: E402

PLAYBOOK = {r["id"]: r for r in load_playbook()}


def _result(rule_id, ci):
    return evaluate_rule(PLAYBOOK[rule_id], ci)


# ---- Cap On Liability ----

def test_cap_on_liability_missing_is_red():
    r = _result("cap_on_liability_present_and_reasonable", ClauseInput(present=False))
    assert r.verdict == Verdict.RED


def test_cap_on_liability_ungrounded_amount_is_amber():
    r = _result("cap_on_liability_present_and_reasonable", ClauseInput(present=True, amount=None))
    assert r.verdict == Verdict.AMBER


def test_cap_on_liability_boundary_at_threshold_is_green():
    r = _result("cap_on_liability_present_and_reasonable", ClauseInput(present=True, amount=50000))
    assert r.verdict == Verdict.GREEN


def test_cap_on_liability_just_below_threshold_is_amber():
    r = _result("cap_on_liability_present_and_reasonable", ClauseInput(present=True, amount=49999))
    assert r.verdict == Verdict.AMBER


def test_cap_on_liability_well_above_threshold_is_green():
    r = _result("cap_on_liability_present_and_reasonable", ClauseInput(present=True, amount=1_000_000))
    assert r.verdict == Verdict.GREEN


# ---- Renewal notice ----

def test_renewal_notice_missing_is_red():
    r = _result("renewal_notice_minimum_window", ClauseInput(present=False))
    assert r.verdict == Verdict.RED


def test_renewal_notice_ungrounded_is_amber():
    r = _result("renewal_notice_minimum_window", ClauseInput(present=True, notice_days=None))
    assert r.verdict == Verdict.AMBER


def test_renewal_notice_boundary_at_threshold_is_green():
    r = _result("renewal_notice_minimum_window", ClauseInput(present=True, notice_days=30))
    assert r.verdict == Verdict.GREEN


def test_renewal_notice_just_below_threshold_is_amber():
    r = _result("renewal_notice_minimum_window", ClauseInput(present=True, notice_days=29))
    assert r.verdict == Verdict.AMBER


def test_renewal_notice_zero_days_is_amber_not_green():
    r = _result("renewal_notice_minimum_window", ClauseInput(present=True, notice_days=0))
    assert r.verdict == Verdict.AMBER


# ---- Governing law ----

def test_governing_law_missing_is_red():
    r = _result("governing_law_preferred_jurisdiction", ClauseInput(present=False))
    assert r.verdict == Verdict.RED


def test_governing_law_ungrounded_jurisdiction_is_amber():
    r = _result("governing_law_preferred_jurisdiction", ClauseInput(present=True, jurisdiction=None))
    assert r.verdict == Verdict.AMBER


def test_governing_law_preferred_is_green():
    r = _result("governing_law_preferred_jurisdiction", ClauseInput(present=True, jurisdiction="Delaware"))
    assert r.verdict == Verdict.GREEN


def test_governing_law_non_preferred_is_amber():
    r = _result("governing_law_preferred_jurisdiction", ClauseInput(present=True, jurisdiction="Texas"))
    assert r.verdict == Verdict.AMBER


# ---- Presence-only rules ----

@pytest.mark.parametrize("rule_id,expected_missing", [
    ("termination_for_convenience_present", Verdict.AMBER),
    ("audit_rights_present", Verdict.AMBER),
    ("post_termination_services_present", Verdict.AMBER),
    ("effective_date_present", Verdict.AMBER),
    ("expiration_date_present", Verdict.RED),
])
def test_presence_only_rules_missing_verdict(rule_id, expected_missing):
    ci = ClauseInput(present=False)
    assert _result(rule_id, ci).verdict == expected_missing


@pytest.mark.parametrize("rule_id", [
    "termination_for_convenience_present", "audit_rights_present", "post_termination_services_present",
])
def test_presence_only_rules_present_is_green(rule_id):
    ci = ClauseInput(present=True)
    assert _result(rule_id, ci).verdict == Verdict.GREEN


@pytest.mark.parametrize("rule_id", ["effective_date_present", "expiration_date_present"])
def test_date_rules_present_but_ungrounded_date_is_not_green(rule_id):
    ci = ClauseInput(present=True, date=None)
    assert _result(rule_id, ci).verdict != Verdict.GREEN


@pytest.mark.parametrize("rule_id", ["effective_date_present", "expiration_date_present"])
def test_date_rules_present_and_grounded_is_green(rule_id):
    ci = ClauseInput(present=True, date="2024-01-01")
    assert _result(rule_id, ci).verdict == Verdict.GREEN


# ---- Unknown rule / malformed id -> needs_review, never a crash ----

def test_unregistered_rule_id_returns_needs_review():
    fake_rule_def = {"id": "not_a_real_rule", "clause_type": "Governing Law", "params": {}}
    r = evaluate_rule(fake_rule_def, ClauseInput(present=True))
    assert r.verdict == Verdict.NEEDS_REVIEW


def test_rule_raising_exception_returns_needs_review(monkeypatch):
    import rules as rules_mod

    def _boom(ci, params):
        raise RuntimeError("deliberate failure")

    monkeypatch.setitem(rules_mod.RULE_FUNCS, "cap_on_liability_present_and_reasonable", _boom)
    r = _result("cap_on_liability_present_and_reasonable", ClauseInput(present=True, amount=100))
    assert r.verdict == Verdict.NEEDS_REVIEW


# ---- Property test: no all-None / absent input ever yields green ----

@given(
    rule_id=st.sampled_from(list(PLAYBOOK.keys())),
    present=st.booleans(),
)
def test_property_none_or_absent_input_never_yields_green(rule_id, present):
    """If the clause is absent, or present with every value field None,
    the verdict must never be green -- there is nothing grounded to
    justify a clean pass."""
    ci = ClauseInput(present=present, amount=None, notice_days=None, jurisdiction=None, date=None)
    result = _result(rule_id, ci)
    if not present:
        assert result.verdict != Verdict.GREEN, f"{rule_id} returned green for an absent clause"
    else:
        # Present but every extracted value is None: only the two pure
        # presence-only rules (no value field to check) may be green.
        presence_only = {"termination_for_convenience_present", "audit_rights_present",
                          "post_termination_services_present"}
        if rule_id not in presence_only:
            assert result.verdict != Verdict.GREEN, f"{rule_id} returned green with every value field None"
