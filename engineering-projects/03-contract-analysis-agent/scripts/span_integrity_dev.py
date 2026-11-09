"""Span integrity, restricted to the dev split of PDF-only contracts
(data_splits/dev_contracts.txt), using PyMuPDF extraction and the same
exact-then-whitespace-normalized matching as scripts/span_integrity.py.
Reports the not-found rate, and for spans still not found after
normalization, prints the span text next to the nearest matching source
text (via difflib) so the mismatch is visible instead of just a count.
"""

from __future__ import annotations

import ast
import csv
import difflib
import sys
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except AttributeError:
    pass

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

from segment import segment_contract, flatten  # noqa: E402
from span_integrity import (  # noqa: E402
    CANDIDATE_CATEGORIES, find_span, classify_span, normalize, build_normalized_map,
)

CSV_PATH = ROOT / "cuad_data" / "CUAD_v1" / "master_clauses.csv"
PDF_DIR = ROOT / "cuad_data" / "CUAD_v1" / "full_contract_pdf"
DEV_FILE = ROOT / "data_splits" / "dev_contracts.txt"


def pymupdf_extract(path: Path) -> str:
    import pymupdf
    doc = pymupdf.open(path)
    try:
        return "\n".join(page.get_text() for page in doc)
    finally:
        doc.close()


def nearest_match(span_text: str, text: str, norm_text: str, index_map: list[int]) -> str:
    norm_span = normalize(span_text)
    sm = difflib.SequenceMatcher(None, norm_span, norm_text, autojunk=False)
    match = sm.find_longest_match(0, len(norm_span), 0, len(norm_text))
    if match.size == 0:
        return "(no overlapping text found at all)"
    orig_start = index_map[match.b]
    orig_end = index_map[min(match.b + match.size - 1, len(index_map) - 1)] + 1
    ctx_start = max(0, orig_start - 60)
    ctx_end = min(len(text), orig_end + 60)
    matched_fragment = norm_span[match.a:match.a + match.size]
    return (f"longest matching fragment ({match.size} chars): {matched_fragment!r}\n"
            f"      source context: ...{text[ctx_start:ctx_end]!r}...")


def main():
    dev_stems = set(s.strip() for s in DEV_FILE.read_text(encoding="utf-8").splitlines() if s.strip())

    with open(CSV_PATH, encoding="utf-8") as f:
        reader = csv.reader(f)
        header = next(reader)
        rows = list(reader)
    idx_filename = header.index("Filename")

    pdf_map = {p.stem: p for p in PDF_DIR.rglob("*.[pP][dD][fF]")}

    per_category = {cat: {"total": 0, "contained": 0, "cut": 0, "not_found": 0} for cat in CANDIDATE_CATEGORIES}
    still_not_found = []  # (category, stem, span_text)
    text_cache, leaf_cache, norm_cache = {}, {}, {}
    read_errors = []

    for r in rows:
        fname = r[idx_filename]
        stem = Path(fname).stem
        if stem not in dev_stems:
            continue
        path = pdf_map.get(stem)
        if path is None:
            continue

        if stem not in text_cache:
            try:
                text_cache[stem] = pymupdf_extract(path)
                leaf_cache[stem] = flatten(segment_contract(text_cache[stem]))
            except Exception as e:
                read_errors.append((stem, str(e)[:150]))
                text_cache[stem] = None
                leaf_cache[stem] = []

        text = text_cache[stem]
        if text is None:
            continue
        leaves = leaf_cache[stem]

        for cat in CANDIDATE_CATEGORIES:
            col_idx = header.index(cat)
            raw = r[col_idx].strip()
            if not raw or raw == "[]":
                continue
            try:
                spans = ast.literal_eval(raw)
            except Exception:
                spans = [raw]

            for span_text in spans:
                span_text = span_text.strip() if isinstance(span_text, str) else str(span_text)
                if not span_text:
                    continue
                stats = per_category[cat]
                stats["total"] += 1
                found = find_span(text, span_text, norm_cache)
                if found is None:
                    stats["not_found"] += 1
                    still_not_found.append((cat, stem, span_text))
                    continue
                verdict = classify_span(leaves, found[0], found[1])
                if verdict == "contained":
                    stats["contained"] += 1
                elif verdict.startswith("cut_across"):
                    stats["cut"] += 1
                else:
                    stats["not_found"] += 1
                    still_not_found.append((cat, stem, span_text))

    print(f"Dev-set contracts: {len(dev_stems)}, read errors: {len(read_errors)}\n")
    print(f"{'Category':30s} {'total':>6s} {'contained':>10s} {'cut-across':>11s} {'not-found':>10s} {'nf%':>6s}")
    grand = {"total": 0, "contained": 0, "cut": 0, "not_found": 0}
    for cat in CANDIDATE_CATEGORIES:
        s = per_category[cat]
        for k in grand:
            grand[k] += s[k]
        nf_pct = (s["not_found"] / s["total"] * 100) if s["total"] else 0.0
        print(f"{cat:30s} {s['total']:6d} {s['contained']:10d} {s['cut']:11d} {s['not_found']:10d} {nf_pct:5.1f}%")
    nf_pct_all = (grand["not_found"] / grand["total"] * 100) if grand["total"] else 0.0
    print(f"{'OVERALL':30s} {grand['total']:6d} {grand['contained']:10d} {grand['cut']:11d} "
          f"{grand['not_found']:10d} {nf_pct_all:5.1f}%\n")

    print("=" * 70)
    print(f"15 STILL-NOT-FOUND EXAMPLES (dev set, out of {len(still_not_found)} total)")
    print("=" * 70)
    for cat, stem, span_text in still_not_found[:15]:
        text = text_cache[stem]
        if id(text) not in norm_cache:
            norm_cache[id(text)] = build_normalized_map(text)
        norm_text, index_map = norm_cache[id(text)]
        print(f"\n[{cat}] {stem}")
        print(f"  SPAN: {span_text[:200]!r}")
        print(f"  {nearest_match(span_text, text, norm_text, index_map)}")


if __name__ == "__main__":
    main()
