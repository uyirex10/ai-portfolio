import json
import os
import time
from pathlib import Path

from dotenv import load_dotenv
from google import genai
from google.genai import types
from qdrant_client import QdrantClient, models

load_dotenv()

CHUNKS_FILE = Path("data/chunks.json")
QDRANT_PATH = "qdrant_data"
COLLECTION_NAME = "contract_chunks"
EMBED_MODEL = "gemini-embedding-001"
OUTPUT_DIMENSIONALITY = 768
MAX_RETRIES = 3
RETRY_DELAY_SECONDS = 2
PROGRESS_EVERY = 5

LIMIT = None  # set to None to process the full chunk list

genai_client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])


def embed_chunk(text):
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            result = genai_client.models.embed_content(
                model=EMBED_MODEL,
                contents=text,
                config=types.EmbedContentConfig(
                    output_dimensionality=OUTPUT_DIMENSIONALITY,
                ),
            )
            return result.embeddings[0].values
        except Exception as exc:
            if attempt == MAX_RETRIES:
                return None
            print(f"  retry {attempt}/{MAX_RETRIES} after error: {exc}")
            time.sleep(RETRY_DELAY_SECONDS)


with open(CHUNKS_FILE, "r", encoding="utf-8") as f:
    all_chunks = json.load(f)

indexed_chunks = list(enumerate(all_chunks))
if LIMIT is not None:
    indexed_chunks = indexed_chunks[:LIMIT]

qdrant_client = QdrantClient(path=QDRANT_PATH)

collection_ready = qdrant_client.collection_exists(COLLECTION_NAME)

existing_ids = set()
if collection_ready:
    next_offset = None
    while True:
        records, next_offset = qdrant_client.scroll(
            collection_name=COLLECTION_NAME,
            with_payload=False,
            with_vectors=False,
            limit=1000,
            offset=next_offset,
        )
        existing_ids.update(record.id for record in records)
        if next_offset is None:
            break

remaining_chunks = [(i, chunk) for i, chunk in indexed_chunks if i not in existing_ids]
skipped = len(indexed_chunks) - len(remaining_chunks)
indexed_chunks = remaining_chunks
if skipped:
    print(f"Skipping {skipped} chunks already present in the collection.")

succeeded = 0
failed = 0

for processed, (i, chunk) in enumerate(indexed_chunks, start=1):
    embedding = embed_chunk(chunk["text"])

    if embedding is None:
        failed += 1
        print(f"FAILED chunk {i}: {chunk['source_file']} page {chunk['page_number']}")
        continue

    if not collection_ready:
        qdrant_client.create_collection(
            collection_name=COLLECTION_NAME,
            vectors_config=models.VectorParams(
                size=len(embedding),
                distance=models.Distance.COSINE,
            ),
        )
        collection_ready = True

    qdrant_client.upsert(
        collection_name=COLLECTION_NAME,
        points=[
            models.PointStruct(
                id=i,
                vector=embedding,
                payload={
                    "text": chunk["text"],
                    "source_file": chunk["source_file"],
                    "page_number": chunk["page_number"],
                },
            )
        ],
    )
    succeeded += 1

    if processed % PROGRESS_EVERY == 0:
        print(f"Processed {processed}/{len(indexed_chunks)} chunks...")

final_count = qdrant_client.count(collection_name=COLLECTION_NAME).count if collection_ready else 0

print("\nSummary:")
print(f"Succeeded: {succeeded}")
print(f"Failed: {failed}")
print(f"Collection point count: {final_count}")

qdrant_client.close()
