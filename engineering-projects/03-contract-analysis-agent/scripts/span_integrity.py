"""Span-integrity check: for each CUAD-labeled clause span (from
master_clauses.csv) in the 8 candidate categories, locate it in the
source text and report whether it falls fully inside one splitter clause
or is cut across 2+ clauses.

Checked against the finest-grained (leaf, i.e. flattened including
sub-clauses) splitter output, since that's the actual unit a Stage 2
classifier would see -- a label that's correct at the top level but
split across two sub-clauses still isn't a clean training example.

Run separately for the TXT set and the PDF set. For PDF, text is
extracted with PyMuPDF only (not pdfplumber): pdfplumber takes 5-50s per
document (see scripts/profile_pdf_extraction.py), and re-running it a
second time just for this metric wasn't worth the wait -- PyMuPDF's
clause-count profile already tracks pdfplumber's closely enough (see
that script's extractor-agreement section) to stand in here.
"""

from __future__ import annotations

import ast
import csv
import json
import sys
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except AttributeError:
    pass

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from segment import segment_contract, flatten  # noqa: E402

CSV_PATH = ROOT / "cuad_data" / "CUAD_v1" / "master_clauses.csv"
TXT_DIR = ROOT / "cuad_data" / "CUAD_v1" / "full_contract_txt"
PDF_DIR = ROOT / "cuad_data" / "CUAD_v1" / "full_contract_pdf"

CANDIDATE_CATEGORIES = [
    "Governing Law",
    "Anti-Assignment",
    "Cap On Liability",
    "License Grant",
    "Termination For Convenience",
    "Exclusivity",
    "Audit Rights",
    "Non-Compete",
]


def load_csv_rows():
    with open(CSV_PATH, encoding="utf-8") as f:
        reader = csv.reader(f)
        header = next(reader)
        rows = list(reader)
    return header, rows


def normalize(s: str) -> str:
    return " ".join(s.split())


def build_normalized_map(text: str):
    """Returns (normalized_text, index_map) where index_map[i] is the
    original-text index corresponding to normalized_text[i]."""
    norm_chars = []
    index_map = []
    prev_was_space = True  # treat leading whitespace as already "consumed"
    for i, ch in enumerate(text):
        if ch.isspace():
            if not prev_was_space:
                norm_chars.append(" ")
                index_map.append(i)
            prev_was_space = True
        else:
            norm_chars.append(ch)
            index_map.append(i)
            prev_was_space = False
    return "".join(norm_chars).strip(), index_map


def find_span(text: str, span_text: str, norm_cache: dict):
    """Try exact substring match first, then whitespace-normalized match.
    Returns (start, end) in original `text` coords, or None."""
    idx = text.find(span_text)
    if idx != -1:
        return idx, idx + len(span_text)

    if id(text) not in norm_cache:
        norm_cache[id(text)] = build_normalized_map(text)
    norm_text, index_map = norm_cache[id(text)]
    norm_span = normalize(span_text)
    if not norm_span:
        return None
    nidx = norm_text.find(norm_span)
    if nidx == -1:
        return None
    start = index_map[nidx]
    end_norm_idx = nidx + len(norm_span) - 1
    end = index_map[min(end_norm_idx, len(index_map) - 1)] + 1
    return start, end


def classify_span(leaf_clauses, span_start: int, span_end: int) -> str:
    overlapping = [c for c in leaf_clauses if c.start < span_end and c.end > span_start]
    if not overlapping:
        return "no_overlap"
    fully_contained = any(c.start <= span_start and c.end >= span_end for c in overlapping)
    if fully_contained:
        return "contained"
    return f"cut_across_{len(overlapping)}"


def run_for_dataset(label: str, header, rows, filename_to_path, extractor=None):
    print("=" * 70)
    print(f"SPAN INTEGRITY -- {label}")
    print("=" * 70)

    idx_filename = header.index("Filename")
    text_cache: dict[str, str] = {}
    leaf_cache: dict[str, list] = {}
    norm_cache: dict = {}

    per_category = {cat: {"total": 0, "contained": 0, "cut": 0, "not_found": 0} for cat in CANDIDATE_CATEGORIES}
    read_errors = []

    for r in rows:
        fname = r[idx_filename]
        stem = Path(fname).stem
        path = filename_to_path.get(stem)
        if path is None:
            continue

        if stem not in text_cache:
            try:
                if extractor is None:
                    text_cache[stem] = path.read_text(encoding="utf-8", errors="replace")
                else:
                    text_cache[stem] = extractor(path)
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
                    continue
                verdict = classify_span(leaves, found[0], found[1])
                if verdict == "contained":
                    stats["contained"] += 1
                elif verdict.startswith("cut_across"):
                    stats["cut"] += 1
                else:
                    stats["not_found"] += 1  # no_overlap treated as a miss

    print(f"\nRead errors: {len(read_errors)}")
    for n, e in read_errors[:5]:
        print(f"  {n}: {e}")

    print(f"\n{'Category':30s} {'total':>6s} {'contained':>10s} {'cut-across':>11s} {'not-found':>10s} "
          f"{'contain%':>9s}")
    grand = {"total": 0, "contained": 0, "cut": 0, "not_found": 0}
    for cat in CANDIDATE_CATEGORIES:
        s = per_category[cat]
        grand["total"] += s["total"]
        grand["contained"] += s["contained"]
        grand["cut"] += s["cut"]
        grand["not_found"] += s["not_found"]
        pct = (s["contained"] / s["total"] * 100) if s["total"] else 0.0
        print(f"{cat:30s} {s['total']:6d} {s['contained']:10d} {s['cut']:11d} {s['not_found']:10d} {pct:8.1f}%")

    overall_pct = (grand["contained"] / grand["total"] * 100) if grand["total"] else 0.0
    print(f"\n{'OVERALL':30s} {grand['total']:6d} {grand['contained']:10d} {grand['cut']:11d} "
          f"{grand['not_found']:10d} {overall_pct:8.1f}%\n")

    return per_category, grand


def main():
    header, rows = load_csv_rows()

    txt_map = {p.stem: p for p in TXT_DIR.rglob("*.txt")}
    pdf_map = {p.stem: p for p in PDF_DIR.rglob("*.[pP][dD][fF]")}
    pdf_only_map = {k: v for k, v in pdf_map.items() if k not in txt_map}

    txt_results, txt_grand = run_for_dataset("TXT SET (200 contracts)", header, rows, txt_map)

    def pymupdf_extract(path: Path) -> str:
        import pymupdf
        doc = pymupdf.open(path)
        try:
            return "\n".join(page.get_text() for page in doc)
        finally:
            doc.close()

    pdf_results, pdf_grand = run_for_dataset(
        "PDF-ONLY SET (314 contracts, PyMuPDF extraction)", header, rows, pdf_only_map, extractor=pymupdf_extract,
    )

    out = {
        "txt": {cat: s for cat, s in txt_results.items()},
        "txt_overall": txt_grand,
        "pdf": {cat: s for cat, s in pdf_results.items()},
        "pdf_overall": pdf_grand,
    }
    out_path = ROOT / "cuad_data" / "span_integrity_results.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(out, f, indent=1)
    print(f"Raw results written to {out_path}")


if __name__ == "__main__":
    main()
