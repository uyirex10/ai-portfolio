"""Seed .cache/llm/ with hand-authored responses for 2 dev contracts, so
scripts/demo.py and the sample-memo generator can run the REAL pipeline
code (segment -> classify -> extract -> rules -> memo) entirely offline,
with no API key, per the project's blocker (no live Gemini/Anthropic key
was available this session -- see STATUS.md).

This is NOT a substitute for real model output: every "response" below
was written by hand after reading the actual clause text (grounded in
what's really in these two contracts), to exercise the real parsing,
batching, and grounding-check code paths end to end. It is clearly
labeled as such wherever it surfaces (demo.py's own banner, STATUS.md,
README limitations).

Uses the real build_classification_prompt / build_extraction_prompt /
build_redline_prompt functions so the cache keys match exactly what the
pipeline will actually request -- these are not duplicated/retyped
prompt strings.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "src" / "llm"))

from extract import extract_pdf_text  # noqa: E402
from segment import segment_contract, flatten  # noqa: E402
from provider import GeminiProvider, write_cache  # noqa: E402
from batching import batch_by_char_budget  # noqa: E402
from classify import build_classification_prompt  # noqa: E402
from extract_values import build_extraction_prompt  # noqa: E402
from memo import build_redline_prompt  # noqa: E402
import pipeline  # noqa: E402

PDF_DIR = ROOT / "cuad_data" / "CUAD_v1" / "full_contract_pdf"
MODEL = GeminiProvider.default_model

DEMO_CONTRACTS = [
    "TRANSMONTAIGNEPARTNERSLLC_03_13_2020-EX-10.9-SERVICES AGREEMENT",
    "GluMobileInc_20070319_S-1A_EX-10.09_436630_EX-10.09_Content License Agreement3",
]


def seed(prompt: str, response_obj) -> None:
    response = response_obj if isinstance(response_obj, str) else json.dumps(response_obj)
    write_cache(MODEL, prompt, response)


def seed_transmontaigne(leaves):
    by_id = {f"clause_{i}": c for i, c in enumerate(leaves)}

    # --- classification batch(es): must mirror classify_clauses' own
    # batching exactly, or the cache key won't match what it actually requests ---
    all_labels = {cid: [] for cid in by_id}
    for cid, c in by_id.items():
        if c.heading == "Choice of Law; Submission to Jurisdiction":
            all_labels[cid] = ["Governing Law"]
        elif c.heading == "Termination of Agreement":
            all_labels[cid] = ["Termination For Convenience"]
        elif c.heading == "SERVICES AGREEMENT":
            all_labels[cid] = ["Effective Date"]

    pairs = [(cid, c.text) for cid, c in by_id.items()]
    batches = batch_by_char_budget(pairs, text_of=lambda p: p[1])
    for batch in batches:
        prompt = build_classification_prompt(batch)
        batch_response = {cid: all_labels[cid] for cid, _ in batch}
        seed(prompt, batch_response)

    # --- extraction, one call per labeled clause ---
    gov_id = next(cid for cid, l in all_labels.items() if l == ["Governing Law"])
    seed(
        build_extraction_prompt("Governing Law", by_id[gov_id].text),
        {"amount": None, "currency": None, "duration_value": None, "duration_unit": None,
         "notice_days": None, "jurisdiction": "Colorado", "date": None,
         "evidence": "governed by the\nlaws of the State of Colorado"},
    )

    term_id = next(cid for cid, l in all_labels.items() if l == ["Termination For Convenience"])
    seed(
        build_extraction_prompt("Termination For Convenience", by_id[term_id].text),
        {"amount": None, "currency": None, "duration_value": 5, "duration_unit": "day",
         "notice_days": 5, "jurisdiction": None, "date": None,
         "evidence": "by either Party upon 5 days written\nnotice to the other Party"},
    )

    date_id = next(cid for cid, l in all_labels.items() if l == ["Effective Date"])
    # The source literally has a blank day ("August __, 2019") -- an honest
    # extractor declines to fabricate a complete date rather than guess one.
    seed(
        build_extraction_prompt("Effective Date", by_id[date_id].text),
        {"amount": None, "currency": None, "duration_value": None, "duration_unit": None,
         "notice_days": None, "jurisdiction": None, "date": None,
         "evidence": "effective as of, August __, 2019"},
    )

    # --- redlines for every non-green rule result ---
    redlines = {
        ("Cap On Liability", "red"): (
            "Add a new Section: \"Limitation of Liability. In no event shall either Party's aggregate "
            "liability under this Agreement exceed the total fees paid in the preceding twelve (12) months.\""
        ),
        ("Notice Period To Terminate Renewal", "red"): (
            "This Agreement has no fixed renewal term, so there is no renewal-notice window to set. If a "
            "renewal term is added, pair it with a minimum 30-day notice-to-terminate-renewal clause."
        ),
        ("Expiration Date", "red"): (
            "Consider adding a fixed initial term (e.g., \"This Agreement shall continue for an initial "
            "term of one (1) year from the Effective Date\") rather than relying solely on notice-based termination."
        ),
        ("Audit Rights", "amber"): (
            "Add: \"The Operating Company may, upon reasonable notice, audit EmployeeCo's records "
            "relating to the reimbursements and fees charged under Section 1.2 and 1.3.\""
        ),
        ("Governing Law", "amber"): (
            "If Delaware or New York law is preferred, revise Section 2.1 to read: \"This Agreement shall "
            "be subject to and governed by the laws of the State of Delaware...\""
        ),
        ("Effective Date", "amber"): "Fill in the blank day in the preamble (\"August __, 2019\") with the actual effective date.",
    }
    for (clause_type, verdict), redline_text in redlines.items():
        if clause_type == "Governing Law":
            clause_text = by_id[gov_id].text
        elif clause_type == "Effective Date":
            clause_text = by_id[date_id].text
        else:
            continue  # missing-clause findings have no clause text to build a redline prompt against
        reason = {
            "Governing Law": "Governing law (Colorado) is not on the preferred jurisdiction list (['Delaware', 'New York']).",
            "Effective Date": "No effective date found, or the extracted date could not be grounded.",
        }[clause_type]
        seed(build_redline_prompt(clause_type, clause_text, verdict, reason), redline_text)

    # Missing-clause findings (Cap On Liability, Notice Period, Expiration Date) never
    # reach build_redline_prompt (memo.py skips the LLM call for those -- see pipeline.py).


def seed_glu_mobile(leaves):
    pairs = [(f"clause_{i}", c.text) for i, c in enumerate(leaves)]
    # This is a narrow royalty amendment; none of the 8 monitored clause
    # types are restated in it (they'd live in the base agreement it
    # amends, which is not part of this exhibit).
    all_labels = {cid: [] for cid, _ in pairs}
    batches = batch_by_char_budget(pairs, text_of=lambda p: p[1])
    for batch in batches:
        prompt = build_classification_prompt(batch)
        batch_response = {cid: all_labels[cid] for cid, _ in batch}
        seed(prompt, batch_response)
    # No extractions needed since nothing was classified.


def main():
    pdf_map = {p.stem: p for p in PDF_DIR.rglob("*.[pP][dD][fF]")}

    text1 = extract_pdf_text(pdf_map[DEMO_CONTRACTS[0]])
    leaves1 = flatten(segment_contract(text1))
    seed_transmontaigne(leaves1)

    text2 = extract_pdf_text(pdf_map[DEMO_CONTRACTS[1]])
    leaves2 = flatten(segment_contract(text2))
    seed_glu_mobile(leaves2)

    print(f"Seeded cache for: {DEMO_CONTRACTS[0]} ({len(leaves1)} leaf clauses)")
    print(f"Seeded cache for: {DEMO_CONTRACTS[1]} ({len(leaves2)} leaf clauses)")

    # Sanity check: run the real pipeline now, entirely from cache.
    provider = GeminiProvider()
    for name, text in [(DEMO_CONTRACTS[0], text1), (DEMO_CONTRACTS[1], text2)]:
        result = pipeline.analyze_contract(text, provider)
        n_findings = len(result["memo_findings"])
        print(f"  {name}: {n_findings} non-green findings (pipeline ran fully from cache, no API key used)")


if __name__ == "__main__":
    main()
