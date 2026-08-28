"""Token and cost accounting for one request.

The brief asks what a document costs to run, so tokens are counted across every model
call a request makes - both extraction attempts if the retry fires, plus the
cross-check pass - not just the first one.

Collected through a ContextVar rather than by threading a parameter through every
function. That keeps the generation calls returning plain strings, which is what makes
the retry loop testable with a stubbed generator, and it stays correct under FastAPI,
where each request runs in its own thread or task and gets its own context.
"""

import contextlib
import contextvars
from dataclasses import dataclass
from typing import Iterator

import config

# Rates come from the environment rather than being baked in here, so changing model
# or reacting to a price change is a config edit, not a code change. The real values
# ship in .env.example - they are public list prices, not secrets:
#
#     DOCINTEL_PRICE_INPUT_PER_MTOK=0.25
#     DOCINTEL_PRICE_OUTPUT_PER_MTOK=1.50
#
# Unset, tokens are still recorded in full and only the money is withheld. That is the
# right failure: a cost-per-document figure gets quoted to clients, and a rate that was
# never checked would be wrong silently, in the API response and in the README.
#
# One rate pair covers all calls. MAIN_MODEL and SECOND_PASS_MODEL default to the same
# model; if they are ever pointed at different ones, this needs to become per-model.
def _rate(name: str) -> float | None:
    raw = config.env(name)
    if not raw:
        return None
    try:
        return float(raw)
    except ValueError:
        return None


@dataclass
class Usage:
    """What one request spent."""

    calls: int = 0
    prompt_tokens: int = 0
    output_tokens: int = 0

    @property
    def total_tokens(self) -> int:
        return self.prompt_tokens + self.output_tokens

    @property
    def cost_usd(self) -> float | None:
        """Cost in USD, or None when the rates are not configured."""
        price_in = _rate("DOCINTEL_PRICE_INPUT_PER_MTOK")
        price_out = _rate("DOCINTEL_PRICE_OUTPUT_PER_MTOK")
        if price_in is None or price_out is None:
            return None
        return (
            self.prompt_tokens * price_in + self.output_tokens * price_out
        ) / 1_000_000


_current: contextvars.ContextVar[Usage | None] = contextvars.ContextVar(
    "docintel_usage", default=None
)


@contextlib.contextmanager
def collect() -> Iterator[Usage]:
    """Accumulate every model call made inside this block."""
    usage = Usage()
    token = _current.set(usage)
    try:
        yield usage
    finally:
        _current.reset(token)


def record(response) -> None:
    """Add one Gemini response's usage to the request in progress.

    A no-op outside a collect() block, so the extraction functions stay callable on
    their own - from a test, or from a script - without a context to record into.
    """
    usage = _current.get()
    if usage is None:
        return
    usage.calls += 1
    metadata = getattr(response, "usage_metadata", None)
    if metadata is None:
        return
    usage.prompt_tokens += getattr(metadata, "prompt_token_count", 0) or 0
    usage.output_tokens += getattr(metadata, "candidates_token_count", 0) or 0
