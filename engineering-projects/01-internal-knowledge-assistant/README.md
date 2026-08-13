# Internal Knowledge Assistant: RAG Done Properly

A grounded document-QA system for a law/insurance firm scenario. Answers cite the exact source page. When the corpus genuinely doesn't contain the answer, the system says so instead of guessing, because in this domain a confident wrong answer is worse than no answer at all.

## The problem

A law/insurance firm has 800 policy documents. Staff ask the same handful of questions against them every week. Right now that means manually searching PDFs or asking a colleague who might remember. The system needed to answer from those documents with a citation to the exact page, and refuse cleanly when the documents don't contain the answer.

## Results

| Version                                            | Hit rate  | Faithful   | Unfaithful | Refusal accuracy |
| -------------------------------------------------- | --------- | ---------- | ---------- | ---------------- |
| Naive baseline                                     | 70.0%     | 98.0%      | 0.0%       | 100%             |
| + Reranking                                        | 82.0%     | 98.0%      | 2.0%       | 100%             |
| Structure-aware chunking alone                     | 74.0%     | 94.0%      | 6.0%       | 100%             |
| **Structure-aware chunking + reranking (shipped)** | **86.0%** | **100.0%** | **0.0%**   | **100%**         |

50-question hand-verified eval set, every page citation checked against the real PDF before being treated as ground truth, plus a 5-question no-answer set to measure refusal accuracy.

## What this does

- Answers natural-language questions against a corpus of real legal contracts, with page-level citations
- Refuses to answer when the corpus doesn't contain reliable information, via a two-layer mechanism (below), rather than guessing
- Serves over a FastAPI endpoint with a Streamlit demo UI in front of it
- Ships with a fully reproducible, hand-verified evaluation methodology, not just a demo

## Architecture

PDFs are parsed and chunked (structure-aware, respecting the contract's own numbered clauses), each chunk embedded and stored in Qdrant (local embedded mode, no server required). A question is embedded the same way, the top 20 candidates retrieved by vector similarity, then re-scored by a cross-encoder reranker down to the final top 5. Those go to the LLM with instructions to answer only from what's given and cite the page. Two independent refusal mechanisms sit around this: a cheap confidence-based gate for decisively irrelevant retrieval, and a deterministic content classifier that catches any refusal regardless of cause. Served via FastAPI, with a Streamlit UI as one client of that API, not a special case.

## Tools used

Python, FastAPI, Streamlit, Qdrant (local embedded mode), Gemini API via `google-genai` (embeddings: `gemini-embedding-001`, 768-dim; generation and judging: `gemini-3.1-flash-lite`), Cohere rerank free tier (`rerank-v3.5`).

## Corpus

CUAD v1, a 60-document random sample (seed=42), CC BY 4.0, The Atticus Project.

|                   | Naive collection         | Structured collection (shipped)                                                       |
| ----------------- | ------------------------ | ------------------------------------------------------------------------------------- |
| Qdrant collection | `contract_chunks`        | `contract_chunks_structured`                                                          |
| Chunks            | 2,700                    | 3,685                                                                                 |
| Chunking          | Blind ~500-token windows | Clause/section-boundary aware, sub-split with overlap, short fragments merged/dropped |

## Key design decisions

**Chunking.** Naive baseline used blind ~500-token windows per page. The structure-aware version detects numbered clause/section boundaries and splits along those instead, so each chunk is a complete unit of meaning rather than an arbitrary cut. Scoped to within a single page only (doesn't stitch a clause across a page break), a known, documented limitation rather than a hidden one.

**Eval methodology.** 50 hand-written Q&A pairs plus 5 no-answer candidates, every citation verified against the real physical PDF page via direct phrase search before being trusted as ground truth, not assumed from page labels. A "hit" requires matching both source file and page number; multi-page citations count as a hit if any cited page is retrieved. Faithfulness is judged by a separate, deterministic (`temperature=0`) LLM call, confirmed stable via repeated-call testing before being trusted.

**Reranking.** Retrieve a wide net (top 20) by vector similarity, then re-score with Cohere's reranker down to the final top 5. Added +12 hit-rate points consistently, whether applied to naive or structured chunks, evidence that chunking and reranking fix independent failure modes rather than overlapping work.

**The refusal mechanism, two layers, not one.** Originally planned as a single confidence threshold. Investigation disproved that: a no-answer question about specific dollar rates scored higher on the reranker than 28 of the 50 genuinely answerable questions, because the retrieved passages were topically relevant, they just didn't contain the specific figure asked for. Relevance and answer-presence are different properties; no confidence score can encode that difference. The system now uses content-grounded refusal (the LLM judging whether retrieved text actually answers the question) as the primary, proven mechanism (5/5 refusal accuracy, including that exact case), and a narrow, conservative confidence floor purely to skip generation on decisively irrelevant retrieval, a cost optimization, not a safety mechanism. This is a deliberate, evidence-based departure from the original plan.

**Hybrid search, explored and not adopted.** Implemented BM25 fused with vector search via Reciprocal Rank Fusion. Measured result: one regression (a question with no distinctive vocabulary let generic lexical matches crowd out the correct chunk), and after fixing that regression with a confidence gate, the result was verdict-for-verdict identical to reranking alone on all 50 questions. The reranker already recovers what hybrid search was meant to add on this corpus. Kept in the codebase, disabled by default, with a documented hypothesis for when it might help (a lexically-dense question set), not pursued further since it isn't earning its complexity here.

**Docker, attempted and honestly documented.** Docker Desktop's backend failed to start; investigated rather than accepted at face value. Hardware virtualization was confirmed present and enabled (ruling that out), and a WSL2-not-installed inference was reached but not fully confirmed (the commands that would settle it require elevated access, deliberately not used). Independent of the exact cause, this machine's free RAM (under 400 MB before Docker even attempts to start) is already below where it previously crashed on a 16 MiB allocation, so this wasn't pursued further. A `Dockerfile` exists, written to standard practice, explicitly labeled as untested.

## Known limitations

- Structure-aware chunking doesn't stitch a clause across a page boundary, single-page scope only.
- Some pages carry very little retrievable information despite chunking successfully (redaction markers, exhibit cover pages), a real corpus characteristic, not a bug.
- A non-breaking-space encoding artifact in pypdf's extracted text inflated token counts by 23.7% in the original naive/reranked pipeline, found and fixed in the structure-aware chunker. The naive-vs-reranked comparison is unaffected (identical underlying text); the structure-aware comparison is confounded by this fix happening alongside the chunking-strategy change.
- 19.6% of structured chunks open at a bare sub-clause number with no preceding heading, a systemic property of clause-level splitting on multi-part lists. Reranking recovers every resulting failure in the shipped configuration; a heading-breadcrumb fix (requiring a full re-embed) was evaluated and deliberately deferred, since it would fix a failure mode invisible in production.
- 2 of the 7 remaining retrieval misses (ids 44, 18) are signature-block questions, near-identical boilerplate across all 60 contracts. The other 5 (ids 41, 10, 45, 12, 50) are "confident wrong-document" errors, a document-scoping problem outside what retrieval-quality upgrades can fix. Faithfulness remains protected either way; zero unfaithful answers even on missed retrieval.
- A genuinely ambiguous (but potentially answerable) question currently gets refused identically to a truly off-topic one, rather than prompted for clarification. Logged as real future work, not a bug fix.
- Installing Streamlit into the same venv as the API silently downgraded a shared dependency FastAPI also relies on. Verified FastAPI still serves correctly, but this is the concrete motivating case for containerizing each service separately.
- Free-tier API limits (Gemini embedding: 1,000/day; Cohere trial: 10 calls/min) required resumable, skip-logic batch design throughout, a real infrastructure constraint, not just an implementation detail.

## Testing

Beyond the eval methodology above, deliberate failure testing against the live system: a corrupted PDF (crashed the entire chunking run before the fix; now isolates per-document failures and continues), an adversarial/ambiguous question (refused cleanly, no hallucination), and a missing Qdrant collection (server survived and returned a clean, non-leaking JSON error rather than hanging or crashing, after a fix from a bare plain-text 500).

## How to run

1. Clone the repo, create a venv, `pip install -r requirements.txt`.
2. Add a `.env` file with `GEMINI_API_KEY` and `COHERE_API_KEY`.
3. Build the corpus and vector store if not already present: `chunk_corpus_structured.py`, then `embed_and_store_structured.py` (resumable; expect multiple days on the Gemini free tier's 1,000 embeddings/day cap).
4. Start the API: `uvicorn api:app --host 127.0.0.1 --port 8000`.
5. Start the demo UI: `streamlit run streamlit_app.py`, then open `http://localhost:8501`.
