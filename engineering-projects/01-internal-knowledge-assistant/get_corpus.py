import random
import shutil
from pathlib import Path

random.seed(42)  # reproducible, so you get the same subset every run

source = Path("full_contract_pdf")
dest = Path("data/corpus")
dest.mkdir(parents=True, exist_ok=True)

all_pdfs = list(source.rglob("*.pdf"))
print(f"Found {len(all_pdfs)} PDFs")  # sanity check before sampling

selected = random.sample(all_pdfs, 60)

for pdf in selected:
    shutil.copy(pdf, dest / pdf.name)

print(f"Copied {len(selected)} contracts to {dest}")