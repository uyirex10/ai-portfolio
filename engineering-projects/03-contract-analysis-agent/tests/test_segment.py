import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from segment import segment_contract, flatten  # noqa: E402


def _ids(clauses):
    return [c.id for c in clauses]


def _assert_round_trip(text, clauses):
    for c in flatten(clauses):
        assert c.text == text[c.start:c.end], f"offset mismatch for clause {c.id}"


def test_nested_numbering():
    text = (
        "1. Definitions. Terms are defined below.\n\n"
        "2. Term and Termination.\n\n"
        "2.1 Initial Term. This Agreement commences on the Effective Date.\n\n"
        "2.2 Renewal. This Agreement renews automatically.\n\n"
        "2.2.1 Notice. Either party may decline renewal with 30 days notice.\n\n"
        "3. Governing Law. Delaware law applies.\n"
    )
    clauses = segment_contract(text)
    _assert_round_trip(text, clauses)
    assert _ids(clauses) == ["1", "2", "3"]

    clause_2 = clauses[1]
    assert _ids(clause_2.subclauses) == ["2.1", "2.2"]

    clause_22 = clause_2.subclauses[1]
    assert _ids(clause_22.subclauses) == ["2.2.1"]
    assert clause_22.subclauses[0].heading == "Notice"


def test_missing_headings():
    text = (
        "1. The Company shall deliver the goods within 30 days.\n\n"
        "2. The Buyer shall pay within 15 days of delivery.\n\n"
        "3. Risk of loss passes upon delivery.\n"
    )
    clauses = segment_contract(text)
    _assert_round_trip(text, clauses)
    assert _ids(clauses) == ["1", "2", "3"]
    # No heading text follows these numbers directly (body text starts
    # immediately), so heading should be None rather than mangled text.
    assert clauses[0].heading is None
    assert "Company shall deliver" in clauses[0].text


def test_numbered_list_inside_a_clause_does_not_fragment_top_level():
    text = (
        "1. Definitions. Terms are defined below.\n\n"
        "2. Obligations. The Company shall: (a) deliver on time; "
        "(b) maintain insurance; (c) provide monthly reports.\n\n"
        "3. Term. This Agreement lasts one year.\n"
    )
    clauses = segment_contract(text)
    _assert_round_trip(text, clauses)
    # Exactly three top-level clauses -- the inline (a)/(b)/(c) list must
    # stay nested inside clause 2, never promoted to top level.
    assert _ids(clauses) == ["1", "2", "3"]
    assert _ids(clauses[1].subclauses) == ["a", "b", "c"]


def test_single_lone_paren_marker_is_not_treated_as_a_subclause():
    text = (
        "1. Definitions. Terms are defined below.\n\n"
        "2. Scope. As described in Exhibit A(a), the scope is limited to the "
        "listed services.\n\n"
        "3. Term. One year.\n"
    )
    clauses = segment_contract(text)
    _assert_round_trip(text, clauses)
    assert _ids(clauses) == ["1", "2", "3"]
    assert clauses[1].subclauses == []


def test_all_caps_headings_no_numbering():
    text = (
        "RECITALS\n\n"
        "WHEREAS the parties wish to enter into this Agreement.\n\n"
        "CONFIDENTIALITY\n\n"
        "Each party shall keep the other's information confidential.\n\n"
        "GOVERNING LAW\n\n"
        "This Agreement is governed by the laws of New York.\n"
    )
    clauses = segment_contract(text)
    _assert_round_trip(text, clauses)
    assert [c.heading for c in clauses] == ["RECITALS", "CONFIDENTIALITY", "GOVERNING LAW"]


def test_all_caps_heading_mixed_with_numbered_sections():
    text = (
        "1. Definitions. Terms are defined below.\n\n"
        "2. Term. This Agreement lasts one year.\n\n"
        "MISCELLANEOUS\n\n"
        "This section contains general provisions.\n"
    )
    clauses = segment_contract(text)
    _assert_round_trip(text, clauses)
    assert _ids(clauses) == ["1", "2", "3"]
    assert clauses[2].heading == "MISCELLANEOUS"


def test_article_and_section_styles():
    text = (
        "ARTICLE I DEFINITIONS\n\n"
        "The following terms have the meanings set forth below.\n\n"
        "ARTICLE II TERM AND TERMINATION\n\n"
        "SECTION 2.1 Initial Term. This Agreement commences on signing.\n\n"
        "ARTICLE III GOVERNING LAW\n\n"
        "This Agreement is governed by Delaware law.\n"
    )
    clauses = segment_contract(text)
    _assert_round_trip(text, clauses)
    assert _ids(clauses) == ["I", "II", "III"]
    assert clauses[1].heading == "TERM AND TERMINATION"


def test_page_break_noise_does_not_create_spurious_clauses():
    text = (
        "1. Definitions. Terms are defined below. This clause continues "
        "across a simulated page break.\n\n"
        "Page 1 of 10\n\n"
        "The definitions continue here without interruption.\n\n"
        "2. Term. This Agreement lasts one year.\n\n"
        "Page 2 of 10\n\n"
        "3. Governing Law. Delaware law applies.\n"
    )
    clauses = segment_contract(text)
    _assert_round_trip(text, clauses)
    assert _ids(clauses) == ["1", "2", "3"]
    # The page-break noise must remain inside clause 1's text (nothing is
    # dropped), but must not have spawned its own clause or heading.
    assert "Page 1 of 10" in clauses[0].text


def test_single_line_contract_no_newlines():
    # Mirrors real CUAD files where the whole contract is one long line.
    text = (
        "This Agreement is entered into by A and B. 1. Definitions. "
        "Terms are defined below. 2. Term. This Agreement lasts one year. "
        "3. Governing Law. Delaware law applies."
    )
    clauses = segment_contract(text)
    _assert_round_trip(text, clauses)
    assert _ids(clauses) == ["0", "1", "2", "3"]


def test_inconsistent_numbering_restart_and_gap():
    # Real contracts (amendments, scanned exhibits) sometimes skip or
    # restart numbers; the splitter must not crash and must still produce
    # one clause per detected heading rather than merging or dropping any.
    text = (
        "1. Definitions. Terms are defined below.\n\n"
        "3. Term. This Agreement lasts one year.\n\n"
        "3. Governing Law. Delaware law applies.\n"
    )
    clauses = segment_contract(text)
    _assert_round_trip(text, clauses)
    assert _ids(clauses) == ["1", "3", "3"]


def test_empty_text_returns_no_clauses():
    assert segment_contract("") == []


def test_no_structure_at_all_returns_single_clause():
    text = "This is a short agreement with no headings or numbering of any kind."
    clauses = segment_contract(text)
    _assert_round_trip(text, clauses)
    assert len(clauses) == 1
    assert clauses[0].text == text


def test_allcaps_disclaimer_sentence_is_not_mistaken_for_a_heading():
    # Real-world shape (found via CUAD PDF profiling): a liability
    # disclaimer written entirely in caps, where every sentence restart
    # after a period looks like a fresh ALL-CAPS heading unless the
    # splitter recognizes it's still inside the same clause.
    text = (
        "13.4 Limitation of Liability\n\n"
        "a) IN NO EVENT SHALL EITHER PARTY BE LIABLE FOR ANY SPECIAL, CONSEQUENTIAL, "
        "PUNITIVE, INCIDENTAL OR INDIRECT DAMAGES, OR LOST PROFITS, HOWEVER CAUSED, ON ANY "
        "THEORY OF LIABILITY. THIS LIMITATION WILL APPLY EVEN IF THE OTHER PARTY HAS BEEN "
        "ADVISED OF THE POSSIBILITY OF SUCH DAMAGE.\n\n"
        "14. Governing Law.\n\n"
        "This Agreement is governed by the laws of Delaware.\n"
    )
    clauses = segment_contract(text)
    _assert_round_trip(text, clauses)
    assert _ids(clauses) == ["0", "14"]
    assert "THIS LIMITATION WILL APPLY" in clauses[0].text


def test_real_allcaps_headings_still_split_even_after_an_allcaps_disclaimer():
    text = (
        "LIMITATION OF LIABILITY\n\n"
        "IN NO EVENT SHALL EITHER PARTY BE LIABLE FOR ANY SPECIAL, CONSEQUENTIAL OR "
        "INCIDENTAL DAMAGES. THIS LIMITATION APPLIES EVEN IF A PARTY HAS BEEN ADVISED OF "
        "THE POSSIBILITY OF SUCH DAMAGES.\n\n"
        "TERMINATION\n\n"
        "Either party may terminate this Agreement upon 30 days written notice.\n\n"
        "GOVERNING LAW\n\n"
        "This Agreement is governed by the laws of Delaware.\n"
    )
    clauses = segment_contract(text)
    _assert_round_trip(text, clauses)
    assert [c.heading for c in clauses] == ["LIMITATION OF LIABILITY", "TERMINATION", "GOVERNING LAW"]


def test_dollar_amounts_and_dates_do_not_trigger_false_boundaries():
    text = (
        "1. Payment. The Buyer shall pay $10.50 per unit, due by 1.15.2024, "
        "and a late fee of 2.5% per month.\n\n"
        "2. Term. One year.\n"
    )
    clauses = segment_contract(text)
    _assert_round_trip(text, clauses)
    assert _ids(clauses) == ["1", "2"]
    assert "$10.50" in clauses[0].text
    assert clauses[0].subclauses == []
