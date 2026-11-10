"""Runs one dev contract end to end and prints each stage's output:
clauses, labels, extracted values, rule verdicts, memo. Uses the disk
cache (seeded by scripts/seed_demo_cache.py) so it works fully offline,
with no API key.

*** IMPORTANT: no real LLM key was available this session (see
STATUS.md). The classification/extraction/redline content below comes
from hand-authored cache entries written to be realistic and grounded
in the real clause text -- not from an actual Gemini/Anthropic call.
The segmentation, batching, grounding check, rule engine, and
quote-by-offset logic are all the real, unmodified pipeline code. ***
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "src" / "llm"))

from extract import extract_pdf_text  # noqa: E402
from provider import GeminiProvider  # noqa: E402
import pipeline  # noqa: E402
import memo as memo_mod  # noqa: E402

PDF_DIR = ROOT / "cuad_data" / "CUAD_v1" / "full_contract_pdf"
DEMO_CONTRACT = "TRANSMONTAIGNEPARTNERSLLC_03_13_2020-EX-10.9-SERVICES AGREEMENT"


def main():
    print("=" * 70)
    print("*** DEMO MODE: no live API key this session. Classification/")
    print("*** extraction/redline content below is hand-authored (cached),")
    print("*** not real model output. See STATUS.md and")
    print("*** scripts/seed_demo_cache.py for exactly what was faked and why.")
    print("=" * 70)
    print()

    pdf_map = {p.stem: p for p in PDF_DIR.rglob("*.[pP][dD][fF]")}
    path = pdf_map.get(DEMO_CONTRACT)
    if path is None:
        print(f"Contract not found: {DEMO_CONTRACT}")
        print("(cuad_data/ is gitignored -- see README for how to fetch CUAD.)")
        return

    print(f"Contract: {DEMO_CONTRACT}\n")

    text = extract_pdf_text(path)
    provider = GeminiProvider()  # lazy client -- no key needed as long as the cache covers this run
    result = pipeline.analyze_contract(text, provider)

    print("-" * 70)
    print(f"STAGE 1: SEGMENTATION -- {len(result['leaves'])} leaf clauses")
    print("-" * 70)
    for i, c in enumerate(result["leaves"]):
        heading = f" ({c.heading})" if c.heading else ""
        print(f"  clause_{i}: id={c.id!r}{heading} [{c.start}:{c.end}] -- {c.text[:60]!r}")

    print()
    print("-" * 70)
    print("STAGE 2: CLASSIFICATION -- multi-label over the 8 Stage C types")
    print("-" * 70)
    for cl in result["classifications"]:
        if cl.labels:
            print(f"  {cl.clause_id}: {cl.labels}")

    print()
    print("-" * 70)
    print("STAGE 3: VALUE EXTRACTION (with grounding check)")
    print("-" * 70)
    for cid, clause, ctype, extraction in result["extraction_records"]:
        v = extraction.values
        print(f"  {cid} ({ctype}): amount={v.amount} currency={v.currency} notice_days={v.notice_days} "
              f"jurisdiction={v.jurisdiction} date={v.date} grounded={v.grounded} "
              f"ungrounded_fields={v.ungrounded_fields}")

    print()
    print("-" * 70)
    print("STAGE 4: RULE VERDICTS")
    print("-" * 70)
    for rr in result["rule_results"]:
        print(f"  [{rr.verdict.value.upper():12s}] {rr.clause_type:35s} ({rr.rule_id}): {rr.reason}")

    print()
    print("-" * 70)
    print("STAGE 5: MEMO (non-green findings only)")
    print("-" * 70)
    print(memo_mod.render_markdown(DEMO_CONTRACT, result["memo_findings"]))


if __name__ == "__main__":
    main()
