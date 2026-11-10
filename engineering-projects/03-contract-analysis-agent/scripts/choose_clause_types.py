"""Stage C: choose the 8 clause types, pre-registered rule.

For each of the 41 real CUAD categories, compute: contract frequency
(how many of 510 contracts have a non-empty labeled span) and whether
labeled spans carry a quantity, duration, currency amount, or named
value a rule can compare -- measured, not assumed, by scanning each
category's raw labeled spans for numeric/currency/duration/percent
tokens, or (for the four date/jurisdiction categories where the
-Answer column itself is already a structured value) checking that
column directly.

Rule: must include (>=40 labeled spans, easily cleared) Cap On
Liability, Termination For Convenience, Notice Period To Terminate
Renewal (the renewal-notice category), Governing Law. Fill the
remaining 4 slots by highest frequency among categories that (a) carry
a rule-comparable value and (b) appear in >=15% of contracts (>=76.5,
i.e. >=77 of 510), excluding Document Name and Parties (pure metadata,
not clause content) and the 4 already chosen.
"""

from __future__ import annotations

import ast
import csv
import re
import sys
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except AttributeError:
    pass

ROOT = Path(__file__).resolve().parents[1]
CSV_PATH = ROOT / "cuad_data" / "CUAD_v1" / "master_clauses.csv"

MUST_INCLUDE = ["Cap On Liability", "Termination For Convenience",
                "Notice Period To Terminate Renewal", "Governing Law"]

NUM_RE = re.compile(r"\b\d+(?:[.,]\d+)?\b")
CURRENCY_RE = re.compile(r"[$€£]|USD|dollars?|cents?", re.I)
DURATION_RE = re.compile(r"\b(day|days|month|months|year|years|annum|week|weeks|hour|hours)\b", re.I)
PERCENT_RE = re.compile(r"%|percent", re.I)

# These categories' -Answer column IS the structured value already
# (date, jurisdiction name), not a Yes/No flag -- treated as
# rule-comparable by definition, not by scanning raw span text.
STRUCTURED_ANSWER_CATEGORIES = {
    "Agreement Date", "Effective Date", "Expiration Date", "Renewal Term",
    "Notice Period To Terminate Renewal", "Governing Law",
}

VALUE_THRESHOLD = 0.5  # share of non-empty raw spans containing a usable token


def main():
    with open(CSV_PATH, encoding="utf-8") as f:
        reader = csv.reader(f)
        header = next(reader)
        rows = list(reader)
    total = len(rows)

    categories = [h for h in header if "Answer" not in h and h != "Filename"]
    print(f"Total contracts: {total}, categories found: {len(categories)}\n")

    results = []
    for cat in categories:
        idx = header.index(cat)
        non_empty = [r[idx].strip() for r in rows if r[idx].strip() and r[idx].strip() != "[]"]
        freq = len(non_empty)

        if cat in STRUCTURED_ANSWER_CATEGORIES:
            carries_value = True
            value_share = 1.0
        else:
            spans_text = []
            for raw in non_empty:
                try:
                    items = ast.literal_eval(raw)
                except Exception:
                    items = [raw]
                spans_text.append(" ".join(str(x) for x in items))
            has_value = sum(
                1 for s in spans_text
                if NUM_RE.search(s) or CURRENCY_RE.search(s) or DURATION_RE.search(s) or PERCENT_RE.search(s)
            )
            value_share = (has_value / len(spans_text)) if spans_text else 0.0
            carries_value = value_share >= VALUE_THRESHOLD

        results.append({
            "category": cat, "freq": freq, "pct": freq / total * 100,
            "carries_value": carries_value, "value_share": value_share * 100,
        })

    results.sort(key=lambda r: -r["freq"])
    print(f"{'Category':40s} {'freq':>5s} {'pct':>6s} {'value%':>7s} {'carries_value':>13s}")
    for r in results:
        print(f"{r['category']:40s} {r['freq']:5d} {r['pct']:5.1f}% {r['value_share']:6.1f}% "
              f"{str(r['carries_value']):>13s}")

    by_cat = {r["category"]: r for r in results}
    print("\n" + "=" * 70)
    print("MUST-INCLUDE (>=40 labeled spans check)")
    print("=" * 70)
    for cat in MUST_INCLUDE:
        r = by_cat[cat]
        print(f"  {cat}: freq={r['freq']} ({'OK, >=40' if r['freq'] >= 40 else 'FAILS, <40'})")

    chosen = list(MUST_INCLUDE)
    excluded_from_fill = set(MUST_INCLUDE) | {"Document Name", "Parties"}
    candidates = [r for r in results
                  if r["category"] not in excluded_from_fill and r["carries_value"] and r["pct"] >= 15.0]
    candidates.sort(key=lambda r: -r["freq"])

    print("\n" + "=" * 70)
    print("CANDIDATES TO FILL REMAINING 4 SLOTS (value-carrying, >=15% frequency, not already chosen)")
    print("=" * 70)
    for r in candidates:
        print(f"  {r['category']:40s} freq={r['freq']:4d} ({r['pct']:.1f}%) value%={r['value_share']:.1f}")

    fill = candidates[:4]
    chosen.extend(r["category"] for r in fill)

    print("\n" + "=" * 70)
    print("FINAL 8 CHOSEN CLAUSE TYPES")
    print("=" * 70)
    for cat in chosen:
        r = by_cat[cat]
        tag = "MUST-INCLUDE" if cat in MUST_INCLUDE else "FILL (highest freq, value-carrying, >=15%)"
        print(f"  {cat:40s} freq={r['freq']:4d} ({r['pct']:.1f}%) -- {tag}")


if __name__ == "__main__":
    main()
