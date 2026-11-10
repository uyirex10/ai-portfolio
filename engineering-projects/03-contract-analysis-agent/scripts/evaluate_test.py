"""Stage G: the sealed TEST split run for the full pipeline, aggregates
only (same discipline as Stage B's splitter-only test run). Gold-label
support is real (no LLM needed); precision/recall/F1/grounding-rate are
BLOCKED this session for the same reason as the dev run -- no API key.
"""

from __future__ import annotations

import sys
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except AttributeError:
    pass

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "src" / "llm"))
sys.path.insert(0, str(ROOT / "scripts"))

from extract import extract_pdf_text  # noqa: E402
from segment import segment_contract, flatten  # noqa: E402
from schemas import CLAUSE_TYPES  # noqa: E402
from provider import GeminiProvider  # noqa: E402
from eval_metrics import is_gold_positive  # noqa: E402
from evaluate import load_csv_rows, find_gold_spans_for_contract  # noqa: E402

PDF_DIR = ROOT / "cuad_data" / "CUAD_v1" / "full_contract_pdf"
TEST_FILE = ROOT / "data_splits" / "test_contracts.txt"  # read ONLY here for Stage G's pipeline eval


def main():
    header, rows = load_csv_rows()
    idx_filename = header.index("Filename")
    test_stems = set(s.strip() for s in TEST_FILE.read_text(encoding="utf-8").splitlines() if s.strip())
    pdf_map = {p.stem: p for p in PDF_DIR.rglob("*.[pP][dD][fF]")}
    rows_by_stem = {Path(r[idx_filename]).stem: r for r in rows}

    support = {t: 0 for t in CLAUSE_TYPES}
    total_clauses = 0
    n_ok = 0

    for stem in test_stems:
        path = pdf_map.get(stem)
        row = rows_by_stem.get(stem)
        if path is None or row is None:
            continue
        try:
            text = extract_pdf_text(path)
        except Exception:
            continue
        leaves = flatten(segment_contract(text))
        total_clauses += len(leaves)
        n_ok += 1
        spans_by_type = find_gold_spans_for_contract(header, row, text)
        for t in CLAUSE_TYPES:
            spans = spans_by_type[t]
            support[t] += sum(1 for c in leaves if is_gold_positive(c.start, c.end, spans))

    try:
        provider = GeminiProvider()
        from classify import classify_clauses
        classify_clauses([("0", "test")], provider)
        blocked = False
        error_message = None
    except Exception as e:
        blocked = True
        error_message = f"{type(e).__name__}: {e}"

    lines = []
    lines.append("# TEST-split pipeline evaluation results (Stage G)")
    lines.append("")
    lines.append("Test split was opened once for this pipeline evaluation, aggregates only; "
                 "no case-level inspection, no tuning against it.")
    lines.append("")
    lines.append(f"Test contracts with gold labels computed: {n_ok} / {len(test_stems)} in split")
    lines.append(f"Total leaf clauses: {total_clauses}")
    lines.append("")
    lines.append("## Gold-label support (real, no LLM needed)")
    lines.append("")
    lines.append("| Clause type | Gold support (clauses) |")
    lines.append("|---|---|")
    for t in CLAUSE_TYPES:
        lines.append(f"| {t} | {support[t]} |")
    lines.append("")
    lines.append("## Precision / recall / F1 / grounding rate -- BLOCKED")
    lines.append("")
    lines.append(f"No real LLM classification predictions could be obtained this session "
                 f"(`{error_message}`). No `GEMINI_API_KEY` or `ANTHROPIC_API_KEY` was available. "
                 f"These numbers are NOT fabricated as a substitute.")
    lines.append("")
    lines.append("## Value-extraction accuracy")
    lines.append("")
    lines.append("Not measured, by design, in this project: CUAD's labels are clause SPANS, not "
                 "structured values, so there is no ground truth to check an extracted amount, date, "
                 "or jurisdiction against. Only whether an extracted value is grounded in its own "
                 "clause text (src/llm/extract_values.py's ground_check) is measured, and that too "
                 "requires a real extraction call this session did not have.")

    out_path = ROOT / "reports" / "eval_test_results.md"
    out_path.write_text("\n".join(lines), encoding="utf-8")
    print("\n".join(lines))
    print(f"\nWritten: {out_path}")


if __name__ == "__main__":
    main()
