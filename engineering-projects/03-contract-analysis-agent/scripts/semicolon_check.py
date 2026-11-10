"""Stage A, step 2: before applying the U+037E->';' character map, check
whether the 2.29x length gap found in scripts/unexplained_bucket.py
(not-found dev spans are longer on average than found spans) was really
just a side effect of semicolon count -- i.e. is "contains more
semicolons" a better explanation than "is longer", given longer spans
naturally have more chances to contain one?

Uses RAW (unmapped) PyMuPDF extraction deliberately, via the OLD
fold-only harness (quote/dash/nbsp, no U+037E), to measure the effect
the character map in src/extract.py is about to remove.
"""

from __future__ import annotations

import ast
import csv
import statistics
import sys
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except AttributeError:
    pass

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

from span_integrity import CANDIDATE_CATEGORIES, find_span, is_omitted, load_csv_rows  # noqa: E402

PDF_DIR = ROOT / "cuad_data" / "CUAD_v1" / "full_contract_pdf"
DEV_FILE = ROOT / "data_splits" / "dev_contracts.txt"


def raw_pymupdf_extract(path: Path) -> str:
    """Deliberately RAW -- no character map -- to measure its effect."""
    import pymupdf
    doc = pymupdf.open(path)
    try:
        return "\n".join(page.get_text() for page in doc)
    finally:
        doc.close()


def dev_pdf_map():
    dev_stems = set(s.strip() for s in DEV_FILE.read_text(encoding="utf-8").splitlines() if s.strip())
    pdf_map = {p.stem: p for p in PDF_DIR.rglob("*.[pP][dD][fF]")}
    return {k: v for k, v in pdf_map.items() if k in dev_stems}


def main():
    header, rows = load_csv_rows()
    idx_filename = header.index("Filename")
    dev_map = dev_pdf_map()

    text_cache, norm_cache = {}, {}
    found_semis, not_found_semis = [], []
    found_lens, not_found_lens = [], []

    for r in rows:
        stem = Path(r[idx_filename]).stem
        path = dev_map.get(stem)
        if path is None:
            continue
        if stem not in text_cache:
            try:
                text_cache[stem] = raw_pymupdf_extract(path)
            except Exception:
                text_cache[stem] = None
        text = text_cache[stem]
        if text is None:
            continue

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
                n_semi = span_text.count(";")
                found = find_span(text, span_text, norm_cache)
                if found is not None:
                    found_semis.append(n_semi)
                    found_lens.append(len(span_text))
                else:
                    not_found_semis.append(n_semi)
                    not_found_lens.append(len(span_text))

    print("=" * 70)
    print("SEMICOLON COUNT: FOUND vs NOT-FOUND dev spans (pre-character-map, RAW PyMuPDF text)")
    print("=" * 70)
    print(f"found:     n={len(found_semis)}, mean semicolons/span={statistics.mean(found_semis):.3f}, "
          f"mean length={statistics.mean(found_lens):.0f}")
    print(f"not_found: n={len(not_found_semis)}, mean semicolons/span={statistics.mean(not_found_semis):.3f}, "
          f"mean length={statistics.mean(not_found_lens):.0f}")

    semi_ratio = statistics.mean(not_found_semis) / max(statistics.mean(found_semis), 1e-9)
    len_ratio = statistics.mean(not_found_lens) / max(statistics.mean(found_lens), 1e-9)
    print(f"\nnot-found spans have {semi_ratio:.2f}x the mean semicolon count of found spans")
    print(f"not-found spans have {len_ratio:.2f}x the mean length of found spans (for reference)")

    # Semicolons per 100 chars, to separate "has more semicolons because
    # it's longer" from "has a higher semicolon RATE regardless of length".
    found_rate = statistics.mean([s / l * 100 for s, l in zip(found_semis, found_lens) if l])
    nf_rate = statistics.mean([s / l * 100 for s, l in zip(not_found_semis, not_found_lens) if l])
    print(f"\nsemicolons per 100 chars -- found: {found_rate:.3f}, not_found: {nf_rate:.3f} "
          f"({nf_rate / max(found_rate, 1e-9):.2f}x)")

    print("\nCONCLUSION:")
    if semi_ratio > len_ratio * 1.1:
        print(f"VERIFIED: not-found spans carry disproportionately more semicolons ({semi_ratio:.2f}x) than "
              f"their length alone would predict ({len_ratio:.2f}x) -- the length gap found earlier is at "
              f"least partly a semicolon-count effect, not purely a length effect.")
    elif nf_rate > found_rate * 1.1:
        print(f"VERIFIED: not-found spans have a higher semicolon RATE per character ({nf_rate:.3f} vs "
              f"{found_rate:.3f} per 100 chars) -- consistent with semicolon count driving the not-found "
              f"outcome independent of raw length.")
    else:
        print(f"NOT VERIFIED as a distinct effect: the semicolon-count gap ({semi_ratio:.2f}x) tracks the "
              f"length gap ({len_ratio:.2f}x) closely enough that semicolon count looks like a side effect "
              f"of length, not an independent driver -- GUESSED that length is the more fundamental variable.")


if __name__ == "__main__":
    main()
