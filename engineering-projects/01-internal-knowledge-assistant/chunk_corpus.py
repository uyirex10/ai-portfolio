import json
import random
from pathlib import Path
import sys
sys.stdout.reconfigure(encoding="utf-8")

import tiktoken
from pypdf import PdfReader

CORPUS_DIR = Path("data/corpus")
CHUNKS_FILE = Path("data/chunks.json")
CHUNK_SIZE = 500

encoding = tiktoken.get_encoding("cl100k_base")

chunks = []
num_documents = 0

for pdf_path in sorted(CORPUS_DIR.glob("*.pdf")):
    reader = PdfReader(pdf_path)
    num_documents += 1

    for page_number, page in enumerate(reader.pages, start=1):
        text = page.extract_text() or ""
        tokens = encoding.encode(text)

        for start in range(0, len(tokens), CHUNK_SIZE):
            token_chunk = tokens[start:start + CHUNK_SIZE]
            chunks.append({
                "text": encoding.decode(token_chunk),
                "source_file": pdf_path.name,
                "page_number": page_number,
            })

CHUNKS_FILE.parent.mkdir(parents=True, exist_ok=True)
with open(CHUNKS_FILE, "w", encoding="utf-8") as f:
    json.dump(chunks, f, ensure_ascii=False, indent=2)

total_tokens = sum(len(encoding.encode(chunk["text"])) for chunk in chunks)
avg_tokens = total_tokens / len(chunks) if chunks else 0

print(f"Total documents processed: {num_documents}")
print(f"Total chunks produced: {len(chunks)}")
print(f"Average tokens per chunk: {avg_tokens:.2f}")

if chunks:
    sample = random.sample(chunks, min(4, len(chunks)))
    for i, example in enumerate(sample, start=1):
        print(f"\nExample chunk {i}:")
        print(f"source_file: {example['source_file']}")
        print(f"page_number: {example['page_number']}")
        print(f"text: {example['text']}")
