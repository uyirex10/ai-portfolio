import logging

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from rag_answer import answer_question, classify_refusal

logger = logging.getLogger("contract_rag.api")

# The configuration the eval runs settled on: structured chunks with Cohere
# reranking (43/50 hit, 50/50 faithful). Hybrid BM25 is left off - gated or not
# it changed no verdict on the eval set, so it is complexity without measured
# benefit here. The retrieval-confidence gate inside answer_question is always
# active; it needs no flag.
COLLECTION_NAME = "contract_chunks_structured"
TOP_K = 5

app = FastAPI(
    title="Contract RAG API",
    description="Question answering over the CUAD contract corpus.",
)


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    """Return a consistent JSON error instead of FastAPI's plain-text 500.

    The full traceback goes to the server log only. The response deliberately
    carries no exception type, message or stack detail: those leak collection
    names, file paths and library internals to whoever is calling.
    """
    logger.exception(
        "Unhandled exception handling %s %s", request.method, request.url.path
    )
    return JSONResponse(
        status_code=500,
        content={
            "error": "internal_error",
            "detail": "An internal error occurred while processing the request.",
            "path": request.url.path,
        },
    )


class AskRequest(BaseModel):
    question: str = Field(..., min_length=1, description="Question to answer.")


class Citation(BaseModel):
    source_file: str
    page_number: int


class AskResponse(BaseModel):
    question: str
    answer: str
    citations: list[Citation]
    refused: bool
    refusal_type: str | None


def build_citations(retrieved_chunks):
    """One citation per distinct (file, page) among the chunks sent to the model.

    Chunks that made the final top_k only - not the wider candidate pool - and
    deduplicated, since several chunks often come from the same page and a
    caller has no use for the same citation repeated.
    """
    citations = []
    seen = set()
    for chunk in retrieved_chunks:
        key = (chunk["source_file"], chunk["page_number"])
        if key not in seen:
            seen.add(key)
            citations.append(Citation(source_file=key[0], page_number=key[1]))
    return citations


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/ask", response_model=AskResponse)
def ask(request: AskRequest) -> AskResponse:
    result = answer_question(
        request.question,
        top_k=TOP_K,
        use_reranking=True,
        collection_name=COLLECTION_NAME,
    )

    refusal_type = result.get("refusal_type")

    # A "threshold" refusal is already settled - the gate fired and no answer was
    # generated, so there is nothing to classify. Otherwise the model did answer,
    # and that prose may itself be a refusal ("the passages do not contain..."),
    # which only reading the text can reveal. Reporting only; answer_question's
    # own generation call and prompt are untouched.
    if refusal_type is None and classify_refusal(result["answer"]):
        refusal_type = "content"

    return AskResponse(
        question=result["question"],
        answer=result["answer"],
        citations=build_citations(result["retrieved_chunks"]),
        refused=refusal_type is not None,
        refusal_type=refusal_type,
    )
