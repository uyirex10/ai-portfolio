"""Stage B: run the TEST split exactly once, with the frozen splitter
(whichever caps_fallback_rule Stage A's bake-off chose). Aggregates
only -- no per-contract printing, no case-level inspection. This script
is the one and only place data_splits/test_contracts.txt is read.
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

from segment import segment_contract, flatten  # noqa: E402
from extract import extract_pdf_text  # noqa: E402
from span_integrity import CANDIDATE_CATEGORIES, find_span, is_omitted, load_csv_rows  # noqa: E402

PDF_DIR = ROOT / "cuad_data" / "CUAD_v1" / "full_contract_pdf"
TEST_FILE = ROOT / "data_splits" / "test_contracts.txt"
OUT_PATH = ROOT / "reports" / "splitter_test_results.md"

FROZEN_RULE = "A"  # set by Stage A's pre-registered bake-off choice


def main():
    test_stems = set(s.strip() for s in TEST_FILE.read_text(encoding="utf-8").splitlines() if s.strip())
    pdf_map = {p.stem: p for p in PDF_DIR.rglob("*.[pP][dD][fF]")}
    test_map = {k: v for k, v in pdf_map.items() if k in test_stems}  # TEST ONLY, read here and only here

    header, rows = load_csv_rows()
    idx_filename = header.index("Filename")

    tops_by_stem, leaves_by_stem = {}, {}
    errors = []
    for stem, path in test_map.items():
        try:
            text = extract_pdf_text(path)
        except Exception as e:
            errors.append((stem, str(e)[:150]))
            continue
        tops = segment_contract(text, caps_fallback_rule=FROZEN_RULE)
        tops_by_stem[stem] = tops
        leaves_by_stem[stem] = flatten(tops)

    top_counts = [len(v) for v in tops_by_stem.values()]
    zero_heading = sum(1 for tops in tops_by_stem.values() if tops and not any(c.heading for c in tops))
    collapsed = sum(1 for tops in tops_by_stem.values() if len(tops) == 1)

    per_cat = {cat: {"total": 0, "omitted": 0, "contained": 0, "cut": 0, "not_found": 0,
                      "fill_ratios": [], "under_20": 0} for cat in CANDIDATE_CATEGORIES}
    norm_cache = {}
    text_cache = {}

    for stem, path in test_map.items():
        if stem not in tops_by_stem:
            continue
        if stem not in text_cache:
            try:
                text_cache[stem] = extract_pdf_text(path)
            except Exception:
                continue
        text = text_cache[stem]
        leaves = leaves_by_stem[stem]
        row = next((r for r in rows if Path(r[idx_filename]).stem == stem), None)
        if row is None:
            continue

        for cat in CANDIDATE_CATEGORIES:
            raw = row[header.index(cat)].strip()
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
                s = per_cat[cat]
                s["total"] += 1
                if is_omitted(span_text):
                    s["omitted"] += 1
                    continue
                found = find_span(text, span_text, norm_cache)
                if found is None:
                    s["not_found"] += 1
                    continue
                start, end = found
                overlapping = [c for c in leaves if c.start < end and c.end > start]
                containing = [c for c in overlapping if c.start <= start and c.end >= end]
                if containing:
                    s["contained"] += 1
                    best = min(containing, key=lambda c: c.end - c.start)
                    clause_len = best.end - best.start
                    ratio = (end - start) / clause_len if clause_len else 0
                    s["fill_ratios"].append(ratio)
                    if ratio < 0.20:
                        s["under_20"] += 1
                elif overlapping:
                    s["cut"] += 1

    lines = []
    lines.append("# Splitter test-split results (Stage B)")
    lines.append("")
    lines.append("Test split was sealed after aggregate PDF-set statistics were seen; "
                  "no case-level inspection, no tuning against it.")
    lines.append("")
    lines.append(f"Frozen caps_fallback_rule: {FROZEN_RULE}")
    lines.append(f"Test-set contracts: {len(test_map)}, read errors: {len(errors)}")
    lines.append("")
    lines.append("## Clause stats")
    lines.append(f"- n = {len(top_counts)}")
    lines.append(f"- mean clauses/contract = {statistics.mean(top_counts):.1f}" if top_counts else "- n/a")
    lines.append(f"- median clauses/contract = {statistics.median(top_counts)}" if top_counts else "")
    lines.append(f"- max clauses/contract = {max(top_counts)}" if top_counts else "")
    lines.append(f"- zero-heading contracts = {zero_heading}")
    lines.append(f"- collapsed (1-clause) contracts = {collapsed}")
    lines.append("")
    lines.append("## Span integrity per category")
    lines.append("")
    lines.append("| Category | raw | omitted | drop% | kept | contained | cut | not_found | "
                  "contain% | cut% | median_fill | under20% |")
    lines.append("|---|---|---|---|---|---|---|---|---|---|---|---|")

    grand = {"total": 0, "omitted": 0, "contained": 0, "cut": 0, "not_found": 0, "under_20": 0}
    for cat in CANDIDATE_CATEGORIES:
        s = per_cat[cat]
        for k in grand:
            if k in s:
                grand[k] += s[k]
        kept = s["total"] - s["omitted"]
        drop_pct = (s["omitted"] / s["total"] * 100) if s["total"] else 0
        contain_pct = (s["contained"] / kept * 100) if kept else 0
        cut_pct = (s["cut"] / kept * 100) if kept else 0
        med_fill = statistics.median(s["fill_ratios"]) if s["fill_ratios"] else 0
        u20_pct = (s["under_20"] / s["contained"] * 100) if s["contained"] else 0
        lines.append(f"| {cat} | {s['total']} | {s['omitted']} | {drop_pct:.1f}% | {kept} | "
                      f"{s['contained']} | {s['cut']} | {s['not_found']} | {contain_pct:.1f}% | "
                      f"{cut_pct:.1f}% | {med_fill:.3f} | {u20_pct:.1f}% |")

    kept_all = grand["total"] - grand["omitted"]
    drop_all = (grand["omitted"] / grand["total"] * 100) if grand["total"] else 0
    contain_all = (grand["contained"] / kept_all * 100) if kept_all else 0
    cut_all = (grand["cut"] / kept_all * 100) if kept_all else 0
    u20_all = (grand["under_20"] / grand["contained"] * 100) if grand["contained"] else 0
    lines.append(f"| **OVERALL** | {grand['total']} | {grand['omitted']} | {drop_all:.1f}% | {kept_all} | "
                  f"{grand['contained']} | {grand['cut']} | {grand['not_found']} | {contain_all:.1f}% | "
                  f"{cut_all:.1f}% | n/a | {u20_all:.1f}% |")

    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUT_PATH.write_text("\n".join(lines), encoding="utf-8")
    print("\n".join(lines))
    print(f"\nWritten: {OUT_PATH}")


if __name__ == "__main__":
    main()
