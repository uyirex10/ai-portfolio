"""Shared PDF text extraction (PyMuPDF), pinned per NOTES.md.

Applies a length-preserving, 1-to-1 character map after extraction:
U+037E (Greek question mark) -> ';' and U+00A0 (non-breaking space) ->
' '. Both are font-encoding artifacts PyMuPDF faithfully reproduces from
the PDF's own glyph mapping (see NOTES.md for how U+037E was found): the
PDF visually renders these as ';' and ' ', so mapping them back is a
correction, not a content change. Every substitution is exactly one
character for one character -- never a deletion, never multi-character
-- so a downstream splitter's character offsets stay valid against this
function's output with no separate index map needed.
"""

from __future__ import annotations

from pathlib import Path

_CHAR_MAP = {
    ";": ";",
    " ": " ",
}


def extract_pdf_text(path: Path | str) -> str:
    import pymupdf

    doc = pymupdf.open(path)
    try:
        raw = "\n".join(page.get_text() for page in doc)
    finally:
        doc.close()
    return "".join(_CHAR_MAP.get(ch, ch) for ch in raw)
