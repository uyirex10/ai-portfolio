"""Stage 1.6, step 2: for dev-set spans still not found after the
fold-aware matching harness (scripts/span_integrity.py), compare span
length for found vs. not-found (overall and per category), and test the
hypothesis that long spans broken by a page header/footer/table are the
ones that go missing.

Hypothesis test method: split each not-found span in half and try to
locate each half independently. If both halves are found, in order, at
non-adjacent positions, the text in between is exactly what's missing
from a clean match -- inspect that gap for a page-number pattern
("Page X of Y"), a short isolated fragment, or table-like runs of
whitespace-separated tokens. This gives a real pass/fail per case
instead of an eyeballed guess from a handful of examples.

Never reads data_splits/test_contracts.txt.
"""

from __future__ import annotations

import ast
import re
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
from extract import extract_pdf_text as pymupdf_extract  # noqa: E402
from span_integrity import (  # noqa: E402
    CANDIDATE_CATEGORIES, find_span, classify_span, is_omitted, load_csv_rows, normalize,
)

PDF_DIR = ROOT / "cuad_data" / "CUAD_v1" / "full_contract_pdf"
DEV_FILE = ROOT / "data_splits" / "dev_contracts.txt"

_PAGE_NUM_RE = re.compile(r"page\s+\d+\s+of\s+\d+", re.I)


def looks_like_header_footer_or_table(gap_text: str) -> str | None:
    g = gap_text.strip()
    if not g:
        return None
    if _PAGE_NUM_RE.search(g):
        return "page-number marker"
    # Repeated running header/footer: a short, isolated line (not a
    # sentence continuation -- no lowercase-starting continuation word).
    words = g.split()
    if len(words) <= 8 and g and g[0].isupper():
        return "short isolated fragment (likely header/footer/caption)"
    # Table-like: many short whitespace-separated tokens, few of them
    # forming normal lowercase prose.
    short_tokens = [w for w in words if len(w) <= 12]
    if words and len(short_tokens) / len(words) > 0.8 and len(words) > 6:
        return "table-like run of short tokens"
    return None


def test_hypothesis_for_span(span_text: str, text: str) -> dict:
    norm_span = normalize(span_text)
    mid = len(norm_span) // 2
    # back off `mid` to the nearest space so halves break on word boundaries
    while mid > 0 and norm_span[mid] != " ":
        mid -= 1
    first_half, second_half = norm_span[:mid].strip(), norm_span[mid:].strip()
    if not first_half or not second_half:
        return {"verdict": "too_short_to_split"}

    norm_text = normalize(text)
    idx1 = norm_text.find(first_half)
    idx2 = norm_text.find(second_half, idx1 + len(first_half) if idx1 != -1 else 0)

    if idx1 == -1 or idx2 == -1:
        return {"verdict": "halves_not_found_either"}

    gap_start = idx1 + len(first_half)
    gap_end = idx2
    if gap_end <= gap_start:
        return {"verdict": "halves_overlap_or_adjacent"}

    gap_text = norm_text[gap_start:gap_end]
    reason = looks_like_header_footer_or_table(gap_text)
    return {
        "verdict": "gap_matches_hypothesis" if reason else "gap_found_but_unexplained",
        "gap_text": gap_text,
        "gap_reason": reason,
    }


def dev_pdf_map():
    dev_stems = set(s.strip() for s in DEV_FILE.read_text(encoding="utf-8").splitlines() if s.strip())
    pdf_map = {p.stem: p for p in PDF_DIR.rglob("*.[pP][dD][fF]")}
    return {k: v for k, v in pdf_map.items() if k in dev_stems}


def main():
    header, rows = load_csv_rows()
    dev_map = dev_pdf_map()
    idx_filename = header.index("Filename")

    text_cache, leaf_cache, norm_cache = {}, {}, {}
    found_lens, not_found_lens = [], []
    found_lens_by_cat = {c: [] for c in CANDIDATE_CATEGORIES}
    not_found_lens_by_cat = {c: [] for c in CANDIDATE_CATEGORIES}
    not_found_cases = []

    for r in rows:
        stem = Path(r[idx_filename]).stem
        path = dev_map.get(stem)
        if path is None:
            continue
        if stem not in text_cache:
            try:
                text_cache[stem] = pymupdf_extract(path)
                leaf_cache[stem] = flatten(segment_contract(text_cache[stem]))
            except Exception:
                text_cache[stem] = None
        text = text_cache[stem]
        if text is None:
            continue
        leaves = leaf_cache[stem]

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
                found = find_span(text, span_text, norm_cache)
                if found is not None:
                    found_lens.append(len(span_text))
                    found_lens_by_cat[cat].append(len(span_text))
                else:
                    not_found_lens.append(len(span_text))
                    not_found_lens_by_cat[cat].append(len(span_text))
                    not_found_cases.append({"category": cat, "stem": stem, "span_text": span_text, "text": text})

    print("=" * 70)
    print("SPAN LENGTH: FOUND vs NOT-FOUND (dev set, after fold-aware matching, non-omitted only)")
    print("=" * 70)
    print(f"\n{'':30s} {'n_found':>8s} {'mean_len':>9s} {'median_len':>11s} | "
          f"{'n_nf':>6s} {'mean_len':>9s} {'median_len':>11s}")
    for cat in CANDIDATE_CATEGORIES:
        fl, nfl = found_lens_by_cat[cat], not_found_lens_by_cat[cat]
        f_mean = statistics.mean(fl) if fl else 0
        f_med = statistics.median(fl) if fl else 0
        nf_mean = statistics.mean(nfl) if nfl else 0
        nf_med = statistics.median(nfl) if nfl else 0
        print(f"{cat:30s} {len(fl):8d} {f_mean:9.0f} {f_med:11.0f} | {len(nfl):6d} {nf_mean:9.0f} {nf_med:11.0f}")

    print(f"\n{'OVERALL':30s} {len(found_lens):8d} {statistics.mean(found_lens):9.0f} "
          f"{statistics.median(found_lens):11.0f} | {len(not_found_lens):6d} "
          f"{statistics.mean(not_found_lens):9.0f} {statistics.median(not_found_lens):11.0f}")

    ratio = statistics.mean(not_found_lens) / statistics.mean(found_lens) if found_lens else 0
    print(f"\nnot-found spans are {ratio:.2f}x the mean length of found spans")

    print("\n" + "=" * 70)
    print(f"HYPOTHESIS TEST: long not-found spans are broken by a page header/footer/table")
    print(f"(n = {len(not_found_cases)} not-found, non-omitted dev spans)")
    print("=" * 70)

    verdict_counts: dict[str, int] = {}
    examples_by_verdict: dict[str, list] = {}
    for case in not_found_cases:
        result = test_hypothesis_for_span(case["span_text"], case["text"])
        v = result["verdict"]
        verdict_counts[v] = verdict_counts.get(v, 0) + 1
        examples_by_verdict.setdefault(v, []).append((case, result))

    for v, n in sorted(verdict_counts.items(), key=lambda x: -x[1]):
        print(f"  {v}: {n} ({n / len(not_found_cases) * 100:.1f}%)")

    matches = verdict_counts.get("gap_matches_hypothesis", 0)
    print(f"\n{matches}/{len(not_found_cases)} ({matches / len(not_found_cases) * 100:.1f}%) "
          f"of not-found spans show a locatable gap that looks like a page header/footer/table.")

    print("\n" + "=" * 70)
    print("10 EXAMPLES (prioritizing gap_matches_hypothesis, then gap_found_but_unexplained)")
    print("=" * 70)
    shown = 0
    for v in ("gap_matches_hypothesis", "gap_found_but_unexplained", "halves_not_found_either",
              "halves_overlap_or_adjacent", "too_short_to_split"):
        for case, result in examples_by_verdict.get(v, []):
            if shown >= 10:
                break
            print(f"\n[{case['category']}] {case['stem']}  -- verdict: {v}")
            print(f"  SPAN: {case['span_text'][:180]!r}")
            if "gap_text" in result:
                print(f"  GAP ({result.get('gap_reason')}): {result['gap_text'][:180]!r}")
            shown += 1
        if shown >= 10:
            break

    print("\n" + "=" * 70)
    print("CONCLUSION")
    print("=" * 70)
    long_support = ratio > 1.15
    gap_support = matches / len(not_found_cases) > 0.25 if not_found_cases else False
    if long_support and gap_support:
        print(f"VERIFIED: not-found spans run {ratio:.2f}x longer on average than found spans, and "
              f"{matches}/{len(not_found_cases)} ({matches / len(not_found_cases) * 100:.1f}%) show a "
              f"locatable, header/footer/table-shaped gap when split in half and relocated independently. "
              f"Both pieces of evidence point the same way.")
    elif gap_support:
        print(f"PARTIALLY VERIFIED: {matches}/{len(not_found_cases)} not-found spans show a header/footer/"
              f"table-shaped gap (supports the mechanism), but the length ratio ({ratio:.2f}x) does not "
              f"clearly show not-found spans are systematically longer -- so 'long spans specifically' is "
              f"GUESSED, not verified, even though 'broken by a header/footer/table' is verified for a "
              f"meaningful minority.")
    else:
        print(f"NOT VERIFIED: only {matches}/{len(not_found_cases)} ({matches / max(len(not_found_cases), 1) * 100:.1f}%) "
              f"not-found spans show a header/footer/table-shaped gap, and the length ratio is {ratio:.2f}x. "
              f"The majority of this bucket is not explained by this hypothesis -- GUESSED only.")


if __name__ == "__main__":
    main()
