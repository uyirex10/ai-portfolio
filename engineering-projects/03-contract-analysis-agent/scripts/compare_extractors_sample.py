"""pdfplumber vs PyMuPDF on the fixed 30-contract sample
(data_splits/sample_30_contracts.txt). PyMuPDF remains the default
extractor unless pdfplumber is clearly better on this sample.
"""

from __future__ import annotations

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
SAMPLE_FILE = ROOT / "data_splits" / "sample_30_contracts.txt"


def extract_pdfplumber(path: Path) -> str:
    import pdfplumber
    with pdfplumber.open(path) as pdf:
        return "\n".join((page.extract_text() or "") for page in pdf.pages)


def profile(text: str) -> dict:
    top = segment_contract(text)
    leaves = flatten(top)
    return {
        "doc_len": len(text),
        "top_count": len(top),
        "headings_found": sum(1 for c in top if c.heading),
        "leaf_min": min((len(c.text) for c in leaves), default=0),
        "leaf_max": max((len(c.text) for c in leaves), default=0),
    }


def main():
    stems = [s.strip() for s in SAMPLE_FILE.read_text(encoding="utf-8").splitlines() if s.strip()]
    pdf_map = {p.stem: p for p in PDF_DIR.rglob("*.[pP][dD][fF]")}

    rows = []
    pp_times, fitz_times = [], []
    for stem in stems:
        path = pdf_map.get(stem)
        if path is None:
            print(f"MISSING: {stem}")
            continue

        t0 = time.time()
        try:
            text_pp = extract_pdfplumber(path)
            pp_time = time.time() - t0
        except Exception as e:
            print(f"pdfplumber FAILED on {stem}: {e}")
            continue
        pp_times.append(pp_time)

        t0 = time.time()
        try:
            text_fitz = extract_pymupdf(path)
            fitz_time = time.time() - t0
        except Exception as e:
            print(f"pymupdf FAILED on {stem}: {e}")
            continue
        fitz_times.append(fitz_time)

        prof_pp = profile(text_pp)
        prof_fitz = profile(text_fitz)
        rows.append((stem, text_pp, text_fitz, prof_pp, prof_fitz, pp_time, fitz_time))

    print(f"\n{'contract':50s} {'pp_len':>8s} {'fitz_len':>8s} {'pp_top':>7s} {'fitz_top':>8s} "
          f"{'pp_s':>6s} {'fitz_s':>6s}")
    for stem, tpp, tfitz, ppp, pfitz, pt, ft in rows:
        print(f"{stem[:50]:50s} {ppp['doc_len']:8d} {pfitz['doc_len']:8d} {ppp['top_count']:7d} "
              f"{pfitz['top_count']:8d} {pt:6.1f} {ft:6.2f}")

    pp_doc_lens = [p[3]["doc_len"] for p in rows]
    fitz_doc_lens = [p[4]["doc_len"] for p in rows]
    pp_tops = [p[3]["top_count"] for p in rows]
    fitz_tops = [p[4]["top_count"] for p in rows]

    print("\n" + "=" * 70)
    print("SUMMARY")
    print("=" * 70)
    print(f"n = {len(rows)}")
    print(f"total extraction time -- pdfplumber: {sum(pp_times):.1f}s, pymupdf: {sum(fitz_times):.1f}s "
          f"({sum(pp_times) / max(sum(fitz_times), 0.001):.0f}x slower)")
    print(f"mean doc length  -- pdfplumber: {statistics.mean(pp_doc_lens):.0f}, pymupdf: {statistics.mean(fitz_doc_lens):.0f}")
    print(f"mean top clauses -- pdfplumber: {statistics.mean(pp_tops):.1f}, pymupdf: {statistics.mean(fitz_tops):.1f}")

    len_diffs = [abs(a - b) / max(a, b, 1) for a, b in zip(pp_doc_lens, fitz_doc_lens)]
    top_diffs = [abs(a - b) for a, b in zip(pp_tops, fitz_tops)]
    print(f"mean relative length difference: {statistics.mean(len_diffs) * 100:.1f}%")
    print(f"top-clause-count identical on: {sum(1 for d in top_diffs if d == 0)}/{len(rows)}")
    print(f"mean |top-clause-count difference|: {statistics.mean(top_diffs):.2f}")


if __name__ == "__main__":
    main()
