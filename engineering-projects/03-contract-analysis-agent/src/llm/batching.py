"""Batch clauses by a character budget so there is at most about 1 LLM
call per 20 clauses: a batch closes when it hits either the clause-count
cap or the character-budget cap, whichever comes first (a handful of
very long clauses shouldn't be crammed into one oversized prompt just
because the count hasn't hit 20 yet).
"""

from __future__ import annotations

from typing import List, Sequence, TypeVar

T = TypeVar("T")

MAX_CLAUSES_PER_BATCH = 20
MAX_CHARS_PER_BATCH = 8000


def batch_by_char_budget(
    items: Sequence[T],
    text_of,
    max_per_batch: int = MAX_CLAUSES_PER_BATCH,
    max_chars: int = MAX_CHARS_PER_BATCH,
) -> List[List[T]]:
    batches: List[List[T]] = []
    current: List[T] = []
    current_chars = 0

    for item in items:
        item_len = len(text_of(item))
        if current and (len(current) >= max_per_batch or current_chars + item_len > max_chars):
            batches.append(current)
            current = []
            current_chars = 0
        current.append(item)
        current_chars += item_len

    if current:
        batches.append(current)
    return batches
