import shutil
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import llm.provider as provider_mod  # noqa: E402
from llm.provider import LLMProvider, QuotaExceededError, RateLimitedError  # noqa: E402


class _FakeProvider(LLMProvider):
    name = "fake"
    default_model = "fake-model"

    def __init__(self, responses):
        # responses: list of either a string (success) or an Exception to raise,
        # consumed in order across calls to _call.
        self._responses = list(responses)
        self.call_count = 0

    def _call(self, model, prompt):
        self.call_count += 1
        item = self._responses.pop(0)
        if isinstance(item, Exception):
            raise item
        return item


@pytest.fixture(autouse=True)
def _isolated_cache(tmp_path, monkeypatch):
    cache_dir = tmp_path / "llm_cache"
    monkeypatch.setattr(provider_mod, "CACHE_DIR", cache_dir)
    yield cache_dir
    shutil.rmtree(cache_dir, ignore_errors=True)


def test_successful_call_is_cached_and_reused():
    p = _FakeProvider(["hello world"])
    result1 = p.complete("prompt A")
    assert result1 == "hello world"
    assert p.call_count == 1

    # Second call with the same prompt must hit the cache, not _call again.
    result2 = p.complete("prompt A")
    assert result2 == "hello world"
    assert p.call_count == 1


def test_different_prompts_are_cached_separately():
    p = _FakeProvider(["resp A", "resp B"])
    assert p.complete("prompt A") == "resp A"
    assert p.complete("prompt B") == "resp B"
    assert p.call_count == 2


def test_rate_limit_retries_then_succeeds():
    p = _FakeProvider([RateLimitedError("429 rate limit"), RateLimitedError("429 rate limit"), "finally ok"])
    # Avoid real sleeping during the test.
    import time as time_mod
    orig_sleep = time_mod.sleep
    time_mod.sleep = lambda s: None
    try:
        result = p.complete("prompt")
    finally:
        time_mod.sleep = orig_sleep
    assert result == "finally ok"
    assert p.call_count == 3


def test_rate_limit_exhausts_retries_and_raises():
    p = _FakeProvider([RateLimitedError("429")] * 10)
    import time as time_mod
    orig_sleep = time_mod.sleep
    time_mod.sleep = lambda s: None
    try:
        with pytest.raises(RateLimitedError):
            p.complete("prompt", max_retries=3)
    finally:
        time_mod.sleep = orig_sleep
    assert p.call_count == 3


def test_quota_exceeded_raises_immediately_without_retry():
    p = _FakeProvider([QuotaExceededError("daily quota exhausted"), "should never be reached"])
    with pytest.raises(QuotaExceededError):
        p.complete("prompt")
    assert p.call_count == 1  # no retry attempted


def test_resumable_across_provider_instances():
    """A fresh provider instance (simulating a resumed run) still gets
    the cached response instead of calling the API again."""
    p1 = _FakeProvider(["cached response"])
    assert p1.complete("same prompt") == "cached response"

    p2 = _FakeProvider(["should not be called"])
    assert p2.complete("same prompt") == "cached response"
    assert p2.call_count == 0
