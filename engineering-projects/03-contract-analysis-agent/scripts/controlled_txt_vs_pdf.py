"""Controlled comparison: for contracts that exist as BOTH TXT and PDF,
run the (unmodified) splitter on the TXT text and on the PyMuPDF text of
the *same* contract, and report cut-across / not-found rate per category
side by side. This isolates the effect of extraction format from the
effect of using different documents, which the earlier TXT-set vs
PDF-only-set comparison could not do.

Note: the splitter was tuned (Stage 1) exclusively on these TXT files --
so the TXT-side numbers here are not an independent check, only a
same-document baseline for what the PDF side is being compared against.
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
from span_integrity import CANDIDATE_CATEGORIES, find_span, classify_span  # noqa: E402

CSV_PATH = ROOT / "cuad_data" / "CUAD_v1" / "master_clauses.csv"
TXT_DIR = ROOT / "cuad_data" / "CUAD_v1" / "full_contract_txt"
PDF_DIR = ROOT / "cuad_data" / "CUAD_v1" / "full_contract_pdf"


def pymupdf_extract(path: Path) -> str:
    import pymupdf
    doc = pymupdf.open(path)
    try:
        return "\n".join(page.get_text() for page in doc)
    finally:
        doc.close()


def score(text: str, leaves, header, row, norm_cache) -> dict:
    stats = {cat: {"total": 0, "contained": 0, "cut": 0, "not_found": 0} for cat in CANDIDATE_CATEGORIES}
    for cat in CANDIDATE_CATEGORIES:
        col_idx = header.index(cat)
        raw = row[col_idx].strip()
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
            s = stats[cat]
            s["total"] += 1
            found = find_span(text, span_text, norm_cache)
            if found is None:
                s["not_found"] += 1
                continue
            verdict = classify_span(leaves, found[0], found[1])
            if verdict == "contained":
                s["contained"] += 1
            elif verdict.startswith("cut_across"):
                s["cut"] += 1
            else:
                s["not_found"] += 1
    return stats


def main():
    with open(CSV_PATH, encoding="utf-8") as f:
        reader = csv.reader(f)
        header = next(reader)
        rows = list(reader)
    idx_filename = header.index("Filename")

    txt_map = {p.stem: p for p in TXT_DIR.rglob("*.txt")}
    pdf_map = {p.stem: p for p in PDF_DIR.rglob("*.[pP][dD][fF]")}
    overlap = sorted(set(txt_map) & set(pdf_map))
    print(f"Overlap contracts (both TXT and PDF): {len(overlap)}\n")

    txt_totals = {cat: {"total": 0, "contained": 0, "cut": 0, "not_found": 0} for cat in CANDIDATE_CATEGORIES}
    pdf_totals = {cat: {"total": 0, "contained": 0, "cut": 0, "not_found": 0} for cat in CANDIDATE_CATEGORIES}
    errors = []
    norm_cache_txt, norm_cache_pdf = {}, {}

    rows_by_stem = {Path(r[idx_filename]).stem: r for r in rows}

    for stem in overlap:
        row = rows_by_stem.get(stem)
        if row is None:
            continue
        try:
            txt_text = txt_map[stem].read_text(encoding="utf-8", errors="replace")
            pdf_text = pymupdf_extract(pdf_map[stem])
        except Exception as e:
            errors.append((stem, str(e)[:150]))
            continue

        txt_leaves = flatten(segment_contract(txt_text))
        pdf_leaves = flatten(segment_contract(pdf_text))

        txt_stats = score(txt_text, txt_leaves, header, row, norm_cache_txt)
        pdf_stats = score(pdf_text, pdf_leaves, header, row, norm_cache_pdf)

        for cat in CANDIDATE_CATEGORIES:
            for k in ("total", "contained", "cut", "not_found"):
                txt_totals[cat][k] += txt_stats[cat][k]
                pdf_totals[cat][k] += pdf_stats[cat][k]

    print(f"Read/extract errors: {len(errors)}")
    for n, e in errors[:5]:
        print(f"  {n}: {e}")

    print(f"\n{'Category':30s} | {'TXT: total/cut/nf':>22s} {'cut%':>6s} || "
          f"{'PDF: total/cut/nf':>22s} {'cut%':>6s}")
    print("-" * 100)
    grand_txt = {"total": 0, "cut": 0, "not_found": 0, "contained": 0}
    grand_pdf = {"total": 0, "cut": 0, "not_found": 0, "contained": 0}
    for cat in CANDIDATE_CATEGORIES:
        t, p = txt_totals[cat], pdf_totals[cat]
        for k in grand_txt:
            grand_txt[k] += t[k]
            grand_pdf[k] += p[k]
        t_found = t["contained"] + t["cut"]
        p_found = p["contained"] + p["cut"]
        t_cut_pct = (t["cut"] / t_found * 100) if t_found else 0.0
        p_cut_pct = (p["cut"] / p_found * 100) if p_found else 0.0
        print(f"{cat:30s} | {t['total']:4d}/{t['cut']:4d}/{t['not_found']:4d}{'':>9s} {t_cut_pct:5.1f}% || "
              f"{p['total']:4d}/{p['cut']:4d}/{p['not_found']:4d}{'':>9s} {p_cut_pct:5.1f}%")

    t_found_all = grand_txt["contained"] + grand_txt["cut"]
    p_found_all = grand_pdf["contained"] + grand_pdf["cut"]
    t_cut_all = (grand_txt["cut"] / t_found_all * 100) if t_found_all else 0.0
    p_cut_all = (grand_pdf["cut"] / p_found_all * 100) if p_found_all else 0.0
    print("-" * 100)
    print(f"{'OVERALL':30s} | {grand_txt['total']:4d}/{grand_txt['cut']:4d}/{grand_txt['not_found']:4d}"
          f"{'':>9s} {t_cut_all:5.1f}% || "
          f"{grand_pdf['total']:4d}/{grand_pdf['cut']:4d}/{grand_pdf['not_found']:4d}{'':>9s} {p_cut_all:5.1f}%")
    print("\n(cut% is computed among spans that were FOUND -- contained + cut -- in that version of the text)")


if __name__ == "__main__":
    main()
