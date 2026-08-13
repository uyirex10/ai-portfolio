import json
from pathlib import Path

from qdrant_client import models

from rag_answer import COHERE_RERANK_MODEL, COLLECTION_NAME, cohere_client, qdrant_client
from run_eval import call_with_retry, judge_faithfulness, judge_refusal

RESULTS_FILE = Path("results_reranked.json")
MATCH_TOLERANCE = 0.01


def get_page_candidates(source_file, page_number):
    records, _ = call_with_retry(
        qdrant_client.scroll,
        collection_name=COLLECTION_NAME,
        with_payload=True,
        with_vectors=False,
        limit=100,
        scroll_filter=models.Filter(
            must=[
                models.FieldCondition(key="source_file", match=models.MatchValue(value=source_file)),
                models.FieldCondition(key="page_number", match=models.MatchValue(value=page_number)),
            ]
        ),
    )
    return records


def resolve_chunk_text(question, source):
    records = get_page_candidates(source["source_file"], source["page_number"])

    if len(records) == 1:
        return records[0].payload["text"]

    if not records:
        return None

    texts = [r.payload["text"] for r in records]
    response = call_with_retry(
        cohere_client.rerank,
        model=COHERE_RERANK_MODEL,
        query=question,
        documents=texts,
        top_n=len(texts),
    )
    matches = [
        item for item in response.results
        if abs(item.relevance_score - source["rerank_score"]) <= MATCH_TOLERANCE
    ]
    if len(matches) == 1:
        return records[matches[0].index].payload["text"]
    return None


def reconstruct_retrieved_chunks(question, retrieved_sources):
    chunks = []
    for source in retrieved_sources:
        text = resolve_chunk_text(question, source)
        if text is None:
            return None
        chunks.append({
            "text": text,
            "source_file": source["source_file"],
            "page_number": source["page_number"],
        })
    return chunks


def backfill_eval_results(eval_results, flagged):
    updated = 0
    for i, entry in enumerate(eval_results, start=1):
        print(f"[eval {i}/{len(eval_results)}] id={entry['id']}: {entry['question'][:60]}...")
        chunks = reconstruct_retrieved_chunks(entry["question"], entry["retrieved_sources"])
        if chunks is None:
            print(f"  FLAGGED FOR MANUAL REVIEW: eval id {entry['id']} (ambiguous chunk match)")
            flagged.append(("eval", entry["id"]))
            continue
        entry["faithfulness"] = judge_faithfulness(
            entry["question"],
            entry["answer"],
            chunks,
            entry["expected_answer"],
        )
        updated += 1
    return updated


def backfill_no_answer_results(no_answer_results, flagged):
    updated = 0
    for i, entry in enumerate(no_answer_results, start=1):
        print(f"[no-answer {i}/{len(no_answer_results)}] id={entry['id']}: {entry['question'][:60]}...")
        chunks = reconstruct_retrieved_chunks(entry["question"], entry["retrieved_sources"])
        if chunks is None:
            print(f"  FLAGGED FOR MANUAL REVIEW: no-answer id {entry['id']} (ambiguous chunk match)")
            flagged.append(("no-answer", entry["id"]))
            continue
        verdict = judge_refusal(entry["question"], entry["answer"], entry["note"])
        entry["refusal_verdict"] = verdict
        entry["correctly_refused"] = verdict == "CORRECT"
        updated += 1
    return updated


def main():
    with open(RESULTS_FILE, "r", encoding="utf-8") as f:
        data = json.load(f)

    flagged = []
    eval_updated = backfill_eval_results(data["eval_results"], flagged)
    no_answer_updated = backfill_no_answer_results(data["no_answer_results"], flagged)

    with open(RESULTS_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    print(f"\nUpdated {eval_updated}/{len(data['eval_results'])} eval entries.")
    print(f"Updated {no_answer_updated}/{len(data['no_answer_results'])} no-answer entries.")
    if flagged:
        print(f"Flagged for manual review ({len(flagged)}):")
        for kind, qid in flagged:
            print(f"  {kind} id {qid}")
    else:
        print("No entries flagged for manual review.")

    qdrant_client.close()


if __name__ == "__main__":
    main()
