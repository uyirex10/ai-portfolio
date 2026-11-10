"""Stage F: write 2 sample memos from dev contracts to
reports/sample_memos/, using the cache seeded by scripts/seed_demo_cache.py
(see that script's docstring -- hand-authored responses, not real model
output, because no API key was available this session).
"""

from __future__ import annotations

import json
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
OUT_DIR = ROOT / "reports" / "sample_memos"

DEMO_CONTRACTS = [
    "TRANSMONTAIGNEPARTNERSLLC_03_13_2020-EX-10.9-SERVICES AGREEMENT",
    "GluMobileInc_20070319_S-1A_EX-10.09_436630_EX-10.09_Content License Agreement3",
]

DISCLAIMER = (
    "> **Note:** this sample memo was generated using hand-authored, clearly-labeled stand-in "
    "LLM responses, not a real Gemini/Anthropic call -- no API key was available this session "
    "(see STATUS.md). The segmentation, rule engine, and quote-by-offset logic are all real; "
    "only the classification/extraction/redline *content* is a placeholder written to be "
    "realistic and grounded in the actual clause text.\n"
)


def main():
    pdf_map = {p.stem: p for p in PDF_DIR.rglob("*.[pP][dD][fF]")}
    provider = GeminiProvider()
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    for stem in DEMO_CONTRACTS:
        text = extract_pdf_text(pdf_map[stem])
        result = pipeline.analyze_contract(text, provider)
        findings = result["memo_findings"]

        md = memo_mod.render_markdown(stem, findings)
        md_with_notice = md.split("\n", 2)
        md_final = f"{md_with_notice[0]}\n\n{DISCLAIMER}\n" + "\n".join(md_with_notice[1:])

        json_data = memo_mod.render_json(stem, findings)
        json_data["_notice"] = ("Hand-authored stand-in LLM responses; no real API call was made "
                                 "this session. See STATUS.md.")

        safe_name = "".join(c if c.isalnum() or c in "-_ " else "_" for c in stem)[:80]
        (OUT_DIR / f"{safe_name}.md").write_text(md_final, encoding="utf-8")
        (OUT_DIR / f"{safe_name}.json").write_text(json.dumps(json_data, indent=2), encoding="utf-8")
        print(f"Wrote {safe_name}.md and .json ({len(findings)} findings)")


if __name__ == "__main__":
    main()
