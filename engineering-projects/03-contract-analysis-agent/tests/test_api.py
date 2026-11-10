import json
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "src" / "llm"))
sys.path.insert(0, str(ROOT / "src" / "api"))

from provider import LLMProvider  # noqa: E402


class _FakeProvider(LLMProvider):
    name = "fake"
    default_model = "fake-model"

    def _call(self, model, prompt):
        if "Respond with ONLY a JSON object mapping each clause id" in prompt:
            # classification call: label the first clause as Governing Law
            import re
            ids = re.findall(r'Clause "([^"]+)"', prompt)
            return json.dumps({ids[0]: ["Governing Law"]} if ids else {})
        if "Extract operative values" in prompt:
            return json.dumps({
                "amount": None, "currency": None, "duration_value": None, "duration_unit": None,
                "notice_days": None, "jurisdiction": "Delaware", "date": None,
                "evidence": "laws of the State of Delaware",
            })
        if "Suggest a specific redline" in prompt:
            return "Consider revising this clause."
        return "{}"


def _make_test_pdf(tmp_path) -> bytes:
    import pymupdf
    doc = pymupdf.open()
    page = doc.new_page()
    text = (
        "1. Governing Law. This Agreement is governed by the laws of the State of Delaware.\n\n"
        "2. Cap On Liability. No limitation of liability is stated in this Agreement.\n"
    )
    page.insert_text((50, 72), text, fontsize=10)
    path = tmp_path / "test_contract.pdf"
    doc.save(str(path))
    doc.close()
    return path.read_bytes()


@pytest.fixture(autouse=True)
def _isolated_cache(tmp_path, monkeypatch):
    import provider as provider_mod
    monkeypatch.setattr(provider_mod, "CACHE_DIR", tmp_path / "llm_cache")
    yield


@pytest.fixture()
def client(monkeypatch):
    import app as app_mod
    monkeypatch.setattr(app_mod, "get_provider", lambda *a, **k: _FakeProvider())
    monkeypatch.setenv("CONTRACT_AGENT_API_KEYS", "testclient:sk_test_123")
    return TestClient(app_mod.app)


def test_health_check_no_auth_required(client):
    resp = client.get("/v1/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


def test_analyze_requires_api_key(client, tmp_path):
    pdf_bytes = _make_test_pdf(tmp_path)
    resp = client.post("/v1/analyze", files={"file": ("contract.pdf", pdf_bytes, "application/pdf")})
    assert resp.status_code == 401


def test_analyze_rejects_wrong_api_key(client, tmp_path):
    pdf_bytes = _make_test_pdf(tmp_path)
    resp = client.post(
        "/v1/analyze",
        files={"file": ("contract.pdf", pdf_bytes, "application/pdf")},
        headers={"X-API-Key": "wrong-key"},
    )
    assert resp.status_code == 401


def test_analyze_succeeds_with_valid_key_and_mocked_provider(client, tmp_path):
    pdf_bytes = _make_test_pdf(tmp_path)
    resp = client.post(
        "/v1/analyze",
        files={"file": ("contract.pdf", pdf_bytes, "application/pdf")},
        headers={"X-API-Key": "sk_test_123"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["filename"] == "contract.pdf"
    assert data["clause_count"] > 0
    assert any(v["clause_type"] == "Governing Law" for v in data["rule_verdicts"])
    assert "memo" in data
    assert "findings" in data["memo"]


def test_analyze_rejects_empty_upload(client):
    resp = client.post(
        "/v1/analyze",
        files={"file": ("empty.pdf", b"", "application/pdf")},
        headers={"X-API-Key": "sk_test_123"},
    )
    assert resp.status_code == 422
    assert resp.json()["error"] == "empty_upload"


def test_analyze_rejects_non_pdf_garbage(client):
    resp = client.post(
        "/v1/analyze",
        files={"file": ("notapdf.pdf", b"this is not a pdf file at all", "application/pdf")},
        headers={"X-API-Key": "sk_test_123"},
    )
    assert resp.status_code == 422
    assert resp.json()["error"] == "extraction_failed"
