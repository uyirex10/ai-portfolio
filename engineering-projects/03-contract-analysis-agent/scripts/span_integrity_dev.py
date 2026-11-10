"""Dev-set span integrity (fold-aware harness) plus the raw list of
still-not-found (non-omitted) spans, for scripts/unexplained_bucket.py
and scripts/cap_liability_report.py to reuse without re-deriving it.
Never reads data_splits/test_contracts.txt.
"""

from __future__ import annotations

import ast
import csv
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
from extract import extract_pdf_text as pymupdf_extract  # noqa: E402
from span_integrity import (  # noqa: E402
    CANDIDATE_CATEGORIES, find_span, classify_span, is_omitted, run_for_dataset, load_csv_rows,
)

PDF_DIR = ROOT / "cuad_data" / "CUAD_v1" / "full_contract_pdf"
DEV_FILE = ROOT / "data_splits" / "dev_contracts.txt"


def dev_pdf_map():
    dev_stems = set(s.strip() for s in DEV_FILE.read_text(encoding="utf-8").splitlines() if s.strip())
    pdf_map = {p.stem: p for p in PDF_DIR.rglob("*.[pP][dD][fF]")}
    return {k: v for k, v in pdf_map.items() if k in dev_stems}  # DEV ONLY


def collect_not_found(header, rows, dev_map):
    """Returns list of dicts: category, stem, span_text, span_len, text (full doc text)."""
    idx_filename = header.index("Filename")
    text_cache, leaf_cache, norm_cache = {}, {}, {}
    not_found = []

    for r in rows:
        stem = Path(r[idx_filename]).stem
        path = dev_map.get(stem)
        if path is None:
            continue
        if stem not in text_cache:
            try:
                text_cache[stem] = pymupdf_extract(path)
                leaf_cache[stem] = flatten(segment_contract(text_cache[stem]))
            except Exception:
                text_cache[stem] = None
                leaf_cache[stem] = []
        text = text_cache[stem]
        if text is None:
            continue
        leaves = leaf_cache[stem]

        for cat in CANDIDATE_CATEGORIES:
            raw = r[header.index(cat)].strip()
            if not raw or raw == "[]":
                continue
            try:
                spans = ast.literal_eval(raw)
            except Exception:
                spans = [raw]
            for span_text in spans:
                span_text = span_text.strip() if isinstance(span_text, str) else str(span_text)
                if not span_text or is_omitted(span_text):
                    continue
                found = find_span(text, span_text, norm_cache)
                if found is not None and classify_span(leaves, *found) in ("contained",) or (
                    found is not None and classify_span(leaves, *found).startswith("cut_across")
                ):
                    continue  # located (found); not part of the not-found bucket
                not_found.append({"category": cat, "stem": stem, "span_text": span_text, "span_len": len(span_text)})

    return not_found, text_cache


def main():
    header, rows = load_csv_rows()
    dev_map = dev_pdf_map()
    print(f"Dev-set PDF contracts: {len(dev_map)}\n")
    run_for_dataset(f"PDF DEV SET ({len(dev_map)} contracts, PyMuPDF, fold-aware)", header, rows, dev_map,
                     extractor=pymupdf_extract)


if __name__ == "__main__":
    main()
