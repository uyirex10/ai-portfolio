"""Span-integrity check: for each CUAD-labeled clause span (from
master_clauses.csv) in the 8 candidate categories, locate it in the
source text and report whether it falls fully inside one splitter clause
or is cut across 2+ clauses.

Checked against the finest-grained (leaf, i.e. flattened including
sub-clauses) splitter output, since that's the actual unit a Stage 2
classifier would see -- a label that's correct at the top level but
split across two sub-clauses still isn't a clean training example.

Matching harness (Stage 1.6, step 1): spans are located by exact match
first, then by a whitespace- AND punctuation-folded match (curly quotes,
dashes, non-breaking spaces folded to their plain ASCII equivalents) that
still carries an index map back to the ORIGINAL text -- folding is for
*locating* a span only; the offsets handed back, and everything the
splitter itself ever sees, are always the unmodified original text.
Spans containing CUAD's own "<omitted>" redaction placeholder can never
match any real document and are excluded from every denominator, but
counted and reported separately (as a "dropped" rate) rather than
silently discarded.

TXT set (200 contracts) was never part of the PDF-only dev/test split
and remains free to use. The PDF-only set's `main()` here is DEV-ONLY
(data_splits/dev_contracts.txt) -- the sealed test split is never read
by this module.
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
from extract import extract_pdf_text as pymupdf_extract  # noqa: E402

CSV_PATH = ROOT / "cuad_data" / "CUAD_v1" / "master_clauses.csv"
TXT_DIR = ROOT / "cuad_data" / "CUAD_v1" / "full_contract_txt"
PDF_DIR = ROOT / "cuad_data" / "CUAD_v1" / "full_contract_pdf"
DEV_FILE = ROOT / "data_splits" / "dev_contracts.txt"

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

OMITTED_MARKER = "<omitted>"

# Matching-only folds: curly quotes/apostrophes, en/em dash, minus sign,
# non-breaking and typographic spaces -> plain ASCII equivalents. Applied
# to a COPY of the text used only to decide where a span is, never to the
# text handed to the splitter or stored as an offset result.
_FOLD_MAP = {
    "‘": "'", "’": "'", "′": "'",
    "“": '"', "”": '"', "″": '"',
    "–": "-", "—": "-", "−": "-",
    "\xa0": " ", " ": " ", " ": " ", " ": " ",
}


def is_omitted(span_text: str) -> bool:
    return OMITTED_MARKER in span_text


def load_csv_rows():
    with open(CSV_PATH, encoding="utf-8") as f:
        reader = csv.reader(f)
        header = next(reader)
        rows = list(reader)
    return header, rows


def _fold_char(ch: str) -> str:
    return _FOLD_MAP.get(ch, ch)


def normalize(s: str) -> str:
    """Whitespace-collapsed, quote/dash/nbsp-folded form, for matching only."""
    return " ".join("".join(_fold_char(c) for c in s).split())


def build_normalized_map(text: str):
    """Returns (normalized_text, index_map) where index_map[i] is the
    ORIGINAL-text index corresponding to normalized_text[i]. Folding
    (quotes/dashes/nbsp) and whitespace collapsing are both 1-char-in
    operations from the original string's point of view, so a single
    index map covers both."""
    norm_chars = []
    index_map = []
    prev_was_space = True  # treat leading whitespace as already "consumed"
    for i, raw_ch in enumerate(text):
        ch = _fold_char(raw_ch)
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
    """Try exact substring match first, then fold+whitespace-normalized
    match. Returns (start, end) in original `text` coords, or None."""
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

    per_category = {
        cat: {"raw_total": 0, "omitted": 0, "contained": 0, "cut": 0, "not_found": 0}
        for cat in CANDIDATE_CATEGORIES
    }
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
                stats["raw_total"] += 1
                if is_omitted(span_text):
                    stats["omitted"] += 1
                    continue
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

    print(f"\n{'Category':30s} {'raw':>5s} {'drop':>5s} {'drop%':>6s} {'kept':>5s} "
          f"{'contain':>8s} {'cut':>5s} {'nf':>5s} {'contain%':>9s} {'cut%':>6s} {'nf%':>6s}")
    grand = {"raw_total": 0, "omitted": 0, "contained": 0, "cut": 0, "not_found": 0}
    for cat in CANDIDATE_CATEGORIES:
        s = per_category[cat]
        for k in grand:
            grand[k] += s[k]
        kept = s["raw_total"] - s["omitted"]
        drop_pct = (s["omitted"] / s["raw_total"] * 100) if s["raw_total"] else 0.0
        contain_pct = (s["contained"] / kept * 100) if kept else 0.0
        cut_pct = (s["cut"] / kept * 100) if kept else 0.0
        nf_pct = (s["not_found"] / kept * 100) if kept else 0.0
        print(f"{cat:30s} {s['raw_total']:5d} {s['omitted']:5d} {drop_pct:5.1f}% {kept:5d} "
              f"{s['contained']:8d} {s['cut']:5d} {s['not_found']:5d} {contain_pct:8.1f}% "
              f"{cut_pct:5.1f}% {nf_pct:5.1f}%")

    kept_all = grand["raw_total"] - grand["omitted"]
    drop_pct_all = (grand["omitted"] / grand["raw_total"] * 100) if grand["raw_total"] else 0.0
    contain_pct_all = (grand["contained"] / kept_all * 100) if kept_all else 0.0
    cut_pct_all = (grand["cut"] / kept_all * 100) if kept_all else 0.0
    nf_pct_all = (grand["not_found"] / kept_all * 100) if kept_all else 0.0
    print(f"{'OVERALL':30s} {grand['raw_total']:5d} {grand['omitted']:5d} {drop_pct_all:5.1f}% {kept_all:5d} "
          f"{grand['contained']:8d} {grand['cut']:5d} {grand['not_found']:5d} {contain_pct_all:8.1f}% "
          f"{cut_pct_all:5.1f}% {nf_pct_all:5.1f}%\n")

    return per_category, grand


def main():
    header, rows = load_csv_rows()

    txt_map = {p.stem: p for p in TXT_DIR.rglob("*.txt")}
    txt_results, txt_grand = run_for_dataset("TXT SET (200 contracts)", header, rows, txt_map)

    dev_stems = set(s.strip() for s in DEV_FILE.read_text(encoding="utf-8").splitlines() if s.strip())
    pdf_map = {p.stem: p for p in PDF_DIR.rglob("*.[pP][dD][fF]")}
    dev_map = {k: v for k, v in pdf_map.items() if k in dev_stems}  # DEV ONLY -- test split never read

    pdf_results, pdf_grand = run_for_dataset(
        f"PDF DEV SET ({len(dev_map)} contracts, PyMuPDF extraction)", header, rows, dev_map, extractor=pymupdf_extract,
    )

    out = {
        "txt": {cat: s for cat, s in txt_results.items()},
        "txt_overall": txt_grand,
        "pdf_dev": {cat: s for cat, s in pdf_results.items()},
        "pdf_dev_overall": pdf_grand,
    }
    out_path = ROOT / "cuad_data" / "span_integrity_results.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(out, f, indent=1)
    print(f"Raw results written to {out_path}")


if __name__ == "__main__":
    main()
