import json
import math
import os
import re
from collections import Counter, defaultdict
from pathlib import Path

import cohere
from dotenv import load_dotenv
from google import genai
from google.genai import types
from qdrant_client import QdrantClient

load_dotenv()

QDRANT_PATH = "qdrant_data"
COLLECTION_NAME = "contract_chunks"
EMBED_MODEL = "gemini-embedding-001"
OUTPUT_DIMENSIONALITY = 768
GENERATION_MODEL = "gemini-3.1-flash-lite"
COHERE_RERANK_MODEL = "rerank-v3.5"
RERANK_CANDIDATE_K = 20

# Hybrid retrieval: lexical BM25 fused with vector search before reranking.
CHUNKS_FILE = Path("data/chunks_structured.json")
HYBRID_CANDIDATE_K = 20
RRF_K = 60
BM25_K1 = 1.5
BM25_B = 0.75

# Below this BM25 top score, the lexical hits are generic contract boilerplate
# ("signed", "parties", "capacity") rather than a distinctive match, and fusing
# them dilutes a good vector ranking. Such questions skip fusion entirely.
# Measured over the 50 eval questions the scores run 10.2 to 99.2 with no
# natural gap; 20.0 sits near the 25th percentile and gates off the bottom 14.
BM25_MIN_TOP_SCORE = 20.0

# Retrieval-confidence gate, deliberately set well below where real answers
# live. Its only job is to catch retrieval that is decisively irrelevant - an
# off-topic question whose best chunk scores near zero (measured at 0.0358 for
# "how to prune tomato plants") - and skip a pointless generation call.
#
# It does NOT attempt to judge answerability. That is classify_refusal's job,
# which reads the generated text and can tell "the passages do not state the
# rates" from a real answer; a relevance score cannot. An earlier value of
# 0.4077 (the lowest eval top-1, less a margin) tried to do both and was too
# close to genuine answers: eval question 36 is a hit at 0.4577, leaving only
# 0.05 of headroom before correct answers would be refused outright.
REFUSAL_THRESHOLD = 0.15
REFUSAL_MESSAGE = "I don't have reliable information on that."

genai_client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])
qdrant_client = QdrantClient(path=QDRANT_PATH)
cohere_client = cohere.ClientV2(api_key=os.environ["COHERE_API_KEY"])


def tokenize(text):
    """Lowercase and split on runs of non-alphanumeric characters."""
    return [token for token in re.split(r"[^a-z0-9]+", text.lower()) if token]


class BM25Index:
    """Okapi BM25 over the chunk corpus, built in-process.

    Document i is chunk i, which is also that chunk's Qdrant point id, so a
    lexical ranking and a vector ranking can be fused on the same key.
    """

    def __init__(self, documents):
        self.doc_count = len(documents)
        self.doc_lengths = []
        self.term_freqs = []
        self.postings = defaultdict(list)
        document_freq = Counter()

        for doc_id, text in enumerate(documents):
            tokens = tokenize(text)
            freqs = Counter(tokens)
            self.doc_lengths.append(len(tokens))
            self.term_freqs.append(freqs)
            document_freq.update(freqs.keys())
            for term in freqs:
                self.postings[term].append(doc_id)

        self.avg_doc_length = (
            sum(self.doc_lengths) / self.doc_count if self.doc_count else 0.0
        )
        self.idf = {
            term: math.log(1 + (self.doc_count - freq + 0.5) / (freq + 0.5))
            for term, freq in document_freq.items()
        }

    def top_n(self, query, n):
        """Return [(doc_id, score)] for the n best-scoring documents."""
        scores = defaultdict(float)

        for term in tokenize(query):
            idf = self.idf.get(term)
            if idf is None:  # term appears in no document
                continue
            for doc_id in self.postings[term]:
                freq = self.term_freqs[doc_id][term]
                length_norm = (
                    1 - BM25_B + BM25_B * self.doc_lengths[doc_id] / self.avg_doc_length
                    if self.avg_doc_length
                    else 1.0
                )
                scores[doc_id] += idf * freq * (BM25_K1 + 1) / (
                    freq + BM25_K1 * length_norm
                )

        return sorted(scores.items(), key=lambda item: item[1], reverse=True)[:n]


_bm25_index = None
_bm25_chunks = None


def get_bm25_index():
    """Build the BM25 index on first use and keep it for the process lifetime.

    Built lazily rather than at import so that callers which never ask for
    hybrid search pay neither the load time nor the memory.
    """
    global _bm25_index, _bm25_chunks
    if _bm25_index is None:
        with open(CHUNKS_FILE, "r", encoding="utf-8") as f:
            _bm25_chunks = json.load(f)
        _bm25_index = BM25Index([chunk["text"] for chunk in _bm25_chunks])
    return _bm25_index, _bm25_chunks


def reciprocal_rank_fusion(ranked_lists, k=RRF_K):
    """Fuse ranked id lists by summing 1 / (k + rank), rank starting at 1."""
    scores = defaultdict(float)
    for ranked_ids in ranked_lists:
        for rank, doc_id in enumerate(ranked_ids, start=1):
            scores[doc_id] += 1.0 / (k + rank)
    return sorted(scores.items(), key=lambda item: item[1], reverse=True)


def vector_candidates(points):
    """Candidate dicts straight from the vector hit list."""
    return [
        {
            "text": point.payload["text"],
            "source_file": point.payload["source_file"],
            "page_number": point.payload["page_number"],
            "similarity_score": point.score,
            "rerank_score": None,
        }
        for point in points
    ]


def hybrid_candidates(question, points):
    """Fuse the vector hit list with a BM25 hit list for the same question.

    Returns (candidates, bm25_top_score). `candidates` is None when BM25's best
    score falls below BM25_MIN_TOP_SCORE, meaning the caller should fall back to
    vector-only ranking rather than fuse in undistinctive lexical matches.
    """
    index, chunks = get_bm25_index()

    # Fusion keys on chunk position, which only lines up when the collection
    # was built from this chunk file. Fail loudly rather than fuse nonsense.
    for point in points:
        if point.id >= len(chunks) or chunks[point.id]["text"] != point.payload["text"]:
            raise ValueError(
                f"use_hybrid requires a collection built from {CHUNKS_FILE}; "
                f"point id {point.id} does not match that chunk's text"
            )

    bm25_ranked = index.top_n(question, HYBRID_CANDIDATE_K)
    bm25_top_score = bm25_ranked[0][1] if bm25_ranked else 0.0

    if bm25_top_score < BM25_MIN_TOP_SCORE:
        return None, bm25_top_score

    vector_ids = [point.id for point in points]
    similarity_by_id = {point.id: point.score for point in points}
    bm25_ids = [doc_id for doc_id, _ in bm25_ranked]

    fused = reciprocal_rank_fusion([vector_ids, bm25_ids])[:HYBRID_CANDIDATE_K]

    candidates = [
        {
            "text": chunks[doc_id]["text"],
            "source_file": chunks[doc_id]["source_file"],
            "page_number": chunks[doc_id]["page_number"],
            # None when BM25 surfaced a chunk the vector search never returned.
            "similarity_score": similarity_by_id.get(doc_id),
            "rerank_score": None,
        }
        for doc_id, _ in fused
    ]
    return candidates, bm25_top_score


def embed_question(question):
    result = genai_client.models.embed_content(
        model=EMBED_MODEL,
        contents=question,
        config=types.EmbedContentConfig(
            output_dimensionality=OUTPUT_DIMENSIONALITY,
        ),
    )
    return result.embeddings[0].values


def build_prompt(question, retrieved_chunks):
    passages = "\n\n".join(
        f"[Source: {chunk['source_file']}, page {chunk['page_number']}]\n{chunk['text']}"
        for chunk in retrieved_chunks
    )
    return f"""Answer the question using ONLY the passages below. Cite the source file and page number for every claim you make. If the passages do not contain enough information to answer the question, say so plainly instead of guessing.

Passages:
{passages}

Question: {question}

Answer:"""


def rerank_chunks(question, candidates, top_k):
    response = cohere_client.rerank(
        model=COHERE_RERANK_MODEL,
        query=question,
        documents=[chunk["text"] for chunk in candidates],
        top_n=top_k,
    )
    reranked = []
    for item in response.results:
        chunk = dict(candidates[item.index])
        chunk["rerank_score"] = item.relevance_score
        reranked.append(chunk)
    return reranked


REFUSAL_LABELS = ("REFUSAL", "ANSWER")


def classify_refusal(answer_text: str) -> bool:
    """True when answer_text declines to answer rather than answering.

    Deterministic at temperature=0, matching how run_eval.py judges the
    no-answer set. It is NOT the same function as run_eval.judge_refusal:
    that one also takes the eval set's `note` explaining why a question is
    unanswerable, and grades whether declining was *correct*. Here there is no
    such premise - only the answer text - so this asks the simpler question of
    whether the text declines at all.

    Makes its own generation call; callers pay one extra call per use.
    """
    if not answer_text or not answer_text.strip():
        return False

    prompt = f"""Classify whether the text below answers a question or declines to answer it.

Text:
{answer_text}

Does this text decline to answer - saying the information is not available, not
present in the provided documents, or that it cannot answer - rather than giving
a substantive answer? Respond with exactly one word: REFUSAL or ANSWER.
"""
    response = genai_client.models.generate_content(
        model=GENERATION_MODEL,
        contents=prompt,
        config=types.GenerateContentConfig(temperature=0),
    )

    normalized = (response.text or "").strip().upper()
    for label in REFUSAL_LABELS:  # REFUSAL first: checked in priority order
        if label in normalized:
            return label == "REFUSAL"
    return False


def answer_question(
    question: str,
    top_k: int = 5,
    use_reranking: bool = True,
    collection_name: str = COLLECTION_NAME,
    use_hybrid: bool = False,
) -> dict:
    query_vector = embed_question(question)

    if use_hybrid:
        vector_limit = HYBRID_CANDIDATE_K
    elif use_reranking:
        vector_limit = RERANK_CANDIDATE_K
    else:
        vector_limit = top_k

    results = qdrant_client.query_points(
        collection_name=collection_name,
        query=query_vector,
        limit=vector_limit,
    )

    fused_this_question = False
    bm25_top_score = None

    if use_hybrid:
        candidates, bm25_top_score = hybrid_candidates(question, results.points)
        if candidates is None:
            # BM25 found nothing distinctive; fall back to vector-only ranking,
            # which is exactly the non-hybrid path into reranking.
            candidates = vector_candidates(results.points)
        else:
            fused_this_question = True
    else:
        candidates = vector_candidates(results.points)

    if use_reranking and candidates:
        retrieved_chunks = rerank_chunks(question, candidates, top_k)
    else:
        retrieved_chunks = candidates

    assert all(chunk.get("text") for chunk in retrieved_chunks), (
        "retrieved_chunks must include the actual chunk text, not just metadata "
        "(callers persist this for later re-judging without needing to re-embed)"
    )

    top_rerank_score = retrieved_chunks[0]["rerank_score"] if retrieved_chunks else None

    # Retrieval-confidence refusal: the best chunk is too weak to answer from, so
    # refuse without spending a generation call. Distinct from a content-based
    # refusal, where the model reads good chunks and reports the answer is absent
    # - that path still runs generation exactly as before.
    if top_rerank_score is not None and top_rerank_score < REFUSAL_THRESHOLD:
        return {
            "question": question,
            "answer": REFUSAL_MESSAGE,
            "retrieved_chunks": retrieved_chunks,
            "used_hybrid": fused_this_question,
            "bm25_top_score": bm25_top_score,
            "top_rerank_score": top_rerank_score,
            "refusal_type": "threshold",
            "generation_skipped": True,
        }

    prompt = build_prompt(question, retrieved_chunks)

    response = genai_client.models.generate_content(
        model=GENERATION_MODEL,
        contents=prompt,
    )

    return {
        "question": question,
        "answer": response.text,
        "retrieved_chunks": retrieved_chunks,
        # Whether BM25 was actually fused for this question, not merely requested.
        "used_hybrid": fused_this_question,
        "bm25_top_score": bm25_top_score,
        "top_rerank_score": top_rerank_score,
        # None here even when the model declines in prose - that is a
        # content-based refusal, which is not this gate.
        "refusal_type": None,
        "generation_skipped": False,
    }


if __name__ == "__main__":
    test_questions = [
        "Who is named as the escrow agent in the Escrow Agreement, and what is its registered office?",
        "Under what state's law is the Adams Golf Endorsement Agreement governed?",
        "What are the actual dollar rates or fees IBM charges Bluefly for the hosting Services?",
    ]

    for question in test_questions:
        result = answer_question(question)
        print(f"Q: {result['question']}")
        print(f"A: {result['answer']}")
        sources = {
            f"{chunk['source_file']} (page {chunk['page_number']})"
            for chunk in result["retrieved_chunks"]
        }
        print("Sources cited:")
        for source in sorted(sources):
            print(f"  - {source}")
        print()

    qdrant_client.close()
