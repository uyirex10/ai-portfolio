"""Stage A, step 5: bake-off between the ALL-CAPS fallback's Variant A
(current, frozen rule: before-context all-caps ratio + canonical-phrase
allowlist) and Variant B (reject a caps candidate if its heading text
contains a verb or modal auxiliary), on the 199-contract TXT set and the
157-contract PDF dev set.

Reports clause stats, zero-heading/collapsed counts, cut rate per
category, and a "merge measure" (for spans fully CONTAINED in one leaf
clause: span length / that clause's length -- how much of the clause the
labeled span actually fills; a low ratio means the clause is a big bag
that buries a small labeled span, which is its own quality problem,
distinct from cutting a span across multiple clauses).

Prints the pre-registered choice at the end, per the rule: pick B only if
it lowers the dev under-20%-fill share AND raises overall dev cut rate by
no more than 0.5 points absolute AND does not raise dev zero-heading
count; otherwise A.
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

TXT_DIR = ROOT / "cuad_data" / "CUAD_v1" / "full_contract_txt"
PDF_DIR = ROOT / "cuad_data" / "CUAD_v1" / "full_contract_pdf"
DEV_FILE = ROOT / "data_splits" / "dev_contracts.txt"


def dev_pdf_map():
    dev_stems = set(s.strip() for s in DEV_FILE.read_text(encoding="utf-8").splitlines() if s.strip())
    pdf_map = {p.stem: p for p in PDF_DIR.rglob("*.[pP][dD][fF]")}
    return {k: v for k, v in pdf_map.items() if k in dev_stems}


def clause_stats(all_leaves_by_stem, all_tops_by_stem):
    top_counts = [len(v) for v in all_tops_by_stem.values()]
    zero_heading = sum(1 for tops in all_tops_by_stem.values() if tops and not any(c.heading for c in tops))
    collapsed = sum(1 for tops in all_tops_by_stem.values() if len(tops) == 1)
    return {
        "n": len(top_counts),
        "mean": statistics.mean(top_counts) if top_counts else 0,
        "median": statistics.median(top_counts) if top_counts else 0,
        "max": max(top_counts) if top_counts else 0,
        "zero_heading": zero_heading,
        "collapsed": collapsed,
    }


def span_metrics(header, rows, text_by_stem, leaves_by_stem):
    idx_filename = header.index("Filename")
    per_cat = {cat: {"total": 0, "contained": 0, "cut": 0, "not_found": 0, "fill_ratios": [], "under_20": 0}
               for cat in CANDIDATE_CATEGORIES}
    norm_cache = {}

    for r in rows:
        stem = Path(r[idx_filename]).stem
        text = text_by_stem.get(stem)
        if text is None:
            continue
        leaves = leaves_by_stem.get(stem, [])

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
                stats = per_cat[cat]
                stats["total"] += 1
                found = find_span(text, span_text, norm_cache)
                if found is None:
                    stats["not_found"] += 1
                    continue
                start, end = found
                overlapping = [c for c in leaves if c.start < end and c.end > start]
                containing = [c for c in overlapping if c.start <= start and c.end >= end]
                if containing:
                    stats["contained"] += 1
                    best = min(containing, key=lambda c: c.end - c.start)
                    clause_len = best.end - best.start
                    ratio = (end - start) / clause_len if clause_len else 0
                    stats["fill_ratios"].append(ratio)
                    if ratio < 0.20:
                        stats["under_20"] += 1
                elif overlapping:
                    stats["cut"] += 1

    return per_cat


def run_variant(label: str, rule: str, header, rows, txt_stems, dev_map):
    print(f"\n{'=' * 70}\nVARIANT {rule} -- {label}\n{'=' * 70}")

    # TXT set
    txt_tops, txt_leaves, txt_text = {}, {}, {}
    for p in TXT_DIR.rglob("*.txt"):
        try:
            t = p.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        txt_text[p.stem] = t
        tops = segment_contract(t, caps_fallback_rule=rule)
        txt_tops[p.stem] = tops
        txt_leaves[p.stem] = flatten(tops)

    txt_cs = clause_stats(txt_leaves, txt_tops)
    print(f"TXT set (n={txt_cs['n']}): mean={txt_cs['mean']:.1f} median={txt_cs['median']} "
          f"max={txt_cs['max']} zero_heading={txt_cs['zero_heading']} collapsed={txt_cs['collapsed']}")
    txt_spans = span_metrics(header, rows, txt_text, txt_leaves)

    # PDF dev set
    dev_tops, dev_leaves, dev_text = {}, {}, {}
    errors = 0
    for stem, path in dev_map.items():
        try:
            t = extract_pdf_text(path)
        except Exception:
            errors += 1
            continue
        dev_text[stem] = t
        tops = segment_contract(t, caps_fallback_rule=rule)
        dev_tops[stem] = tops
        dev_leaves[stem] = flatten(tops)

    dev_cs = clause_stats(dev_leaves, dev_tops)
    print(f"PDF dev set (n={dev_cs['n']}, errors={errors}): mean={dev_cs['mean']:.1f} "
          f"median={dev_cs['median']} max={dev_cs['max']} zero_heading={dev_cs['zero_heading']} "
          f"collapsed={dev_cs['collapsed']}")
    dev_spans = span_metrics(header, rows, dev_text, dev_leaves)

    def print_span_table(label, per_cat):
        print(f"\n  {label}")
        print(f"  {'Category':30s} {'cut%':>6s} {'under20%':>9s} {'median_fill':>12s}")
        for cat in CANDIDATE_CATEGORIES:
            s = per_cat[cat]
            found = s["contained"] + s["cut"]
            cut_pct = (s["cut"] / found * 100) if found else 0.0
            u20_pct = (s["under_20"] / s["contained"] * 100) if s["contained"] else 0.0
            med_fill = statistics.median(s["fill_ratios"]) if s["fill_ratios"] else 0.0
            print(f"  {cat:30s} {cut_pct:5.1f}% {u20_pct:8.1f}% {med_fill:11.3f}")

        all_cut = sum(s["cut"] for s in per_cat.values())
        all_found = sum(s["contained"] + s["cut"] for s in per_cat.values())
        all_u20 = sum(s["under_20"] for s in per_cat.values())
        all_contained = sum(s["contained"] for s in per_cat.values())
        print(f"  {'OVERALL':30s} {(all_cut / all_found * 100 if all_found else 0):5.1f}% "
              f"{(all_u20 / all_contained * 100 if all_contained else 0):8.1f}%")

    print_span_table("TXT span metrics", txt_spans)
    print_span_table("PDF dev span metrics", dev_spans)

    return {
        "txt_clause_stats": txt_cs, "dev_clause_stats": dev_cs,
        "txt_spans": txt_spans, "dev_spans": dev_spans,
        "dev_tops": dev_tops, "txt_tops": txt_tops,
    }


def diff_boundaries(label_a, tops_a, label_b, tops_b, n=15):
    """Print up to n caps-fallback boundaries one variant keeps that the
    other removes (matched by (stem, heading) across all-caps clauses)."""
    a_caps = {(stem, c.start) for stem, tops in tops_a.items() for c in tops if c.heading and c.heading.isupper()}
    b_caps = {(stem, c.start) for stem, tops in tops_b.items() for c in tops if c.heading and c.heading.isupper()}

    only_a = sorted(a_caps - b_caps)[:n]
    only_b = sorted(b_caps - a_caps)[:n]

    print(f"\n{'=' * 70}\n{label_a} KEEPS, {label_b} REMOVES ({len(a_caps - b_caps)} total, showing {len(only_a)})\n{'=' * 70}")
    for stem, start in only_a:
        clause = next(c for c in tops_a[stem] if c.start == start)
        print(f"  [{stem}] heading={clause.heading!r}")

    print(f"\n{'=' * 70}\n{label_b} KEEPS, {label_a} REMOVES ({len(b_caps - a_caps)} total, showing {len(only_b)})\n{'=' * 70}")
    for stem, start in only_b:
        clause = next(c for c in tops_b[stem] if c.start == start)
        print(f"  [{stem}] heading={clause.heading!r}")


def main():
    header, rows = load_csv_rows()
    txt_stems = {p.stem for p in TXT_DIR.rglob("*.txt")}
    dev_map = dev_pdf_map()

    result_a = run_variant("Variant A (current, frozen)", "A", header, rows, txt_stems, dev_map)
    result_b = run_variant("Variant B (verb/modal rejection)", "B", header, rows, txt_stems, dev_map)

    diff_boundaries("A", {**result_a["txt_tops"], **{f"PDF:{k}": v for k, v in result_a["dev_tops"].items()}},
                     "B", {**result_b["txt_tops"], **{f"PDF:{k}": v for k, v in result_b["dev_tops"].items()}})

    print(f"\n{'=' * 70}\nSUMMARY FOR PRE-REGISTERED CHOICE\n{'=' * 70}")
    a_dev_u20 = sum(s["under_20"] for s in result_a["dev_spans"].values())
    a_dev_contained = sum(s["contained"] for s in result_a["dev_spans"].values())
    b_dev_u20 = sum(s["under_20"] for s in result_b["dev_spans"].values())
    b_dev_contained = sum(s["contained"] for s in result_b["dev_spans"].values())
    a_u20_pct = (a_dev_u20 / a_dev_contained * 100) if a_dev_contained else 0
    b_u20_pct = (b_dev_u20 / b_dev_contained * 100) if b_dev_contained else 0

    a_cut = sum(s["cut"] for s in result_a["dev_spans"].values())
    a_found = sum(s["contained"] + s["cut"] for s in result_a["dev_spans"].values())
    b_cut = sum(s["cut"] for s in result_b["dev_spans"].values())
    b_found = sum(s["contained"] + s["cut"] for s in result_b["dev_spans"].values())
    a_cut_pct = (a_cut / a_found * 100) if a_found else 0
    b_cut_pct = (b_cut / b_found * 100) if b_found else 0

    a_zero = result_a["dev_clause_stats"]["zero_heading"]
    b_zero = result_b["dev_clause_stats"]["zero_heading"]

    print(f"dev under-20%-fill share: A={a_u20_pct:.1f}%, B={b_u20_pct:.1f}%")
    print(f"dev overall cut rate:     A={a_cut_pct:.1f}%, B={b_cut_pct:.1f}% (delta={b_cut_pct - a_cut_pct:+.2f} pts)")
    print(f"dev zero-heading count:   A={a_zero}, B={b_zero}")

    lowers_u20 = b_u20_pct < a_u20_pct
    cut_within_half_point = (b_cut_pct - a_cut_pct) <= 0.5
    no_more_zero_heading = b_zero <= a_zero

    print(f"\nRule check: lowers under-20% share: {lowers_u20}; "
          f"cut rate within +0.5pt: {cut_within_half_point}; "
          f"zero-heading not raised: {no_more_zero_heading}")
    choice = "B" if (lowers_u20 and cut_within_half_point and no_more_zero_heading) else "A"
    print(f"\nPRE-REGISTERED CHOICE: {choice}")


if __name__ == "__main__":
    main()
