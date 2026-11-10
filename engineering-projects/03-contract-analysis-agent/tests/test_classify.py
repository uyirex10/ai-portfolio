import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src" / "llm"))

from batching import batch_by_char_budget  # noqa: E402
from classify import build_classification_prompt, classify_clauses, parse_classification_response  # noqa: E402
from provider import LLMProvider  # noqa: E402
from schemas import CLAUSE_TYPES  # noqa: E402


class _ScriptedProvider(LLMProvider):
    name = "scripted"
    default_model = "scripted-model"

    def __init__(self, response_fn):
        self._response_fn = response_fn
        self.prompts = []

    def _call(self, model, prompt):
        self.prompts.append(prompt)
        return self._response_fn(prompt)


@pytest.fixture(autouse=True)
def _isolated_cache(tmp_path, monkeypatch):
    import provider as provider_mod
    monkeypatch.setattr(provider_mod, "CACHE_DIR", tmp_path / "cache")
    yield


def test_batch_by_char_budget_respects_count_cap():
    clauses = [(str(i), "x" * 10) for i in range(45)]
    batches = batch_by_char_budget(clauses, text_of=lambda c: c[1], max_per_batch=20, max_chars=10_000)
    assert len(batches) == 3
    assert [len(b) for b in batches] == [20, 20, 5]


def test_batch_by_char_budget_respects_char_cap():
    clauses = [("a", "x" * 6000), ("b", "x" * 6000), ("c", "x" * 100)]
    batches = batch_by_char_budget(clauses, text_of=lambda c: c[1], max_per_batch=20, max_chars=8000)
    # First clause alone already exceeds half the budget; second must start a new batch.
    assert len(batches) == 2
    assert batches[0] == [("a", "x" * 6000)]


def test_parse_classification_response_filters_unknown_types():
    response = json.dumps({"1": [CLAUSE_TYPES[0], "Not A Real Type"], "2": []})
    parsed = parse_classification_response(response, ["1", "2"])
    assert parsed["1"] == [CLAUSE_TYPES[0]]
    assert parsed["2"] == []


def test_parse_classification_response_fails_closed_on_malformed_json():
    parsed = parse_classification_response("not json at all {{{", ["1", "2"])
    assert parsed == {"1": [], "2": []}


def test_parse_classification_response_missing_id_defaults_to_empty():
    response = json.dumps({"1": [CLAUSE_TYPES[0]]})
    parsed = parse_classification_response(response, ["1", "2"])
    assert parsed["2"] == []


def test_classify_clauses_end_to_end_with_scripted_provider():
    clauses = [("c1", "Governing law is Delaware."), ("c2", "Totally unrelated recital text.")]

    def respond(prompt):
        assert '"c1"' in prompt or "c1" in prompt
        return json.dumps({"c1": ["Governing Law"], "c2": []})

    provider = _ScriptedProvider(respond)
    results = classify_clauses(clauses, provider)
    by_id = {r.clause_id: r.labels for r in results}
    assert by_id["c1"] == ["Governing Law"]
    assert by_id["c2"] == []


def test_build_classification_prompt_includes_all_clause_types():
    prompt = build_classification_prompt([("1", "some clause text")])
    for t in CLAUSE_TYPES:
        assert t in prompt
