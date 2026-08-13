import argparse
import json
import os
import time
from pathlib import Path

from google.genai import types

from rag_answer import (
    COLLECTION_NAME as DEFAULT_COLLECTION,
    GENERATION_MODEL,
    answer_question,
    genai_client,
    qdrant_client,
)

EVAL_SET_FILE = Path("data/eval_set.json")
NO_ANSWER_SET_FILE = Path("data/no_answer_set.json")
RESULTS_FILE = Path("results_reranked.json")

MAX_RETRIES = 6
RETRY_DELAY_SECONDS = 5

FAITHFULNESS_LABELS = {"FAITHFUL", "PARTIAL", "UNFAITHFUL"}
REFUSAL_LABELS = {"CORRECT", "INCORRECT"}


COHERE_RATE_LIMIT_BACKOFF_SECONDS = 65  # Cohere trial key: 10 calls/min, no retry-after hint given


def get_retry_delay_seconds(exc, default):
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

    if type(exc).__name__ == "TooManyRequestsError" and getattr(exc, "status_code", None) == 429:
        return COHERE_RATE_LIMIT_BACKOFF_SECONDS

    return default


def call_with_retry(fn, *args, **kwargs):
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            return fn(*args, **kwargs)
        except Exception as exc:
            if attempt == MAX_RETRIES:
                raise
            delay = get_retry_delay_seconds(exc, RETRY_DELAY_SECONDS)
            print(f"  retry {attempt}/{MAX_RETRIES} after error: {exc}; waiting {delay:.1f}s")
            time.sleep(delay)


def load_existing_results(path):
    """Load prior results so a resumed run can skip questions already answered."""
    if not path.exists():
        return [], []
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    return data.get("eval_results", []), data.get("no_answer_results", [])


def save_results(path, eval_results, no_answer_results):
    """Write the whole results file atomically.

    Called after every question, so a run that dies partway - on a quota wall,
    a kill, or a crash - keeps everything it had already judged. Writing to a
    temp file and replacing means a death mid-write cannot leave a truncated
    file that the next run would fail to parse.
    """
    payload = {
        "eval_results": sorted(eval_results, key=lambda r: r["id"]),
        "no_answer_results": sorted(no_answer_results, key=lambda r: r["id"]),
    }
    tmp_path = path.with_suffix(path.suffix + ".tmp")
    with open(tmp_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    os.replace(tmp_path, path)


def parse_verdict(text, allowed_labels):
    normalized = text.strip().upper()
    for label in allowed_labels:
        if label in normalized:
            return label
    return "UNKNOWN"


def judge_faithfulness(question, answer, retrieved_chunks, expected_answer):
    context = "\n\n".join(
        f"[Source: {chunk['source_file']}, page {chunk['page_number']}]\n{chunk['text']}"
        for chunk in retrieved_chunks
    )
    prompt = f"""You are evaluating whether a generated answer is faithfully supported by the retrieved context it was generated from.

Question: {question}

Retrieved context:
{context}

Generated answer:
{answer}

Reference answer (for context on what a correct answer should contain, not for exact wording match):
{expected_answer}

Judge whether every claim in the generated answer is actually supported by the retrieved context above. Respond with exactly one word: FAITHFUL, PARTIAL, or UNFAITHFUL.
"""
    response = call_with_retry(
        genai_client.models.generate_content,
        model=GENERATION_MODEL,
        contents=prompt,
        config=types.GenerateContentConfig(temperature=0),
    )
    return parse_verdict(response.text, FAITHFULNESS_LABELS)


def judge_refusal(question, answer, note):
    prompt = f"""The question below cannot be answered from the available documents.

Question: {question}
Why it's unanswerable: {note}

Generated answer: {answer}

Did the generated answer correctly decline to answer (state that the information isn't available, rather than guessing or fabricating an answer)? Respond with exactly one word: CORRECT or INCORRECT.
"""
    response = call_with_retry(
        genai_client.models.generate_content,
        model=GENERATION_MODEL,
        contents=prompt,
        config=types.GenerateContentConfig(temperature=0),
    )
    return parse_verdict(response.text, REFUSAL_LABELS)


def is_hit(entry, retrieved_chunks):
    return any(
        chunk["source_file"] == entry["source_file"]
        and chunk["page_number"] in entry["expected_pages"]
        for chunk in retrieved_chunks
    )


def run_eval_set(eval_set, results_file, results, no_answer_results,
                 collection_name=DEFAULT_COLLECTION, use_reranking=True,
                 use_hybrid=False):
    done_ids = {r["id"] for r in results}
    skipped = sum(1 for entry in eval_set if entry["id"] in done_ids)
    if skipped:
        print(f"Skipping {skipped} eval questions already present in the results file.")

    for entry in eval_set:
        if entry["id"] in done_ids:
            continue
        print(f"[{entry['id']}/50] {entry['question'][:70]}...")
        result = call_with_retry(
            answer_question,
            entry["question"],
            collection_name=collection_name,
            use_reranking=use_reranking,
            use_hybrid=use_hybrid,
        )
        hit = is_hit(entry, result["retrieved_chunks"])
        faithfulness = judge_faithfulness(
            entry["question"],
            result["answer"],
            result["retrieved_chunks"],
            entry["expected_answer"],
        )
        results.append({
            "id": entry["id"],
            "document": entry["document"],
            "type": entry["type"],
            "question": entry["question"],
            "expected_answer": entry["expected_answer"],
            "expected_pages": entry["expected_pages"],
            "answer": result["answer"],
            "hit": hit,
            "faithfulness": faithfulness,
            "retrieved_sources": [
                {
                    "text": chunk["text"],
                    "source_file": chunk["source_file"],
                    "page_number": chunk["page_number"],
                    "similarity_score": chunk["similarity_score"],
                    "rerank_score": chunk["rerank_score"],
                }
                for chunk in result["retrieved_chunks"]
            ],
        })
        save_results(results_file, results, no_answer_results)
    return results


def run_no_answer_set(no_answer_set, results_file, results, eval_results,
                      collection_name=DEFAULT_COLLECTION, use_reranking=True,
                      use_hybrid=False):
    done_ids = {r["id"] for r in results}
    skipped = sum(1 for entry in no_answer_set if entry["id"] in done_ids)
    if skipped:
        print(f"Skipping {skipped} no-answer questions already present in the results file.")

    for entry in no_answer_set:
        if entry["id"] in done_ids:
            continue
        print(f"[no-answer {entry['id']}/5] {entry['question'][:70]}...")
        result = call_with_retry(
            answer_question,
            entry["question"],
            collection_name=collection_name,
            use_reranking=use_reranking,
            use_hybrid=use_hybrid,
        )
        refusal_verdict = judge_refusal(entry["question"], result["answer"], entry["note"])
        results.append({
            "id": entry["id"],
            "document": entry["document"],
            "question": entry["question"],
            "note": entry["note"],
            "answer": result["answer"],
            "correctly_refused": refusal_verdict == "CORRECT",
            "refusal_verdict": refusal_verdict,
            "retrieved_sources": [
                {
                    "text": chunk["text"],
                    "source_file": chunk["source_file"],
                    "page_number": chunk["page_number"],
                    "similarity_score": chunk["similarity_score"],
                    "rerank_score": chunk["rerank_score"],
                }
                for chunk in result["retrieved_chunks"]
            ],
        })
        save_results(results_file, eval_results, results)
    return results


def print_summary(eval_results, no_answer_results):
    total = len(eval_results)
    hits = sum(1 for r in eval_results if r["hit"])
    print(f"\nHit rate: {hits}/{total} ({100 * hits / total:.1f}%)")

    print("\nFaithfulness breakdown:")
    for label in ["FAITHFUL", "PARTIAL", "UNFAITHFUL", "UNKNOWN"]:
        count = sum(1 for r in eval_results if r["faithfulness"] == label)
        if count or label != "UNKNOWN":
            print(f"  {label}: {count} ({100 * count / total:.1f}%)")

    correct_refusals = sum(1 for r in no_answer_results if r["correctly_refused"])
    total_no_answer = len(no_answer_results)
    print(f"\nRefusal accuracy: {correct_refusals}/{total_no_answer} ({100 * correct_refusals / total_no_answer:.1f}%)")


def parse_args():
    parser = argparse.ArgumentParser(
        description="Run the RAG eval set against a Qdrant collection."
    )
    parser.add_argument(
        "--collection",
        default=DEFAULT_COLLECTION,
        help=f"Qdrant collection to query (default: {DEFAULT_COLLECTION}).",
    )
    parser.add_argument(
        "--results-file",
        type=Path,
        default=RESULTS_FILE,
        help=f"Where to write results (default: {RESULTS_FILE}).",
    )
    parser.add_argument(
        "--no-rerank",
        action="store_true",
        help="Skip Cohere reranking and use raw vector-similarity order "
             "(default: reranking on).",
    )
    parser.add_argument(
        "--hybrid",
        action="store_true",
        help="Fuse BM25 with vector search (RRF) before reranking "
             "(default: vector search only). Requires a collection whose point "
             "ids match data/chunks_structured.json.",
    )
    return parser.parse_args()


def main():
    args = parse_args()
    use_reranking = not args.no_rerank
    print(f"Collection: {args.collection}")
    print(f"Results file: {args.results_file}")
    print(f"Reranking: {'on' if use_reranking else 'off'}")
    print(f"Hybrid (BM25 + RRF): {'on' if args.hybrid else 'off'}\n")

    with open(EVAL_SET_FILE, "r", encoding="utf-8") as f:
        eval_set = json.load(f)
    with open(NO_ANSWER_SET_FILE, "r", encoding="utf-8") as f:
        no_answer_set = json.load(f)

    eval_results, no_answer_results = load_existing_results(args.results_file)
    if eval_results or no_answer_results:
        print(f"Resuming from {args.results_file}: "
              f"{len(eval_results)} eval and {len(no_answer_results)} no-answer "
              f"results already present.\n")

    run_eval_set(eval_set, args.results_file, eval_results, no_answer_results,
                 args.collection, use_reranking, args.hybrid)
    run_no_answer_set(no_answer_set, args.results_file, no_answer_results, eval_results,
                      args.collection, use_reranking, args.hybrid)

    print_summary(eval_results, no_answer_results)
    save_results(args.results_file, eval_results, no_answer_results)

    qdrant_client.close()


if __name__ == "__main__":
    main()
