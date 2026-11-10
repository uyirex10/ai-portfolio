"""Held-out check: run src/segment.py (unchanged) against the 314 CUAD
contracts that exist only as PDF, using two different text extractors
(pdfplumber and PyMuPDF). Reports the same profile stats used for the TXT
set in scripts/profile_splitter.py, plus an extractor-vs-extractor and
PDF-vs-TXT comparison, and dumps raw numbers to JSON for later reuse
(e.g. by the span-integrity script).
"""

from __future__ import annotations

import json
import statistics
import sys
import time
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except AttributeError:
    pass

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from segment import segment_contract, flatten  # noqa: E402
from extract import extract_pdf_text as extract_pymupdf  # noqa: E402

PDF_DIR = ROOT / "cuad_data" / "CUAD_v1" / "full_contract_pdf"
TXT_DIR = ROOT / "cuad_data" / "CUAD_v1" / "full_contract_txt"
OUT_JSON = ROOT / "cuad_data" / "pdf_extraction_profile.json"


def find_pdf_only_contracts():
    txt_stems = {p.stem for p in TXT_DIR.rglob("*.txt")}
    pdfs = sorted(PDF_DIR.rglob("*.[pP][dD][fF]"))
    return [p for p in pdfs if p.stem not in txt_stems]


def extract_pdfplumber(path: Path) -> str:
    import pdfplumber
    with pdfplumber.open(path) as pdf:
        return "\n".join((page.extract_text() or "") for page in pdf.pages)


def profile_text(name: str, text: str) -> dict:
    top_clauses = segment_contract(text)
    all_clauses = flatten(top_clauses)
    top_lengths = [len(c.text) for c in top_clauses]
    leaf_lengths = [len(c.text) for c in all_clauses]
    return {
        "name": name,
        "doc_len": len(text),
        "top_count": len(top_clauses),
        "all_count": len(all_clauses),
        "top_min": min(top_lengths) if top_lengths else 0,
        "top_max": max(top_lengths) if top_lengths else 0,
        "leaf_min": min(leaf_lengths) if leaf_lengths else 0,
        "leaf_max": max(leaf_lengths) if leaf_lengths else 0,
        "headings_found": sum(1 for c in top_clauses if c.heading),
        "non_preamble_min": min([len(c.text) for c in top_clauses if c.id != "0"], default=top_lengths[0] if top_lengths else 0),
    }


def suspicion_score(p: dict) -> tuple[float, str]:
    doc_len = p["doc_len"]
    top_count = p["top_count"]
    if doc_len > 3000 and top_count <= 1:
        return (doc_len / 1000.0, "long document but only 1 top-level clause (likely under-segmented)")
    if top_count > 0:
        avg = doc_len / top_count
        if doc_len > 1500 and avg < 60:
            return (1500.0 / max(avg, 1), f"very short average clause length ({avg:.0f} chars/clause)")
    if p["non_preamble_min"] < 15 and top_count > 2:
        return (100.0 / max(p["non_preamble_min"], 1), f"has a near-empty clause ({p['non_preamble_min']} chars)")
    if doc_len > 0 and p["top_max"] / doc_len > 0.95 and top_count > 1:
        return (p["top_max"] / doc_len * 10, "one clause swallows almost the entire document")
    return (0.0, "")


def report_block(label: str, profiles: list[dict]):
    print("=" * 70)
    print(label)
    print("=" * 70)
    if not profiles:
        print("  (no successful extractions)")
        return
    top_counts = [p["top_count"] for p in profiles]
    print(f"  contracts analyzed: {len(profiles)}")
    print(f"  top-level clause count: min={min(top_counts)}, max={max(top_counts)}, "
          f"mean={statistics.mean(top_counts):.1f}, median={statistics.median(top_counts)}")
    zero_heading = sum(1 for p in profiles if p["top_count"] > 0 and p["headings_found"] == 0)
    single = sum(1 for p in profiles if p["top_count"] == 1)
    many = sum(1 for p in profiles if p["top_count"] > 40)
    print(f"  zero detected headings: {zero_heading}/{len(profiles)}")
    print(f"  collapsed to 1 clause:  {single}/{len(profiles)}")
    print(f"  >40 top-level clauses:  {many}/{len(profiles)}")

    scored = [(suspicion_score(p), p) for p in profiles]
    scored = [(s, r, p) for (s, r), p in scored if s > 0]
    scored.sort(key=lambda x: -x[0])
    print(f"\n  WORST 10:")
    for score, reason, p in scored[:10]:
        print(f"   [{p['name']}] doc_len={p['doc_len']} top_clauses={p['top_count']} "
              f"headings={p['headings_found']} score={score:.1f} -- {reason}")
    print()


def main():
    limit = int(sys.argv[1]) if len(sys.argv) > 1 else None

    pdf_only = find_pdf_only_contracts()
    if limit:
        pdf_only = pdf_only[:limit]
    print(f"Found {len(pdf_only)} PDF-only contracts" + (f" (limited to {limit})" if limit else "") + "\n")

    pp_profiles, fitz_profiles = [], []
    pp_errors, fitz_errors = [], []
    pp_times, fitz_times = [], []
    raw_records = []

    for i, path in enumerate(pdf_only):
        name = path.name
        if i % 25 == 0:
            print(f"... {i}/{len(pdf_only)}", flush=True)

        t0 = time.time()
        try:
            text_pp = extract_pdfplumber(path)
            pp_times.append(time.time() - t0)
            prof = profile_text(name, text_pp)
            pp_profiles.append(prof)
        except Exception as e:
            pp_errors.append((name, str(e)[:150]))
            text_pp = None

        t0 = time.time()
        try:
            text_fitz = extract_pymupdf(path)
            fitz_times.append(time.time() - t0)
            prof2 = profile_text(name, text_fitz)
            fitz_profiles.append(prof2)
        except Exception as e:
            fitz_errors.append((name, str(e)[:150]))
            text_fitz = None

        raw_records.append({
            "name": name,
            "pdfplumber_len": len(text_pp) if text_pp is not None else None,
            "pymupdf_len": len(text_fitz) if text_fitz is not None else None,
            "pdfplumber_top_count": pp_profiles[-1]["top_count"] if text_pp is not None else None,
            "pymupdf_top_count": fitz_profiles[-1]["top_count"] if text_fitz is not None else None,
        })

    print(f"\nDone. pdfplumber errors: {len(pp_errors)}, pymupdf errors: {len(fitz_errors)}")
    for n, e in pp_errors[:5]:
        print(f"  pdfplumber FAILED: {n} -- {e}")
    for n, e in fitz_errors[:5]:
        print(f"  pymupdf FAILED: {n} -- {e}")

    print(f"\nExtraction time -- pdfplumber: total={sum(pp_times):.1f}s mean={statistics.mean(pp_times):.3f}s/doc "
          f"(n={len(pp_times)})")
    print(f"Extraction time -- pymupdf:    total={sum(fitz_times):.1f}s mean={statistics.mean(fitz_times):.3f}s/doc "
          f"(n={len(fitz_times)})\n")

    report_block("PDFPLUMBER-EXTRACTED TEXT -- SPLITTER PROFILE", pp_profiles)
    report_block("PYMUPDF-EXTRACTED TEXT -- SPLITTER PROFILE", fitz_profiles)

    # Extractor-vs-extractor agreement on the same underlying documents.
    both = [r for r in raw_records if r["pdfplumber_len"] is not None and r["pymupdf_len"] is not None]
    if both:
        len_diffs = [abs(r["pdfplumber_len"] - r["pymupdf_len"]) / max(r["pdfplumber_len"], r["pymupdf_len"], 1) for r in both]
        count_diffs = [abs(r["pdfplumber_top_count"] - r["pymupdf_top_count"]) for r in both]
        exact_count_match = sum(1 for d in count_diffs if d == 0)
        print("=" * 70)
        print("PDFPLUMBER vs PYMUPDF -- AGREEMENT ON SAME DOCUMENTS")
        print("=" * 70)
        print(f"  documents extracted by both: {len(both)}")
        print(f"  mean relative text-length difference: {statistics.mean(len_diffs) * 100:.1f}%")
        print(f"  median relative text-length difference: {statistics.median(len_diffs) * 100:.1f}%")
        print(f"  top-level clause count identical: {exact_count_match}/{len(both)}")
        print(f"  mean |clause count difference|: {statistics.mean(count_diffs):.2f}")
        print(f"  max |clause count difference|: {max(count_diffs)}")

    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    with open(OUT_JSON, "w", encoding="utf-8") as f:
        json.dump({
            "pdf_only_count": len(pdf_only),
            "pdfplumber_profiles": pp_profiles,
            "pymupdf_profiles": fitz_profiles,
            "pdfplumber_errors": pp_errors,
            "pymupdf_errors": fitz_errors,
            "raw_records": raw_records,
        }, f, indent=1)
    print(f"\nRaw profile data written to {OUT_JSON}")


if __name__ == "__main__":
    main()
