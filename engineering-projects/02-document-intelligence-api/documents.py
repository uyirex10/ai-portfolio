"""PDF to text.

Thin on purpose. The only real decisions here are what counts as a document we cannot
read, and making that distinct from a document we read but could not extract from -
they are different failures and the client deserves to be told which one happened.
"""

import io
import pathlib

import pdfplumber

# A text layer this short means we opened the file and got essentially nothing. The
# usual cause is a scanned image with no embedded text, which no amount of retrying
# will fix - it needs OCR, which this service does not do. Failing loudly here is
# better than sending an empty page to the model and paying for it to invent a
# contract out of whitespace.
MIN_USABLE_CHARS = 50


class DocumentError(Exception):
    """The document could not be turned into usable text."""

    def __init__(self, message: str, *, reason: str):
        super().__init__(message)
        self.reason = reason  # machine-readable, for the 422 body


def pdf_to_text(source: str | pathlib.Path | bytes) -> str:
    """Extract text from a PDF given a path or raw bytes.

    Bytes are accepted because the API receives an upload, not a file on disk, and
    writing it to a temp file just to read it back would be pointless I/O.
    """
    handle = io.BytesIO(source) if isinstance(source, bytes) else source
    try:
        with pdfplumber.open(handle) as pdf:
            if not pdf.pages:
                raise DocumentError("The PDF contains no pages.", reason="empty_pdf")
            # Page order is the reading order; join with blank lines so a clause split
            # across a page break does not silently run into the next heading.
            pages = [page.extract_text() or "" for page in pdf.pages]
    except DocumentError:
        raise
    except Exception as exc:
        raise DocumentError(
            f"The file could not be opened as a PDF: {exc}", reason="unreadable_pdf"
        ) from exc

    text = "\n\n".join(p.strip() for p in pages if p.strip()).strip()
    if len(text) < MIN_USABLE_CHARS:
        raise DocumentError(
            "The PDF has no extractable text layer. It is most likely a scan; this "
            "service does not perform OCR.",
            reason="no_text_layer",
        )
    return text
