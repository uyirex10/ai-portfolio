import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src" / "llm"))

from extract_values import extract_clause_values, ground_check, parse_extraction_response  # noqa: E402
from provider import LLMProvider  # noqa: E402
from schemas import ExtractedValues  # noqa: E402


class _ScriptedProvider(LLMProvider):
    name = "scripted"
    default_model = "scripted-model"

    def __init__(self, response: str):
        self._response = response

    def _call(self, model, prompt):
        return self._response


@pytest.fixture(autouse=True)
def _isolated_cache(tmp_path, monkeypatch):
    import provider as provider_mod
    monkeypatch.setattr(provider_mod, "CACHE_DIR", tmp_path / "cache")
    yield


def test_ground_check_keeps_values_that_appear_in_clause_text():
    clause = "Either party may terminate this Agreement upon 30 days written notice."
    values = ExtractedValues(notice_days=30, evidence="upon 30 days written notice")
    checked = ground_check(values, clause)
    assert checked.notice_days == 30
    assert checked.evidence == "upon 30 days written notice"
    assert checked.grounded is True
    assert checked.ungrounded_fields == []


def test_ground_check_nulls_fabricated_values():
    clause = "Either party may terminate this Agreement upon 30 days written notice."
    values = ExtractedValues(notice_days=90, jurisdiction="Delaware", evidence="90 days notice period")
    checked = ground_check(values, clause)
    assert checked.notice_days is None
    assert checked.jurisdiction is None
    assert checked.evidence is None
    assert checked.grounded is False
    assert set(checked.ungrounded_fields) == {"notice_days", "jurisdiction", "evidence"}


def test_ground_check_handles_formatted_numbers():
    clause = "The aggregate liability shall not exceed $50,000 in any calendar year."
    values = ExtractedValues(amount=50000.0, currency="$", evidence="shall not exceed $50,000")
    checked = ground_check(values, clause)
    assert checked.amount == 50000.0
    assert checked.grounded is True


def test_parse_extraction_response_handles_malformed_json():
    values = parse_extraction_response("not json")
    assert values.amount is None
    assert values.evidence is None


def test_parse_extraction_response_treats_empty_string_as_null():
    response = json.dumps({"jurisdiction": "", "notice_days": 30})
    values = parse_extraction_response(response)
    assert values.jurisdiction is None
    assert values.notice_days == 30


def test_extract_clause_values_end_to_end_grounds_real_value():
    clause_text = "Governing Law. This Agreement is governed by the laws of the State of Delaware."
    response = json.dumps({
        "amount": None, "currency": None, "duration_value": None, "duration_unit": None,
        "notice_days": None, "jurisdiction": "Delaware", "date": None,
        "evidence": "governed by the laws of the State of Delaware",
    })
    provider = _ScriptedProvider(response)
    result = extract_clause_values("c1", "Governing Law", clause_text, provider)
    assert result.values.jurisdiction == "Delaware"
    assert result.values.grounded is True


def test_extract_clause_values_end_to_end_nulls_fabricated_value():
    clause_text = "Governing Law. This Agreement is governed by the laws of the State of Delaware."
    response = json.dumps({
        "amount": None, "currency": None, "duration_value": None, "duration_unit": None,
        "notice_days": None, "jurisdiction": "California", "date": None,
        "evidence": "governed by the laws of California",
    })
    provider = _ScriptedProvider(response)
    result = extract_clause_values("c1", "Governing Law", clause_text, provider)
    assert result.values.jurisdiction is None
    assert result.values.grounded is False
    assert "jurisdiction" in result.values.ungrounded_fields
