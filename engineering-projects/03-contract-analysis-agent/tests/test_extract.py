import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from extract import _CHAR_MAP  # noqa: E402
from segment import segment_contract, flatten  # noqa: E402


def _apply_map(raw: str) -> str:
    return "".join(_CHAR_MAP.get(ch, ch) for ch in raw)


def test_char_map_preserves_length():
    raw = "Section 8.1; damages and costs; plus fees."
    mapped = _apply_map(raw)
    assert len(mapped) == len(raw)


def test_char_map_substitutes_one_to_one():
    raw = "a;b c"
    mapped = _apply_map(raw)
    assert mapped == "a;b c"
    assert len(mapped) == len(raw)


def test_char_map_offsets_round_trip():
    raw = "The parties agree; Vendor shall pay $100 per unit."
    mapped = _apply_map(raw)
    # Every index in `raw` still points at the "same" character (mapped
    # or not) in `mapped` -- no shifting.
    for i, ch in enumerate(raw):
        assert mapped[i] == _CHAR_MAP.get(ch, ch)


def test_splitter_stays_offset_exact_on_normalized_text():
    raw = (
        "1. Definitions. Terms are defined below; see Section 2.\n\n"
        "2. Payment. Buyer shall pay within 30 days; time is of the essence.\n"
    )
    text = _apply_map(raw)
    assert len(text) == len(raw)
    clauses = segment_contract(text)
    for c in flatten(clauses):
        assert c.text == text[c.start:c.end]
