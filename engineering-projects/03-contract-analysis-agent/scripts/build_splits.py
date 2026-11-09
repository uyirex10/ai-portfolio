"""Build the fixed, seeded splits used from Stage 1.5b onward:

- data_splits/sample_30_contracts.txt: a seed-42 random sample of 30 of
  the PDF-only contracts, for the pdfplumber-vs-PyMuPDF comparison (full
  pdfplumber extraction over all 314 was too slow -- see
  scripts/profile_pdf_extraction.py's timing numbers).
- data_splits/dev_contracts.txt / test_contracts.txt: a seed-42 50/50
  split of all PDF-only contracts. From here on, only dev may be
  inspected case by case; test is aggregate-only.

Real PDF-only count is 314, not the 310 estimated -- split as 157/157
rather than dropping 4 real contracts to force a round 155/155.
"""

import random
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TXT_DIR = ROOT / "cuad_data" / "CUAD_v1" / "full_contract_txt"
PDF_DIR = ROOT / "cuad_data" / "CUAD_v1" / "full_contract_pdf"
SPLITS_DIR = ROOT / "data_splits"


def find_pdf_only_stems():
    txt_stems = {p.stem for p in TXT_DIR.rglob("*.txt")}
    pdf_stems = {p.stem for p in PDF_DIR.rglob("*.[pP][dD][fF]")}
    return sorted(pdf_stems - txt_stems)


def main():
    pdf_only = find_pdf_only_stems()
    print(f"PDF-only contracts found: {len(pdf_only)}")

    sample_30 = random.Random(42).sample(pdf_only, 30)
    sample_30_sorted = sorted(sample_30)

    shuffled = random.Random(42).sample(pdf_only, len(pdf_only))
    half = len(shuffled) // 2
    dev = sorted(shuffled[:half])
    test = sorted(shuffled[half:])
    print(f"dev: {len(dev)}, test: {len(test)}")

    SPLITS_DIR.mkdir(parents=True, exist_ok=True)
    (SPLITS_DIR / "sample_30_contracts.txt").write_text("\n".join(sample_30_sorted) + "\n", encoding="utf-8")
    (SPLITS_DIR / "dev_contracts.txt").write_text("\n".join(dev) + "\n", encoding="utf-8")
    (SPLITS_DIR / "test_contracts.txt").write_text("\n".join(test) + "\n", encoding="utf-8")
    print("Written: sample_30_contracts.txt, dev_contracts.txt, test_contracts.txt")

    overlap_dev_test = set(dev) & set(test)
    overlap_sample_dev = set(sample_30_sorted) & set(dev)
    print(f"dev/test overlap (must be 0): {len(overlap_dev_test)}")
    print(f"sample_30/dev overlap (informational, not required to be 0): {len(overlap_sample_dev)}")


if __name__ == "__main__":
    main()
