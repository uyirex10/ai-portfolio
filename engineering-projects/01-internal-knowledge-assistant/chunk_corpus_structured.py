import json
import re
import sys
import time
from pathlib import Path
sys.stdout.reconfigure(encoding="utf-8")

import tiktoken
from pypdf import PdfReader

CORPUS_DIR = Path("data/corpus")
CHUNKS_FILE = Path("data/chunks_structured.json")
CHUNK_SIZE = 500
CHUNK_OVERLAP = 50
MIN_CHUNK_TOKENS = 100

# Merging aims for MIN_CHUNK_TOKENS but cannot reach across a page boundary, so
# a page holding only "22" or a run of redaction markers still yields a runt.
# Those are dropped below this floor. It is deliberately far below the merge
# target: a ~50 token chunk such as a redaction notice carries real meaning that
# eval questions depend on, so raising this to MIN_CHUNK_TOKENS would lose them.
DROP_BELOW_TOKENS = 30

DOCUMENT_LIMIT = None  # set to an int to process only the first N documents

# The sub-splitting window advances by STRIDE. A zero or negative stride is the
# one way that loop can spin forever, so the overlap is clamped here instead of
# being trusted to stay below CHUNK_SIZE.
STRIDE = max(1, CHUNK_SIZE - min(CHUNK_OVERLAP, CHUNK_SIZE - 1))

# Contract headings: "ARTICLE IV", "SECTION 3.2", "EXHIBIT A", "7.1 Termination",
# and "29. SEVERABILITY". The optional trailing period matters: without it the
# "29." numbering style is not recognised as a heading at all, so every clause in
# such a document runs together into one segment and gets cut at the token cap.
HEADING_RE = re.compile(
    r"^\s*(?:(?:ARTICLE|SECTION|EXHIBIT|SCHEDULE|APPENDIX|ANNEX)\b|\d+(?:\.\d+)*\s*\.?\s+\S)",
    re.IGNORECASE,
)

# Example selection: prefer a document with cleanly numbered clauses.
EXAMPLE_DOC_HINT = "ADAMSGOLF"
# Adams Golf titles its governing-law clause "25. APPLICABLE LAW", so match that
# wording first and keep "governing law" for documents that use the usual phrase.
EXAMPLE_KEYWORDS = ["applicable law", "governing law", "entire agreement", "termination"]
NUMBERED_CLAUSE_RE = re.compile(r"^\s*\d+(?:\.\d+)*\s*\.?\s+\S")

encoding = tiktoken.get_encoding("cl100k_base")


def normalize_text(text):
    """Fold non-breaking spaces to ordinary spaces.

    pypdf returns these contracts with \xa0 between words. Normalizing once at
    extraction means every consumer downstream -- heading detection, the stored
    chunk text, embeddings, prompts and keyword search -- sees ordinary spaces,
    rather than each having to know about the quirk.
    """
    return text.replace("\xa0", " ")


def split_into_segments(text):
    """Split page text into heading/paragraph segments.

    Returns (segments, heading_found). `heading_found` reports whether any line
    on the page looked like a clause heading, which is what separates a page
    segmented on real structure from one that just gets windowed by token count.

    Iterates a fixed list of lines exactly once, so it always terminates.
    """
    segments = []
    buffer = []
    heading_found = False

    for line in text.splitlines():
        if not line.strip():
            if buffer:
                segments.append("\n".join(buffer))
                buffer = []
            continue

        if HEADING_RE.match(line):
            heading_found = True
            if buffer:
                segments.append("\n".join(buffer))
                buffer = [line]
                continue

        buffer.append(line)

    if buffer:
        segments.append("\n".join(buffer))

    cleaned = [stripped for stripped in (segment.strip() for segment in segments) if stripped]
    return cleaned, heading_found


def merge_short_segments(segments):
    """Combine runs of undersized segments so single-line fragments aren't chunks.

    Deliberately a single forward pass: every input segment is consumed exactly
    once and a merged result is never pushed back onto the input, so the merge
    condition cannot be re-entered by the segment it just produced. That is the
    failure mode a re-scanning merge has -- combining two short segments into a
    result that is still short, then testing it again forever.
    """
    merged = []
    buffer = []
    buffer_tokens = 0

    for segment in segments:
        size = len(encoding.encode(segment))

        if size >= MIN_CHUNK_TOKENS and not buffer:
            merged.append(segment)
            continue

        buffer.append(segment)
        buffer_tokens += size

        if buffer_tokens >= MIN_CHUNK_TOKENS:
            merged.append("\n\n".join(buffer))
            buffer = []
            buffer_tokens = 0

    if buffer:
        # A trailing run that never reached MIN_CHUNK_TOKENS is attached to the
        # previous chunk and accepted as-is. It is not carried forward looking
        # for more text, because there is none left on this page.
        tail = "\n\n".join(buffer)
        if merged:
            merged[-1] = merged[-1] + "\n\n" + tail
        else:
            merged.append(tail)

    return merged


def split_oversized(tokens):
    """Window an oversized token list into pieces of at most CHUNK_SIZE.

    `start` grows by STRIDE, which is clamped to >= 1, so the loop advances on
    every iteration regardless of how CHUNK_SIZE and CHUNK_OVERLAP are set.
    """
    if len(tokens) <= CHUNK_SIZE:
        return [tokens]

    windows = []
    start = 0

    while start < len(tokens):
        windows.append(tokens[start:start + CHUNK_SIZE])
        if start + CHUNK_SIZE >= len(tokens):
            break
        start += STRIDE

    return windows


def searchable(text):
    """Lowercase for keyword matching. Spaces are already normalized on extract."""
    return text.lower()


def pick_examples(all_chunks, wanted=4):
    """Pick chunks that begin with a numbered clause, for eyeballing completeness.

    Deterministic rather than a random sample: the point is to confirm a known
    clause survives as one piece, which a random draw cannot reliably show.
    Adams Golf is preferred because its governing-law clause is a clean case.
    """
    ordered = sorted(
        all_chunks,
        key=lambda chunk: 0 if EXAMPLE_DOC_HINT in chunk["source_file"].upper() else 1,
    )

    picked = []
    used = set()

    for keyword in EXAMPLE_KEYWORDS:
        for index, chunk in enumerate(ordered):
            if index in used or not NUMBERED_CLAUSE_RE.match(chunk["text"]):
                continue
            if keyword in searchable(chunk["text"]):
                picked.append((keyword, chunk))
                used.add(index)
                break
        if len(picked) >= wanted:
            return picked

    # If the keywords came up short, top up with any numbered clause at all.
    for index, chunk in enumerate(ordered):
        if len(picked) >= wanted:
            break
        if index in used or not NUMBERED_CLAUSE_RE.match(chunk["text"]):
            continue
        picked.append(("any numbered clause", chunk))
        used.add(index)

    return picked


pdf_paths = sorted(CORPUS_DIR.glob("*.pdf"))
if DOCUMENT_LIMIT is not None:
    pdf_paths = pdf_paths[:DOCUMENT_LIMIT]

chunks = []
dropped_chunks = 0
naive_chunks = 0
pages_with_headings = 0
pages_with_text = 0
pages_empty = 0
started_at = time.time()

failed_documents = []

for document_number, pdf_path in enumerate(pdf_paths, start=1):
    # Accumulated per document and merged only once the whole document parses.
    # A file that dies on page 30 therefore contributes nothing at all, rather
    # than leaving pages 1-29 in the output as a silently partial document.
    doc_chunks = []
    doc_naive_chunks = 0
    doc_pages_with_text = 0
    doc_pages_with_headings = 0
    doc_pages_empty = 0
    doc_dropped_chunks = 0

    try:
        reader = PdfReader(pdf_path)
        page_count = len(reader.pages)
        print(f"[{document_number}/{len(pdf_paths)}] {pdf_path.name} ({page_count} pages)")

        for page_number, page in enumerate(reader.pages, start=1):
            text = normalize_text(page.extract_text() or "")

            # Same fixed-window logic as chunk_corpus.py, counted over the same
            # extracted text so the two strategies are compared like for like.
            doc_naive_chunks += len(range(0, len(encoding.encode(text)), CHUNK_SIZE))

            raw_segments, heading_found = split_into_segments(text)

            if text.strip():
                doc_pages_with_text += 1
                if heading_found:
                    doc_pages_with_headings += 1
            else:
                doc_pages_empty += 1

            segments = merge_short_segments(raw_segments)

            page_chunks = 0
            page_dropped = 0
            for segment in segments:
                segment_tokens = encoding.encode(segment)

                # Runts that merging could not rescue are discarded here, before
                # windowing, so a dropped segment costs no downstream embedding.
                if len(segment_tokens) < DROP_BELOW_TOKENS:
                    page_dropped += 1
                    doc_dropped_chunks += 1
                    continue

                for token_window in split_oversized(segment_tokens):
                    doc_chunks.append({
                        "text": encoding.decode(token_window),
                        "source_file": pdf_path.name,
                        "page_number": page_number,
                    })
                    page_chunks += 1

            dropped_note = f" ({page_dropped} dropped)" if page_dropped else ""
            print(f"  page {page_number}/{page_count} -> {page_chunks} chunks{dropped_note}", flush=True)

    # Broad by intent: a corrupt or unreadable PDF must cost only its own file.
    # Before this, one bad document aborted the run and discarded every chunk
    # built up to that point, since the JSON is written only after the loop.
    except Exception as exc:
        failed_documents.append((pdf_path.name, f"{type(exc).__name__}: {exc}"))
        print(f"  SKIPPED {pdf_path.name}: {type(exc).__name__}: {exc}", flush=True)
        continue

    chunks.extend(doc_chunks)
    naive_chunks += doc_naive_chunks
    pages_with_text += doc_pages_with_text
    pages_with_headings += doc_pages_with_headings
    pages_empty += doc_pages_empty
    dropped_chunks += doc_dropped_chunks

elapsed = time.time() - started_at

CHUNKS_FILE.parent.mkdir(parents=True, exist_ok=True)
with open(CHUNKS_FILE, "w", encoding="utf-8") as f:
    json.dump(chunks, f, ensure_ascii=False, indent=2)

# Which documents made it into the run, recorded beside the chunks rather than
# inside them: chunks_structured.json has to stay a flat list of chunk objects,
# because downstream scripts index it positionally and those positions are the
# Qdrant point ids. Derived from CHUNKS_FILE rather than hardcoded, so a run
# pointed at a scratch output writes its manifest there too.
MANIFEST_FILE = CHUNKS_FILE.with_name(f"{CHUNKS_FILE.stem}_manifest.json")
with open(MANIFEST_FILE, "w", encoding="utf-8") as f:
    json.dump(
        {
            "documents_found": len(pdf_paths),
            "documents_succeeded": len(pdf_paths) - len(failed_documents),
            "documents_failed": len(failed_documents),
            "failures": [
                {"source_file": name, "error": error}
                for name, error in failed_documents
            ],
        },
        f,
        ensure_ascii=False,
        indent=2,
    )

chunk_sizes = [len(encoding.encode(chunk["text"])) for chunk in chunks]
avg_tokens = sum(chunk_sizes) / len(chunk_sizes) if chunk_sizes else 0

succeeded_documents = len(pdf_paths) - len(failed_documents)

print(f"\nElapsed: {elapsed:.2f}s")
print(f"Documents found:     {len(pdf_paths)}")
print(f"Documents succeeded: {succeeded_documents}")
print(f"Documents failed:    {len(failed_documents)}")
for name, error in failed_documents:
    print(f"    FAILED {name}: {error}")
print(f"Chunks kept: {len(chunks)}")
print(f"Chunks dropped (under {DROP_BELOW_TOKENS} tokens): {dropped_chunks}")
print(f"Chunks before dropping: {len(chunks) + dropped_chunks}")
print(f"Average tokens per chunk: {avg_tokens:.2f}")
if chunk_sizes:
    print(f"Min / max tokens per chunk: {min(chunk_sizes)} / {max(chunk_sizes)}")

fallback_pages = pages_with_text - pages_with_headings
coverage_pct = (pages_with_headings / pages_with_text * 100) if pages_with_text else 0
fallback_pct = (fallback_pages / pages_with_text * 100) if pages_with_text else 0

print("\nClause-boundary coverage (pages with extractable text):")
print(f"  pages with >=1 detected clause boundary: {pages_with_headings}/{pages_with_text} ({coverage_pct:.1f}%)")
print(f"  pages fell back to token windowing:      {fallback_pages}/{pages_with_text} ({fallback_pct:.1f}%)")
print(f"  pages with no extractable text:          {pages_empty}")
print("  Fallback is graceful degradation: those pages still chunk, just on")
print("  token count rather than clause structure.")

print("\nStructured vs naive (chunk_corpus.py) over the same documents:")
print(f"  naive fixed-{CHUNK_SIZE}-token windows: {naive_chunks} chunks")
print(f"  structured segments:                 {len(chunks)} chunks")
print(f"  difference:                          {len(chunks) - naive_chunks:+d} chunks")

for keyword, example in pick_examples(chunks):
    size = len(encoding.encode(example["text"]))
    print(f"\n--- Example chunk (matched on: {keyword}) ---")
    print(f"source_file: {example['source_file']}")
    print(f"page_number: {example['page_number']}")
    print(f"tokens: {size}")
    print(f"text:\n{example['text']}")
