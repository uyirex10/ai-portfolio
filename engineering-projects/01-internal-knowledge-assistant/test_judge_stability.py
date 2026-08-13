import json

from rag_answer import COLLECTION_NAME, RERANK_CANDIDATE_K, embed_question, qdrant_client, rerank_chunks
from run_eval import judge_faithfulness

QUESTION_ID = 47

with open("data/eval_set.json", "r", encoding="utf-8") as f:
    eval_set = json.load(f)
with open("results_reranked.json", "r", encoding="utf-8") as f:
    reranked = json.load(f)

entry = next(e for e in eval_set if e["id"] == QUESTION_ID)
result = next(r for r in reranked["eval_results"] if r["id"] == QUESTION_ID)

# Reconstruct the exact retrieved context by recomputing retrieval (deterministic:
# embeddings + Qdrant search + Cohere rerank), not by re-generating the answer.
query_vector = embed_question(entry["question"])
candidates_raw = qdrant_client.query_points(
    collection_name=COLLECTION_NAME,
    query=query_vector,
    limit=RERANK_CANDIDATE_K,
)
candidates = [
    {
        "text": p.payload["text"],
        "source_file": p.payload["source_file"],
        "page_number": p.payload["page_number"],
        "similarity_score": p.score,
        "rerank_score": None,
    }
    for p in candidates_raw.points
]
retrieved_chunks = rerank_chunks(entry["question"], candidates, 5)

print(f"Question {QUESTION_ID}: {entry['question']}")
print(f"Answer under test: {result['answer'][:100]}...\n")

verdicts = []
for i in range(1, 6):
    verdict = judge_faithfulness(
        entry["question"],
        result["answer"],
        retrieved_chunks,
        entry["expected_answer"],
    )
    verdicts.append(verdict)
    print(f"Run {i}: {verdict}")

print()
if len(set(verdicts)) == 1:
    print(f"STABLE: all 5 runs returned {verdicts[0]}")
else:
    print(f"NOT STABLE: got {verdicts}")

qdrant_client.close()
