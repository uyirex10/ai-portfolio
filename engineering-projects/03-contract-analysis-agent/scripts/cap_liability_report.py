"""Write reports/cap_liability_cuts_after.md: every Cap On Liability cut-across
case in the dev split of PDF-only contracts (PyMuPDF extraction), with
the labeled span, the boundary that split it, 200 chars of source on
each side of the cut point, and an inferred heading-pattern label for
the clause that starts at the cut.

The heading-pattern label is INFERRED from the public Clause.id/heading
shape, not read out of segment.py internals (segment.py is not modified
or imported beyond its public segment_contract/flatten API) -- it's a
best-effort classification for grouping, not a guaranteed-exact trace of
which regex fired. Flagged as such in the report itself.
"""

from __future__ import annotations

import ast
import csv
import re
import sys
from collections import defaultdict
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
from span_integrity import find_span, classify_span  # noqa: E402

CSV_PATH = ROOT / "cuad_data" / "CUAD_v1" / "master_clauses.csv"
PDF_DIR = ROOT / "cuad_data" / "CUAD_v1" / "full_contract_pdf"
DEV_FILE = ROOT / "data_splits" / "dev_contracts.txt"
OUT_PATH = ROOT / "reports" / "cap_liability_cuts_after.md"

CATEGORY = "Cap On Liability"

_ROMAN_RE = re.compile(r"^[IVXLCDM]+$")
_LOWER_ROMAN_RE = re.compile(r"^[ivxlcdm]{1,5}$")
_LOWER_LETTER_RE = re.compile(r"^[a-z]{1,3}$")
_DOTTED_RE = re.compile(r"^\d+(\.\d+)+$")


def infer_trigger(clause) -> str:
    cid = clause.id
    heading = clause.heading
    if cid == "0":
        return "preamble (no marker)"
    if _DOTTED_RE.match(cid):
        return "dotted sub-number (N.M...)"
    if _ROMAN_RE.match(cid):
        return "roman numeral (ARTICLE or bare roman numeral)"
    if _LOWER_LETTER_RE.match(cid):
        return "lettered sub-item ((a), (b), ...)"
    if _LOWER_ROMAN_RE.match(cid):
        return "lowercase roman sub-item ((i), (ii), ...)"
    if cid.isdigit():
        if heading and heading.isupper():
            return "ALL-CAPS heading fallback (inferred from upper-case heading)"
        if heading:
            return "plain numbered with heading (\"N. Heading\")"
        return "plain numbered, no heading (\"N.\")"
    return f"unrecognized id shape ({cid!r})"


def main():
    dev_stems = set(s.strip() for s in DEV_FILE.read_text(encoding="utf-8").splitlines() if s.strip())

    with open(CSV_PATH, encoding="utf-8") as f:
        reader = csv.reader(f)
        header = next(reader)
        rows = list(reader)
    idx_filename = header.index("Filename")
    col_idx = header.index(CATEGORY)

    pdf_map = {p.stem: p for p in PDF_DIR.rglob("*.[pP][dD][fF]")}
    norm_cache = {}
    cases = []
    errors = []

    for r in rows:
        stem = Path(r[idx_filename]).stem
        if stem not in dev_stems:
            continue
        raw = r[col_idx].strip()
        if not raw or raw == "[]":
            continue
        path = pdf_map.get(stem)
        if path is None:
            continue
        try:
            text = extract_pdf_text(path)
        except Exception as e:
            errors.append((stem, str(e)[:150]))
            continue
        leaves = flatten(segment_contract(text))

        try:
            spans = ast.literal_eval(raw)
        except Exception:
            spans = [raw]

        for span_text in spans:
            span_text = span_text.strip() if isinstance(span_text, str) else str(span_text)
            if not span_text:
                continue
            found = find_span(text, span_text, norm_cache)
            if found is None:
                continue
            verdict = classify_span(leaves, found[0], found[1])
            if not verdict.startswith("cut_across"):
                continue

            span_start, span_end = found
            overlapping = [c for c in leaves if c.start < span_end and c.end > span_start]
            overlapping.sort(key=lambda c: c.start)
            # The cut points are every overlapping clause's start that falls
            # strictly inside the labeled span (i.e. where a new clause began
            # partway through what should have been one labeled clause).
            cut_clauses = [c for c in overlapping if span_start < c.start < span_end]

            cases.append({
                "stem": stem,
                "span_text": span_text,
                "span_start": span_start,
                "span_end": span_end,
                "text": text,
                "overlapping": overlapping,
                "cut_clauses": cut_clauses,
            })

    print(f"Dev-set contracts: {len(dev_stems)}, read errors: {len(errors)}")
    print(f"Cap On Liability cut-across cases found: {len(cases)}")

    grouped = defaultdict(list)
    for case in cases:
        for cut_clause in case["cut_clauses"]:
            trigger = infer_trigger(cut_clause)
            grouped[trigger].append((case, cut_clause))

    lines = []
    lines.append("# Cap On Liability -- cut-across cases (dev set, PyMuPDF extraction)")
    lines.append("")
    lines.append(f"Dev-set PDF-only contracts: {len(dev_stems)}. "
                 f"Cap On Liability spans cut across 2+ splitter clauses: **{len(cases)}**.")
    lines.append("")
    lines.append("The \"trigger\" label for each cut is **inferred** from the shape of the clause id/heading "
                 "that starts partway through the labeled span (e.g. a dotted id like `4.2` implies a dotted "
                 "sub-number boundary fired there) -- it is not read out of segment.py's internal regex state "
                 "(this report does not modify or introspect segment.py beyond its public API), so treat it as "
                 "a best-effort classification for grouping, not a guaranteed trace of which rule fired.")
    lines.append("")

    for trigger in sorted(grouped, key=lambda k: -len(grouped[k])):
        entries = grouped[trigger]
        lines.append(f"## {trigger} ({len(entries)} cases)")
        lines.append("")
        for case, cut_clause in entries:
            text = case["text"]
            cut_pos = cut_clause.start
            ctx_start = max(0, cut_pos - 200)
            ctx_end = min(len(text), cut_pos + 200)
            before = text[ctx_start:cut_pos]
            after = text[cut_pos:ctx_end]

            lines.append(f"### {case['stem']}")
            lines.append("")
            lines.append(f"**Labeled span (Cap On Liability):**")
            lines.append("```")
            lines.append(case["span_text"][:600])
            lines.append("```")
            lines.append(f"**Cut boundary:** new clause `id={cut_clause.id!r}` "
                          f"heading={cut_clause.heading!r} begins at offset {cut_pos} "
                          f"(span runs {case['span_start']}-{case['span_end']})")
            lines.append("")
            lines.append("**200 chars before the cut:**")
            lines.append("```")
            lines.append(before)
            lines.append("```")
            lines.append("**200 chars after the cut (start of new clause):**")
            lines.append("```")
            lines.append(after)
            lines.append("```")
            lines.append("")

    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUT_PATH.write_text("\n".join(lines), encoding="utf-8")
    print(f"Written: {OUT_PATH}")

    print("\nBy trigger:")
    for trigger in sorted(grouped, key=lambda k: -len(grouped[k])):
        print(f"  {trigger}: {len(grouped[trigger])}")


if __name__ == "__main__":
    main()
