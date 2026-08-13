import json
import re
from pathlib import Path

SOURCE_MD = Path("RAG_eval_set_50_QA_pairs.md")
EVAL_SET_FILE = Path("data/eval_set.json")
NO_ANSWER_FILE = Path("data/no_answer_set.json")

DOCUMENT_SOURCE_FILES = {
    "HealthGate": "HEALTHGATEDATACORP_11_24_1999-EX-10.1-HOSTING AND MANAGEMENT AGREEMENT - Escrow Agreement.pdf",
    "Adams Golf": "ADAMSGOLFINC_03_21_2005-EX-10.17-ENDORSEMENT AGREEMENT.PDF",
    "Bluefly": "BLUEFLYINC_03_27_2002-EX-10.27-e-business Hosting Agreement.PDF",
    "Transphorm": "TRANSPHORM,INC_02_14_2020-EX-10.12(1)-JOINT VENTURE AGREEMENT.PDF",
    "Dynamex": "DYNAMEXINC_06_06_1996-EX-10.4-TRANSPORTATION SERVICES AGREEMENT.PDF",
}

SECTION_HEADER_RE = re.compile(r"^## \d+\. (\S+)", re.MULTILINE)
NO_ANSWER_RE = re.compile(
    r'\*\*No-answer candidate \(not in the 50\)\*\*:\s*"(.+?)"\s*—\s*(.+)'
)


def short_name_for_section(header_text):
    for name in DOCUMENT_SOURCE_FILES:
        if name.replace(" ", "").upper() in header_text.replace("_", "").upper():
            return name
    raise ValueError(f"No document mapping found for section header: {header_text}")


def parse_pages(cell):
    pages = []
    for part in cell.split(","):
        part = part.strip()
        if "–" in part:
            start, end = part.split("–")
            pages.extend(range(int(start), int(end) + 1))
        else:
            pages.append(int(part))
    return pages


def parse_table_rows(section_text):
    rows = []
    for line in section_text.splitlines():
        line = line.strip()
        if not line.startswith("| Easy |") and not line.startswith("| Connecting |"):
            continue
        cells = [c.strip() for c in line.strip("|").split("|")]
        qtype, question, answer, pages_cell = cells
        rows.append({
            "type": qtype.lower(),
            "question": question,
            "expected_answer": answer,
            "expected_pages": parse_pages(pages_cell),
        })
    return rows


def main():
    text = SOURCE_MD.read_text(encoding="utf-8")
    text = text.split("\n## Summary", 1)[0]

    headers = list(SECTION_HEADER_RE.finditer(text))

    eval_set = []
    no_answer_set = []
    eval_id = 1
    no_answer_id = 1

    for i, match in enumerate(headers):
        section_start = match.end()
        section_end = headers[i + 1].start() if i + 1 < len(headers) else len(text)
        section_text = text[section_start:section_end]

        doc_name = short_name_for_section(match.group(1))
        source_file = DOCUMENT_SOURCE_FILES[doc_name]

        for row in parse_table_rows(section_text):
            eval_set.append({
                "id": eval_id,
                "document": doc_name,
                "source_file": source_file,
                "type": row["type"],
                "question": row["question"],
                "expected_answer": row["expected_answer"],
                "expected_pages": row["expected_pages"],
            })
            eval_id += 1

        no_answer_match = NO_ANSWER_RE.search(section_text)
        if not no_answer_match:
            raise ValueError(f"No no-answer candidate found for {doc_name}")
        question, note = no_answer_match.groups()
        no_answer_set.append({
            "id": no_answer_id,
            "document": doc_name,
            "source_file": source_file,
            "question": question,
            "note": note.strip(),
        })
        no_answer_id += 1

    EVAL_SET_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(EVAL_SET_FILE, "w", encoding="utf-8") as f:
        json.dump(eval_set, f, ensure_ascii=False, indent=2)
    with open(NO_ANSWER_FILE, "w", encoding="utf-8") as f:
        json.dump(no_answer_set, f, ensure_ascii=False, indent=2)

    print(f"eval_set.json: {len(eval_set)} entries")
    per_doc = {}
    for row in eval_set:
        per_doc[row["document"]] = per_doc.get(row["document"], 0) + 1
    for doc, count in per_doc.items():
        print(f"  {doc}: {count}")

    print(f"\nno_answer_set.json: {len(no_answer_set)} entries")
    for row in no_answer_set:
        print(f"  {row['document']}")

    print("\nSource file check:")
    allowed = set(DOCUMENT_SOURCE_FILES.values())
    all_ok = True
    for row in eval_set + no_answer_set:
        if row["source_file"] not in allowed:
            all_ok = False
            print(f"  MISMATCH: id={row['id']} document={row['document']} source_file={row['source_file']}")
    print("  All source_file values match one of the 5 given filenames exactly." if all_ok else "  MISMATCHES FOUND (see above)")


if __name__ == "__main__":
    main()
