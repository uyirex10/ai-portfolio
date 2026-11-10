"""Stage G: clause-level evaluation.

Gold labels (a clause counts as positive for type T if it overlaps
>=50% of any labeled T span) need only the frozen splitter and CUAD's
labels -- no LLM call, always computable, and computed for real here.

Precision/recall/F1 need PREDICTIONS from a real classifier run, which
needs a live LLM call. No API key was available this session (see
STATUS.md) -- this script attempts the real run, and if every call
fails for that reason, it says so explicitly in the report rather than
substituting fabricated numbers. The only LLM output anywhere in this
report comes from the 2 contracts hand-seeded by
scripts/seed_demo_cache.py, and is labeled as a smoke test of the
harness, never as the dev or test measurement.

Value-extraction accuracy against CUAD's labeled values is NOT
measured anywhere in this project -- CUAD's labels are clause SPANS,
not structured values, so there is no ground truth to check extracted
amounts/dates/jurisdictions against. Only whether an extracted value is
grounded in its own clause (ground_check) is measured.
"""

from __future__ import annotations

import ast
import csv
import sys
from collections import defaultdict
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
from provider import GeminiProvider, QuotaExceededError, RateLimitedError  # noqa: E402
from schemas import CLAUSE_TYPES  # noqa: E402
from span_integrity import is_omitted  # noqa: E402
from eval_metrics import is_gold_positive, classify_error  # noqa: E402
import pipeline  # noqa: E402

CSV_PATH = ROOT / "cuad_data" / "CUAD_v1" / "master_clauses.csv"
PDF_DIR = ROOT / "cuad_data" / "CUAD_v1" / "full_contract_pdf"
DEV_FILE = ROOT / "data_splits" / "dev_contracts.txt"


def load_csv_rows():
    with open(CSV_PATH, encoding="utf-8") as f:
        reader = csv.reader(f)
        header = next(reader)
        return header, list(reader)


def find_gold_spans_for_contract(header, row, text: str) -> dict:
    """clause_type -> list of (start, end) spans located in `text`."""
    sys.path.insert(0, str(ROOT / "scripts"))
    from span_integrity import find_span

    norm_cache = {}
    spans_by_type = {t: [] for t in CLAUSE_TYPES}
    for cat in CLAUSE_TYPES:
        col_idx = header.index(cat)
        raw = row[col_idx].strip()
        if not raw or raw == "[]":
            continue
        try:
            items = ast.literal_eval(raw)
        except Exception:
            items = [raw]
        for span_text in items:
            span_text = span_text.strip() if isinstance(span_text, str) else str(span_text)
            if not span_text or is_omitted(span_text):
                continue
            found = find_span(text, span_text, norm_cache)
            if found is not None:
                spans_by_type[cat].append(found)
    return spans_by_type


def compute_gold_for_dev():
    """Returns {clause_type: {"support": int, "total_clauses": int}} and
    the raw per-contract gold maps for later error analysis, all without
    any LLM call."""
    header, rows = load_csv_rows()
    idx_filename = header.index("Filename")
    dev_stems = set(s.strip() for s in DEV_FILE.read_text(encoding="utf-8").splitlines() if s.strip())
    pdf_map = {p.stem: p for p in PDF_DIR.rglob("*.[pP][dD][fF]")}
    rows_by_stem = {Path(r[idx_filename]).stem: r for r in rows}

    support = {t: 0 for t in CLAUSE_TYPES}
    total_clauses = 0
    per_contract = {}  # stem -> (leaves, gold_by_type: clause_type -> {clause_idx: bool}, spans_by_type)

    for stem in dev_stems:
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
        spans_by_type = find_gold_spans_for_contract(header, row, text)

        gold_by_type = {}
        for t in CLAUSE_TYPES:
            spans = spans_by_type[t]
            gold_map = {i: is_gold_positive(c.start, c.end, spans) for i, c in enumerate(leaves)}
            gold_by_type[t] = gold_map
            support[t] += sum(gold_map.values())

        per_contract[stem] = (leaves, gold_by_type, spans_by_type, text)

    return support, total_clauses, per_contract, len(dev_stems)


def attempt_real_predictions(per_contract, limit=None):
    """Tries real classify_clauses calls. Returns (pred_by_contract, blocked, error_message).
    pred_by_contract: stem -> {clause_type: {clause_idx: bool}}."""
    provider = GeminiProvider()
    pred_by_contract = {}
    stems = list(per_contract.keys())
    if limit:
        stems = stems[:limit]

    for stem in stems:
        leaves, gold_by_type, spans_by_type, text = per_contract[stem]
        pairs = [(str(i), c.text) for i, c in enumerate(leaves)]
        try:
            from classify import classify_clauses
            classifications = classify_clauses(pairs, provider)
        except (QuotaExceededError, RateLimitedError, ValueError) as e:
            return pred_by_contract, True, f"{type(e).__name__}: {e}"
        except Exception as e:
            return pred_by_contract, True, f"{type(e).__name__}: {e}"

        pred_by_type = {t: {} for t in CLAUSE_TYPES}
        for cl in classifications:
            idx = int(cl.clause_id)
            for t in CLAUSE_TYPES:
                pred_by_type[t][idx] = t in cl.labels
        pred_by_contract[stem] = pred_by_type

    return pred_by_contract, False, None


def main():
    print("Computing gold labels for the dev set (no LLM call needed)...")
    support, total_clauses, per_contract, n_contracts = compute_gold_for_dev()

    print(f"\nDev contracts with gold labels computed: {len(per_contract)} / {n_contracts} in split")
    print(f"Total leaf clauses across dev set: {total_clauses}\n")
    print(f"{'Clause type':35s} {'gold support':>12s}")
    for t in CLAUSE_TYPES:
        print(f"{t:35s} {support[t]:12d}")

    print("\nAttempting real classification predictions (expected to be blocked, no API key)...")
    pred_by_contract, blocked, error_message = attempt_real_predictions(per_contract, limit=3)

    lines = []
    lines.append("# Dev-set error analysis (Stage G)")
    lines.append("")
    lines.append("## Gold-label support (computed from real data, no LLM needed -- VERIFIED)")
    lines.append("")
    lines.append(f"Dev contracts with gold labels computed: {len(per_contract)} / {n_contracts} in split")
    lines.append(f"Total leaf clauses across dev set: {total_clauses}")
    lines.append("")
    lines.append("| Clause type | Gold support (clauses) |")
    lines.append("|---|---|")
    for t in CLAUSE_TYPES:
        lines.append(f"| {t} | {support[t]} |")
    lines.append("")

    lines.append("## Precision / recall / F1 -- BLOCKED" if blocked else "## Precision / recall / F1")
    lines.append("")
    if blocked:
        lines.append(f"**No real LLM classification predictions could be obtained this session.** "
                      f"Error on first attempted call: `{error_message}`. No `GEMINI_API_KEY` or "
                      f"`ANTHROPIC_API_KEY` was available (confirmed by direct instantiation attempt, "
                      f"not just an env-var check -- see STATUS.md). Precision, recall, F1, and the "
                      f"10 false-positive / 10 false-negative examples per type this section is "
                      f"supposed to contain cannot be produced without real predictions, and are "
                      f"**GUESSED-NOT-PRESENT rather than fabricated.** The gold-label support counts "
                      f"above are real and independent of this blocker -- they describe the data, not "
                      f"a model's performance on it.")
        lines.append("")
        lines.append("Per clause type, the required skeleton (to fill in once a real run is possible):")
        lines.append("")
        for t in CLAUSE_TYPES:
            lines.append(f"### {t}")
            lines.append("")
            lines.append("- Precision: BLOCKED (no predictions)")
            lines.append("- Recall: BLOCKED (no predictions)")
            lines.append("- F1: BLOCKED (no predictions)")
            lines.append(f"- Support: {support[t]} (real)")
            lines.append("- 10 false positives: BLOCKED (no predictions)")
            lines.append("- 10 false negatives: BLOCKED (no predictions)")
            lines.append("- Rex's hypothesis: ")
            lines.append("")
    else:
        # (Not reached this session, but written for when a key is available.)
        lines.append("(Real predictions obtained -- see below.)")

    out_path = ROOT / "reports" / "error_analysis_dev.md"
    out_path.write_text("\n".join(lines), encoding="utf-8")
    print(f"\nWritten: {out_path}")


if __name__ == "__main__":
    main()
