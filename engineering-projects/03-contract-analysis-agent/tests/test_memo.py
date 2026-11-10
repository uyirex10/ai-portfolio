import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from memo import (  # noqa: E402
    ClauseFindingInput, build_memo_findings, locate_quote, render_json, render_markdown,
)


def test_locate_quote_finds_evidence_within_clause():
    source = "Preamble text. 1. Governing Law. This Agreement is governed by the laws of Delaware.\n2. Term."
    clause_start = source.index("1. Governing Law")
    clause_end = source.index("2. Term")
    quote, start, end = locate_quote(source, clause_start, clause_end, "laws of Delaware")
    assert quote == "laws of Delaware"
    assert source[start:end] == quote


def test_locate_quote_falls_back_to_whole_clause_when_evidence_missing():
    source = "1. Governing Law. This Agreement is governed by Delaware law.\n2. Term."
    clause_start = 0
    clause_end = source.index("2. Term")
    quote, start, end = locate_quote(source, clause_start, clause_end, evidence=None)
    assert quote == source[clause_start:clause_end]
    assert source[start:end] == quote


def test_locate_quote_falls_back_when_evidence_not_actually_in_clause():
    source = "1. Governing Law. This Agreement is governed by Delaware law.\n2. Term."
    clause_start = 0
    clause_end = source.index("2. Term")
    # Evidence claims something not actually in this clause's text.
    quote, start, end = locate_quote(source, clause_start, clause_end, evidence="fabricated nonsense")
    assert quote == source[clause_start:clause_end]
    assert source[start:end] == quote


def test_every_quote_is_a_real_source_substring_at_its_offsets():
    """The required invariant: a quote must always equal
    source[start:end]. This test constructs several findings, including
    one with fabricated evidence and one with no backing clause at all,
    and asserts the invariant holds for every single one -- it would
    fail if locate_quote (or the missing-clause fallback) ever returned
    a quote that wasn't a direct slice."""
    source = (
        "1. Cap On Liability. Liability shall not exceed $10,000 in aggregate.\n"
        "2. Governing Law. This Agreement is governed by the laws of Nevada.\n"
        "3. Audit Rights. Buyer may audit Seller's records annually.\n"
    )
    c1_end = source.index("2. Governing Law")
    c2_end = source.index("3. Audit Rights")
    findings_in = [
        ClauseFindingInput("Cap On Liability", "cap_on_liability_present_and_reasonable", "amber",
                            "below threshold", clause_start=0, clause_end=c1_end, evidence="not exceed $10,000"),
        ClauseFindingInput("Governing Law", "governing_law_preferred_jurisdiction", "amber", "not preferred",
                            clause_start=c1_end, clause_end=c2_end, evidence="totally made up text not in the clause"),
        ClauseFindingInput("Audit Rights", "audit_rights_present", "green", "present",
                            clause_start=c2_end, clause_end=len(source), evidence=None),
        ClauseFindingInput("Notice Period To Terminate Renewal", "renewal_notice_minimum_window", "red",
                            "no renewal-notice clause found"),  # clause_start/end default to None
    ]
    findings = build_memo_findings(source, findings_in, provider=None, skip_green=False)
    assert len(findings) == 4
    for f in findings:
        assert f.quote == source[f.quote_start:f.quote_end], (
            f"quote for rule {f.rule_id} is not a real substring of the source at its own offsets"
        )


def test_missing_clause_finding_has_empty_quote_and_redline_note():
    source = "Some unrelated contract text."
    findings_in = [
        ClauseFindingInput("Notice Period To Terminate Renewal", "renewal_notice_minimum_window", "red",
                            "no renewal-notice clause found"),
    ]
    findings = build_memo_findings(source, findings_in, provider=None)
    assert findings[0].quote == ""
    assert findings[0].quote_start == 0 and findings[0].quote_end == 0
    assert findings[0].redline_suggestion is not None


def test_skip_green_excludes_green_findings_by_default():
    source = "1. Audit Rights. Buyer may audit Seller's records annually."
    findings_in = [
        ClauseFindingInput("Audit Rights", "audit_rights_present", "green", "present",
                            clause_start=0, clause_end=len(source)),
    ]
    findings = build_memo_findings(source, findings_in, provider=None)
    assert findings == []


def test_redline_suggestion_is_none_without_a_provider_for_a_real_clause():
    source = "1. Cap On Liability. No cap specified."
    findings_in = [
        ClauseFindingInput("Cap On Liability", "cap_on_liability_present_and_reasonable", "red", "missing",
                            clause_start=0, clause_end=len(source)),
    ]
    findings = build_memo_findings(source, findings_in, provider=None)
    assert findings[0].redline_suggestion is None


def test_render_markdown_includes_quote_and_marks_redline_as_suggestion():
    source = "1. Cap On Liability. No cap specified."
    findings_in = [
        ClauseFindingInput("Cap On Liability", "cap_on_liability_present_and_reasonable", "red",
                            "missing cap", clause_start=0, clause_end=len(source), evidence=None),
    ]
    findings = build_memo_findings(source, findings_in, provider=None)
    findings[0].redline_suggestion = "Add: Liability shall not exceed $100,000."
    md = render_markdown("Test Contract", findings)
    assert "RED" in md
    assert "Cap On Liability" in md
    assert "No cap specified" in md
    assert "Add: Liability shall not exceed $100,000." in md
    assert "suggestion" in md.lower()


def test_render_markdown_notes_missing_clause_explicitly():
    source = "Unrelated text."
    findings_in = [
        ClauseFindingInput("Governing Law", "governing_law_preferred_jurisdiction", "red", "missing"),
    ]
    findings = build_memo_findings(source, findings_in, provider=None)
    md = render_markdown("Test Contract", findings)
    assert "no clause of this type was found" in md.lower()


def test_render_json_round_trips_quote_offsets():
    source = "1. Audit Rights. No audit clause."
    findings_in = [
        ClauseFindingInput("Audit Rights", "audit_rights_present", "amber", "missing",
                            clause_start=0, clause_end=len(source)),
    ]
    findings = build_memo_findings(source, findings_in, provider=None)
    data = render_json("Test Contract", findings)
    assert data["contract"] == "Test Contract"
    f = data["findings"][0]
    assert source[f["quote_start"]:f["quote_end"]] == f["quote"]
    assert f["redline_is_suggestion"] is True
