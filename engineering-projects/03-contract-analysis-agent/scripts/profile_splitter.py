"""Profile src/segment.py against real CUAD contracts.

Runs the clause splitter over the CUAD full_contract_txt corpus (plain
text, no PDF-extraction noise mixed in) and reports per-contract clause
counts, the shortest/longest clauses seen, contracts that look
under- or over-segmented, and the worst offenders with a snippet
explaining why.
"""

from __future__ import annotations

import sys
import statistics
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except AttributeError:
    pass

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from segment import segment_contract, flatten  # noqa: E402

TXT_DIR = ROOT / "cuad_data" / "CUAD_v1" / "full_contract_txt"


def load_contracts(limit: int | None = None):
    paths = sorted(TXT_DIR.rglob("*.txt"))
    contracts = []
    skipped = []
    for p in paths:
        try:
            text = p.read_text(encoding="utf-8", errors="replace")
        except OSError as e:
            skipped.append((p, str(e)))
            continue
        if text.strip():
            contracts.append((p, text))
        if limit and len(contracts) >= limit:
            break
    return contracts, skipped


def profile_one(path: Path, text: str) -> dict:
    top_clauses = segment_contract(text)
    all_clauses = flatten(top_clauses)
    top_lengths = [len(c.text) for c in top_clauses]
    leaf_lengths = [len(c.text) for c in all_clauses]

    return {
        "path": path,
        "doc_len": len(text),
        "top_count": len(top_clauses),
        "all_count": len(all_clauses),
        "top_min": min(top_lengths) if top_lengths else 0,
        "top_max": max(top_lengths) if top_lengths else 0,
        "leaf_min": min(leaf_lengths) if leaf_lengths else 0,
        "leaf_max": max(leaf_lengths) if leaf_lengths else 0,
        "headings_found": sum(1 for c in top_clauses if c.heading),
        "clauses": top_clauses,
    }


def suspicion_score(p: dict) -> tuple[float, str]:
    """Higher = more suspicious. Returns (score, reason)."""
    doc_len = p["doc_len"]
    top_count = p["top_count"]

    if doc_len > 3000 and top_count <= 1:
        return (doc_len / 1000.0, "long document but only 1 top-level clause (likely under-segmented)")

    if top_count > 0:
        avg_clause_len = doc_len / top_count
        if doc_len > 1500 and avg_clause_len < 60:
            return (1500.0 / max(avg_clause_len, 1), f"very short average clause length ({avg_clause_len:.0f} chars/clause, likely over-segmented)")

    # Exclude the inferred preamble ("0") -- a short exhibit stamp before
    # the first real heading is normal, not a sign of bad segmentation.
    non_preamble_lens = [len(c.text) for c in p["clauses"] if c.id != "0"]
    min_non_preamble = min(non_preamble_lens) if non_preamble_lens else p["top_min"]
    if min_non_preamble < 15 and top_count > 2:
        return (100.0 / max(min_non_preamble, 1), f"has a near-empty clause ({min_non_preamble} chars)")

    if doc_len > 0 and p["top_max"] / doc_len > 0.95 and top_count > 1:
        return (p["top_max"] / doc_len * 10, "one clause swallows almost the entire document")

    return (0.0, "")


def main():
    limit = None
    if len(sys.argv) > 1:
        limit = int(sys.argv[1])

    contracts, skipped = load_contracts(limit=limit)
    print(f"Loaded {len(contracts)} contracts" + (f" (limit={limit})" if limit else "") +
          f", {len(skipped)} unreadable (skipped).")
    if skipped:
        for p, err in skipped[:5]:
            print(f"  SKIPPED: {p.name} -- {err}")

    profiles = [profile_one(p, t) for p, t in contracts]

    top_counts = [p["top_count"] for p in profiles]
    all_leaf_lens = [l for p in profiles for l in [p["leaf_min"], p["leaf_max"]]]

    print()
    print("=" * 70)
    print(f"CONTRACTS ANALYZED: {len(profiles)}")
    print("=" * 70)
    print(f"Top-level clause count per contract: min={min(top_counts)}, "
          f"max={max(top_counts)}, mean={statistics.mean(top_counts):.1f}, "
          f"median={statistics.median(top_counts)}")

    shortest = min(profiles, key=lambda p: p["leaf_min"])
    longest = max(profiles, key=lambda p: p["leaf_max"])
    print(f"\nShortest clause overall: {shortest['leaf_min']} chars in {shortest['path'].name}")
    print(f"Longest clause overall:  {longest['leaf_max']} chars in {longest['path'].name}")

    no_heading = [p for p in profiles if p["top_count"] > 0 and p["headings_found"] == 0]
    print(f"\nContracts with zero detected headings (number-only or single-clause): {len(no_heading)} / {len(profiles)}")

    single_clause = [p for p in profiles if p["top_count"] == 1]
    print(f"Contracts that produced exactly 1 top-level clause: {len(single_clause)} / {len(profiles)}")

    many_clauses = [p for p in profiles if p["top_count"] > 40]
    print(f"Contracts that produced >40 top-level clauses: {len(many_clauses)} / {len(profiles)}")

    scored = [(suspicion_score(p), p) for p in profiles]
    scored = [(s, r, p) for (s, r), p in scored if s > 0]
    scored.sort(key=lambda x: -x[0])

    print()
    print("=" * 70)
    print("10 WORST CASES")
    print("=" * 70)
    for score, reason, p in scored[:10]:
        print(f"\n[{p['path'].name}]")
        print(f"  doc_len={p['doc_len']}, top_clauses={p['top_count']}, "
              f"headings_found={p['headings_found']}, score={score:.1f}")
        print(f"  WHY: {reason}")
        snippet_src = p["clauses"][0].text if p["clauses"] else ""
        snippet = snippet_src[:200].replace("\n", " ")
        print(f"  snippet: {snippet!r}")

    if not scored:
        print("No cases flagged as suspicious by the current heuristics.")


if __name__ == "__main__":
    main()
