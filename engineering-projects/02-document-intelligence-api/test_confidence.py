"""Tests for the second-pass cross-check.

Entirely offline: every case builds both passes by hand, so the comparison logic is
tested without a network call, a key, or the model's cooperation. That matters because
the properties asserted here are the ones a client's integration depends on, and they
should not be able to break silently when an unrelated prompt is tweaked.

Run directly:  python test_confidence.py
Written as test_* functions, so pytest collects them unchanged if it is ever added.
"""

import sys
import traceback

import confidence
from confidence import (
    AGREE,
    CONFLICT,
    MISSING,
    REWRITTEN,
    OMITTED,
    UNCHECKED,
    CHECKS,
    SecondPass,
    cross_check,
    verify,
)
from models import CRITICAL_FIELDS, ExtractedContract

# --------------------------------------------------------------------- helpers ---


def contract(
    *,
    parties=(("Northwind Logistics Ltd.", 1.0),),
    dates=(("effective_date", "2026-01-15", 1.0),),
    terms=("Net 30 days from invoice",),
    terms_confidence=1.0,
    renewal=None,
):
    payload = {
        "parties": [{"name": n, "confidence": c} for n, c in parties],
        "key_dates": [
            {"label": lab, "value": val, "confidence": c} for lab, val, c in dates
        ],
        "payment_terms": list(terms),
        "payment_terms_confidence": terms_confidence,
    }
    if renewal:
        label, value, conf = renewal
        payload["renewal_date"] = {"label": label, "value": value, "confidence": conf}
    return ExtractedContract.model_validate(payload)


def second(
    *,
    printed=("Northwind Logistics Ltd.",),
    dates=(("effective_date", "2026-01-15", "15 January 2026"),),
    figures=None,
    renewal=None,
):
    return SecondPass.model_validate(
        {
            "party_names_as_printed": list(printed),
            "key_dates": [
                {"label": lab, "value": val, "as_printed": printed_form}
                for lab, val, printed_form in dates
            ],
            "payment_figures": figures if figures is not None else {"net_days": 30},
            "renewal_date": renewal,
        }
    )


def outcome_for(findings, field, item=None):
    for f in findings:
        if f.field == field and (item is None or f.item == item):
            return f.outcome, f.confidence_after
    raise AssertionError(f"no finding for {field}/{item}: {[f.field for f in findings]}")


# ----------------------------------------------------------------------- tests ---


def test_full_agreement_changes_nothing():
    """A clean document must produce no false alarms."""
    _, findings = cross_check(contract(), second())
    assert all(f.outcome == AGREE for f in findings), [f.outcome for f in findings]
    assert not any(f.lowered for f in findings)


def test_rewritten_party_caps_at_half():
    """The main pass silently repaired the name: unverified, not refuted."""
    _, findings = cross_check(
        contract(parties=(("Northwind Logistics Ltd.", 1.0),)),
        second(printed=("N0rthwind L0gistics Ltd.",)),
    )
    assert outcome_for(findings, "parties") == (REWRITTEN, 0.5)


def test_party_absent_from_verbatim_pass_is_a_conflict():
    """A party a verbatim transcription never saw is a stronger signal than a rewrite,
    and must land in the bottom band rather than the middle one."""
    _, findings = cross_check(
        contract(parties=(("Ghost Holdings SA", 1.0),)),
        second(printed=("Northwind Logistics Ltd.",)),
    )
    assert outcome_for(findings, "parties") == (CONFLICT, 0.2)


def test_conflicting_date_value_caps_at_lowest_band():
    _, findings = cross_check(
        contract(dates=(("expiration_date", "2028-01-14", 1.0),)),
        second(dates=(("expiration_date", "2028-04-01", "1 April 2028"),)),
    )
    assert outcome_for(findings, "key_dates") == (CONFLICT, 0.2)


def test_date_label_the_second_pass_did_not_report_is_missing():
    _, findings = cross_check(
        contract(dates=(("signing_date", "2026-01-15", 1.0),)),
        second(dates=(("effective_date", "2026-01-15", "15 January 2026"),)),
    )
    assert outcome_for(findings, "key_dates") == (MISSING, 0.5)


def test_date_labels_match_despite_formatting():
    """models.py normalizes labels; the comparison must not be defeated by spacing."""
    _, findings = cross_check(
        contract(dates=(("Effective Date", "2026-01-15", 1.0),)),
        second(dates=(("effective_date", "2026-01-15", "15 January 2026"),)),
    )
    assert outcome_for(findings, "key_dates")[0] == AGREE


def test_renewal_date_claimed_by_one_pass_only():
    _, findings = cross_check(
        contract(renewal=("renewal_date", "2027-11-15", 1.0)),
        second(renewal=None),
    )
    assert outcome_for(findings, "renewal_date") == (MISSING, 0.5)


def test_renewal_date_absent_from_both_is_not_scored():
    """Nothing was claimed, so there is nothing to verify and no finding to report."""
    _, findings = cross_check(contract(renewal=None), second(renewal=None))
    assert not [f for f in findings if f.field == "renewal_date"]


def test_payment_terms_match_on_meaning_not_characters():
    """The whole reason payment_terms needs a semantic comparison: these phrasings are
    the same obligation and share almost no characters."""
    phrasings = [
        "Net 30",
        "payment due within 30 days",
        "Payment shall be rendered no later than thirty (30) days from invoice",
    ]
    for phrasing in phrasings:
        _, findings = cross_check(
            contract(terms=(phrasing,)), second(figures={"net_days": 30})
        )
        assert outcome_for(findings, "payment_terms")[0] == AGREE, phrasing


def test_payment_terms_written_in_words_are_understood():
    """Contracts spell numbers out at least as often as they use digits, and a
    digits-only reader scored those as a conflict on a correctly extracted field -
    observed live, not hypothetically."""
    for phrasing, days in [
        ("Invoices are settled within forty-five days of receipt", 45),
        ("Net thirty days", 30),
        ("payment due within sixty days", 60),
        ("settled within ninety nine days", 99),
    ]:
        _, findings = cross_check(
            contract(terms=(phrasing,)), second(figures={"net_days": days})
        )
        assert outcome_for(findings, "payment_terms")[0] == AGREE, phrasing


def test_payment_terms_disagreeing_figure_conflicts():
    _, findings = cross_check(
        contract(terms=("Net 60",)), second(figures={"net_days": 30})
    )
    assert outcome_for(findings, "payment_terms") == (CONFLICT, 0.2)


def test_payment_terms_figure_with_no_support_in_prose_conflicts():
    """The second pass found a discount the main pass never mentioned."""
    _, findings = cross_check(
        contract(terms=("Net 30",)),
        second(figures={"net_days": 30, "discount_percent": 5.0}),
    )
    assert outcome_for(findings, "payment_terms") == (CONFLICT, 0.2)


def test_payment_terms_both_silent_is_agreement():
    _, findings = cross_check(contract(terms=()), second(figures={}))
    assert outcome_for(findings, "payment_terms")[0] == AGREE


def test_payment_terms_prose_but_no_figures_is_missing():
    _, findings = cross_check(contract(terms=("Net 30",)), second(figures={}))
    assert outcome_for(findings, "payment_terms") == (MISSING, 0.5)


def test_empty_key_dates_is_not_scored_when_both_passes_agree_there_are_none():
    """The relative-dates case reaching the cross-check: nothing was claimed and
    nothing was seen, so there is nothing to verify and no finding to raise."""
    _, findings = cross_check(contract(dates=()), second(dates=()))
    assert not [f for f in findings if f.field == "key_dates"]


def test_main_pass_dropping_dates_the_second_pass_saw_is_reported():
    """key_dates has no minimum any more, so an omission is now possible where it
    previously could not be. It has no confidence score to lower, so it is reported
    informationally rather than silently passing."""
    _, findings = cross_check(contract(dates=()), second())
    outcome, _ = outcome_for(findings, "key_dates")
    assert outcome == OMITTED
    finding = [f for f in findings if f.field == "key_dates"][0]
    assert "effective_date" in finding.second_pass
    assert not finding.lowered, "informational only - it must not read as a drop"


def test_cross_check_never_raises_a_score():
    """Agreement is not positive evidence - two passes can share a misreading - so it
    must never promote a score the main pass deliberately set low."""
    low = contract(
        parties=(("Northwind Logistics Ltd.", 0.2),),
        dates=(("effective_date", "2026-01-15", 0.2),),
        terms_confidence=0.2,
    )
    adjusted, _ = cross_check(low, second())
    assert adjusted.parties[0].confidence == 0.2
    assert adjusted.key_dates[0].confidence == 0.2
    assert adjusted.payment_terms_confidence == 0.2


def test_original_contract_is_not_mutated():
    """The caller keeps the main-pass result; the request log needs both sides."""
    original = contract(parties=(("Northwind Logistics Ltd.", 1.0),))
    cross_check(original, second(printed=("N0rthwind L0gistics Ltd.",)))
    assert original.parties[0].confidence == 1.0


def test_result_is_a_valid_contract():
    adjusted, _ = cross_check(contract(), second())
    assert isinstance(adjusted, ExtractedContract)


def test_checks_cover_critical_fields_exactly():
    """A field added to CRITICAL_FIELDS without a comparison must fail loudly here
    rather than be skipped in silence."""
    assert set(CHECKS) == set(CRITICAL_FIELDS)


def test_failed_second_pass_degrades_instead_of_raising():
    """A cross-check that cannot run must not fail the request - the client still gets
    a usable extraction, marked unverified."""
    original = confidence.second_pass
    confidence.second_pass = lambda text: (_ for _ in ()).throw(RuntimeError("boom"))
    try:
        extracted = contract()
        adjusted, findings = verify("some text", extracted)
    finally:
        confidence.second_pass = original
    assert adjusted is extracted
    assert len(findings) == 1 and findings[0].outcome == UNCHECKED
    assert "boom" in findings[0].second_pass


# ---------------------------------------------------------------------- runner ---


def main() -> int:
    tests = [(n, f) for n, f in sorted(globals().items()) if n.startswith("test_")]
    failed = []
    for name, fn in tests:
        try:
            fn()
            print(f"  PASS  {name}")
        except Exception:
            failed.append(name)
            print(f"  FAIL  {name}")
            traceback.print_exc()
    print(f"\n{len(tests) - len(failed)}/{len(tests)} passed")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
