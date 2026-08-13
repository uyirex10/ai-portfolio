import json
from pathlib import Path

from rag_answer import COLLECTION_NAME, RERANK_CANDIDATE_K, embed_question, qdrant_client, rerank_chunks
from run_eval import judge_faithfulness, judge_refusal

FILES = [
    {"path": Path("results_naive.json"), "use_reranking": False},
    {"path": Path("results_reranked.json"), "use_reranking": True},
]


def reconstruct_retrieved_chunks(question, use_reranking):
    query_vector = embed_question(question)
    candidates_raw = qdrant_client.query_points(
        collection_name=COLLECTION_NAME,
        query=query_vector,
        limit=RERANK_CANDIDATE_K if use_reranking else 5,
    )
    candidates = [
        {
            "text": p.payload["text"],
            "source_file": p.payload["source_file"],
            "page_number": p.payload["page_number"],
        }
        for p in candidates_raw.points
    ]
    if use_reranking:
        return rerank_chunks(question, candidates, 5)
    return candidates


def summarize(eval_results, no_answer_results):
    total = len(eval_results)
    hits = sum(1 for r in eval_results if r["hit"])
    faithfulness_counts = {
        label: sum(1 for r in eval_results if r["faithfulness"] == label)
        for label in ["FAITHFUL", "PARTIAL", "UNFAITHFUL", "UNKNOWN"]
    }
    correct_refusals = sum(1 for r in no_answer_results if r["correctly_refused"])
    return {
        "hit_rate": (hits, total),
        "faithfulness": faithfulness_counts,
        "refusal": (correct_refusals, len(no_answer_results)),
    }


def rejudge_file(path, use_reranking):
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)

    before = summarize(data["eval_results"], data["no_answer_results"])

    for i, entry in enumerate(data["eval_results"], start=1):
        print(f"[{path.name}] eval {i}/{len(data['eval_results'])}: {entry['question'][:60]}...")
        retrieved_chunks = reconstruct_retrieved_chunks(entry["question"], use_reranking)
        entry["faithfulness"] = judge_faithfulness(
            entry["question"],
            entry["answer"],
            retrieved_chunks,
            entry["expected_answer"],
        )

    for i, entry in enumerate(data["no_answer_results"], start=1):
        print(f"[{path.name}] no-answer {i}/{len(data['no_answer_results'])}: {entry['question'][:60]}...")
        refusal_verdict = judge_refusal(entry["question"], entry["answer"], entry["note"])
        entry["refusal_verdict"] = refusal_verdict
        entry["correctly_refused"] = refusal_verdict == "CORRECT"

    after = summarize(data["eval_results"], data["no_answer_results"])

    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    return before, after


def print_side_by_side(label, before, after):
    hb, tb = before["hit_rate"]
    ha, ta = after["hit_rate"]
    print(f"\n{label}")
    print(f"  Hit rate:            {hb}/{tb} -> {ha}/{ta}  (unaffected by judge, shown for reference)")
    print("  Faithfulness:")
    for lbl in ["FAITHFUL", "PARTIAL", "UNFAITHFUL", "UNKNOWN"]:
        cb = before["faithfulness"][lbl]
        ca = after["faithfulness"][lbl]
        if cb or ca:
            print(f"    {lbl:<11} {cb:>2} -> {ca:>2}")
    rb, nb = before["refusal"]
    ra, na = after["refusal"]
    print(f"  Refusal accuracy:    {rb}/{nb} -> {ra}/{na}")


def main():
    summaries = []
    for file_info in FILES:
        before, after = rejudge_file(file_info["path"], file_info["use_reranking"])
        summaries.append((file_info["path"].name, before, after))

    print("\n" + "=" * 70)
    print("UPDATED SUMMARY (deterministic judge, temperature=0)")
    print("=" * 70)
    for name, before, after in summaries:
        print_side_by_side(name, before, after)

    qdrant_client.close()


if __name__ == "__main__":
    main()
