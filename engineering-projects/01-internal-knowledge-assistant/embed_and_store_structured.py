import json
import os
import time
from pathlib import Path

from dotenv import load_dotenv
from google import genai
from google.genai import types
from qdrant_client import QdrantClient, models

load_dotenv()

CHUNKS_FILE = Path("data/chunks_structured.json")
QDRANT_PATH = "qdrant_data"
COLLECTION_NAME = "contract_chunks_structured"
EMBED_MODEL = "gemini-embedding-001"
OUTPUT_DIMENSIONALITY = 768
MAX_RETRIES = 3
FALLBACK_RETRY_DELAY_SECONDS = 2  # transient non-quota errors with no retryDelay hint
RATE_LIMIT_FALLBACK_DELAY_SECONDS = 50  # 429s with no retryDelay hint
PROGRESS_EVERY = 5

LIMIT = None  # set to None to process the full chunk list

genai_client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])


class DailyQuotaExhausted(Exception):
    """Raised when a 429 names a per-day quota, which no retry can clear."""


def is_daily_quota_error(exc):
    """True when a 429 names a per-day quota rather than a per-minute one.

    Per-minute limits clear on their own within about a minute, so waiting is
    the right move. A per-day quota resets at midnight Pacific and its
    retryDelay hint is misleadingly short -- observed at ~50s -- so retrying
    burns the retry budget, fails anyway, and does so for every remaining
    chunk. Stopping immediately is both faster and clearer.
    """
    details = getattr(exc, "details", None)
    if isinstance(details, dict):
        for item in details.get("error", {}).get("details", []):
            if item.get("@type", "").endswith("QuotaFailure"):
                for violation in item.get("violations", []):
                    if "PerDay" in violation.get("quotaId", ""):
                        return True

    # Fall back to the string form in case the SDK does not surface details.
    return "PerDay" in str(exc)


def is_rate_limit_error(exc):
    """True when the error is a 429, whether or not it carries structured details."""
    if getattr(exc, "code", None) == 429:
        return True
    text = str(exc)
    return "429" in text or "RESOURCE_EXHAUSTED" in text


def fallback_delay_seconds(exc):
    """Delay to use when a retryable error carries no retryDelay hint.

    Some 429s from this API arrive bare -- no RetryInfo, no quotaId. Waiting the
    generic 2s burns all three attempts inside ~6s against a per-minute window
    that needs ~50s, which loses the chunk *and* spends daily quota to do it.
    Other transient errors keep the short delay, since they usually clear at once.
    """
    if is_rate_limit_error(exc):
        return RATE_LIMIT_FALLBACK_DELAY_SECONDS
    return FALLBACK_RETRY_DELAY_SECONDS


def get_retry_delay_seconds(exc, default):
    """Read the server's own retryDelay out of a 429, as run_eval.py does.

    Gemini returns a RetryInfo entry such as {"retryDelay": "27s"} on rate
    limits. Honouring it beats a fixed sleep: too short and every retry burns
    against the same closed window, too long and a full corpus run stalls.
    The trailing +1s matches run_eval.py, covering clock skew at the boundary.
    """
    details = getattr(exc, "details", None)
    if isinstance(details, dict):
        for item in details.get("error", {}).get("details", []):
            if item.get("@type", "").endswith("RetryInfo"):
                delay_str = item.get("retryDelay", "")
                if delay_str.endswith("s"):
                    try:
                        return float(delay_str[:-1]) + 1
                    except ValueError:
                        pass

    return default


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
            if is_daily_quota_error(exc):
                raise DailyQuotaExhausted(str(exc)) from exc
            if attempt == MAX_RETRIES:
                return None
            delay = get_retry_delay_seconds(exc, fallback_delay_seconds(exc))
            print(f"  retry {attempt}/{MAX_RETRIES} after error: {exc}; waiting {delay:.1f}s")
            time.sleep(delay)


with open(CHUNKS_FILE, "r", encoding="utf-8") as f:
    all_chunks = json.load(f)

# Enumerated before any slicing, so a chunk's point ID is its position in the
# full list and stays stable across resumed runs.
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
daily_quota_hit = False

for processed, (i, chunk) in enumerate(indexed_chunks, start=1):
    try:
        embedding = embed_chunk(chunk["text"])
    except DailyQuotaExhausted as exc:
        daily_quota_hit = True
        print(f"\nDAILY QUOTA EXHAUSTED - stopping the run immediately.")
        print(f"Successfully embedded this run: {succeeded} chunks")
        print(f"Stopped at chunk ID {i} ({processed}/{len(indexed_chunks)} attempted this run)")
        print(f"Not attempted: {len(indexed_chunks) - processed} chunks")
        print(f"Error: {exc}")
        break

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
print(f"Chunks in source file: {len(all_chunks)}")

if daily_quota_hit:
    print(f"\nRun stopped early on the daily quota, with {len(all_chunks) - final_count} "
          f"chunks still to embed.")
    print("Rerun after the quota resets (midnight Pacific); chunks already stored")
    print("are skipped automatically, so the run picks up where this one left off.")

qdrant_client.close()
