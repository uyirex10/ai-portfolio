"""LLM provider interface. Default Gemini Flash, pluggable to Anthropic.

Every call is disk-cached by a hash of (model, prompt) under .cache/llm/,
so a run can be killed and resumed without re-paying for completed calls
-- the cache is checked before any network call, and is deliberately
*not* gitignored, so scripts/demo.py can replay a cached run offline on
a fresh checkout with no API key at all.

Rate limiting: a 429-shaped error is classified as either a per-minute
rate limit (retried with exponential backoff) or a daily quota
exhaustion (raised immediately as QuotaExceededError, not retried --
the caller is expected to fall back to a seeded sample instead of
burning retries against a limit that won't reset for hours).

`src/rules/` and the verdict logic must never import this module or any
LLM client -- see tests/test_llm_isolation.py.
"""

from __future__ import annotations

import hashlib
import json
import os
import random
import time
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Optional

CACHE_DIR = Path(__file__).resolve().parents[2] / ".cache" / "llm"


class QuotaExceededError(Exception):
    """Daily quota exhausted. Do not retry; caller should fall back to a
    seeded stratified sample and say so, per the project's global rule."""


class RateLimitedError(Exception):
    """Per-minute rate limit. Retried internally with backoff; raised
    only if retries are exhausted."""


def _cache_key(model: str, prompt: str) -> str:
    h = hashlib.sha256()
    h.update(model.encode("utf-8"))
    h.update(b"\x00")
    h.update(prompt.encode("utf-8"))
    return h.hexdigest()


def _cache_path(key: str) -> Path:
    return CACHE_DIR / f"{key}.json"


def read_cache(model: str, prompt: str) -> Optional[str]:
    p = _cache_path(_cache_key(model, prompt))
    if not p.exists():
        return None
    return json.loads(p.read_text(encoding="utf-8"))["response"]


def write_cache(model: str, prompt: str, response: str) -> None:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    key = _cache_key(model, prompt)
    _cache_path(key).write_text(
        json.dumps({"model": model, "prompt": prompt, "response": response}, indent=1),
        encoding="utf-8",
    )


class LLMProvider(ABC):
    name: str
    default_model: str

    @abstractmethod
    def _call(self, model: str, prompt: str) -> str:
        """Make the real API call. Must raise QuotaExceededError or
        RateLimitedError (not a bare provider exception) when the
        failure is quota/rate-limit shaped, so complete() can react."""

    def complete(self, prompt: str, model: Optional[str] = None, max_retries: int = 5) -> str:
        model = model or self.default_model
        cached = read_cache(model, prompt)
        if cached is not None:
            return cached

        delay = 1.0
        last_err: Exception | None = None
        for attempt in range(max_retries):
            try:
                response = self._call(model, prompt)
                write_cache(model, prompt, response)
                return response
            except QuotaExceededError:
                raise  # never retry a daily quota failure
            except RateLimitedError as e:
                last_err = e
                if attempt == max_retries - 1:
                    raise
                time.sleep(delay + random.uniform(0, delay * 0.25))
                delay *= 2
        raise last_err or RuntimeError("unreachable")


def _classify_error(exc: Exception) -> Exception:
    msg = str(exc).lower()
    if "quota" in msg and ("day" in msg or "daily" in msg or "per day" in msg):
        return QuotaExceededError(str(exc))
    if "429" in msg or "resource_exhausted" in msg or "rate limit" in msg or "rate_limit" in msg:
        return RateLimitedError(str(exc))
    return exc


class GeminiProvider(LLMProvider):
    name = "gemini"
    default_model = "gemini-2.0-flash"

    def __init__(self, api_key: Optional[str] = None):
        from google import genai
        self._client = genai.Client(api_key=api_key or os.environ.get("GEMINI_API_KEY"))

    def _call(self, model: str, prompt: str) -> str:
        try:
            resp = self._client.models.generate_content(model=model, contents=prompt)
            return resp.text or ""
        except Exception as e:
            classified = _classify_error(e)
            if classified is not e:
                raise classified from e
            raise


class AnthropicProvider(LLMProvider):
    name = "anthropic"
    default_model = "claude-haiku-4-5-20251001"

    def __init__(self, api_key: Optional[str] = None):
        import anthropic
        self._client = anthropic.Anthropic(api_key=api_key or os.environ.get("ANTHROPIC_API_KEY"))

    def _call(self, model: str, prompt: str) -> str:
        try:
            resp = self._client.messages.create(
                model=model, max_tokens=4096, messages=[{"role": "user", "content": prompt}],
            )
            return "".join(getattr(block, "text", "") for block in resp.content)
        except Exception as e:
            classified = _classify_error(e)
            if classified is not e:
                raise classified from e
            raise


def get_provider(name: Optional[str] = None) -> LLMProvider:
    name = (name or os.environ.get("LLM_PROVIDER") or "gemini").lower()
    if name == "gemini":
        return GeminiProvider()
    if name == "anthropic":
        return AnthropicProvider()
    raise ValueError(f"Unknown LLM provider: {name!r}")
