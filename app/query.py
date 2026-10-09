from __future__ import annotations

import logging
from time import perf_counter

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from pydantic import BaseModel, Field
from starlette.concurrency import run_in_threadpool

from app.core.config import Settings
from app.services.cache import QueryCacheService
from app.services.embedding import EmbeddingService
from app.services.generator import GeneratorService
from app.services.metrics import QueryMetricsService
from app.services.retriever import RetrieverService

logger = logging.getLogger(__name__)
router = APIRouter(tags=["query"])


class QueryRequest(BaseModel):
    question: str = Field(..., min_length=3, description="Healthcare-focused natural language question.")


class QueryResponse(BaseModel):
    answer: str
    retrieved_chunks: list[dict]
    response_time_ms: float


def get_embedding_service(request: Request) -> EmbeddingService:
    return request.app.state.embedding_service


def get_retriever_service(request: Request) -> RetrieverService:
    return request.app.state.retriever_service


def get_generator_service(request: Request) -> GeneratorService:
    return request.app.state.generator_service


def get_query_cache_service(request: Request) -> QueryCacheService:
    return request.app.state.query_cache_service


def get_metrics_service(request: Request) -> QueryMetricsService:
    return request.app.state.metrics_service


def get_settings(request: Request) -> Settings:
    return request.app.state.settings


def _trim_chunks(chunks: list[dict], max_chars: int) -> list[dict]:
    limit = max(1, max_chars)
    trimmed: list[dict] = []
    for chunk in chunks:
        item = dict(chunk)
        text = item.get("text", "")
        if isinstance(text, str) and len(text) > limit:
            item["text"] = text[: limit - 3].rstrip() + "..."
        trimmed.append(item)
    return trimmed


@router.post("/query", response_model=QueryResponse)
async def query_documents(
    body: QueryRequest,
    top_k: int | None = Query(
        default=None,
        ge=1,
        le=50,
        description="Optional retrieval depth override (defaults to TOP_K from config).",
    ),
    threshold: float | None = Query(
        default=None,
        ge=0.0,
        le=1.0,
        description="Optional similarity threshold override (defaults to SIMILARITY_THRESHOLD from config).",
    ),
    use_retrieval: bool = Query(
        default=True,
        description="Disable retrieval to benchmark generation-only baseline.",
    ),
    bypass_cache: bool = Query(
        default=False,
        description="Bypass query cache (useful for controlled evaluation runs).",
    ),
    embedding_service: EmbeddingService = Depends(get_embedding_service),
    retriever_service: RetrieverService = Depends(get_retriever_service),
    generator_service: GeneratorService = Depends(get_generator_service),
    query_cache_service: QueryCacheService = Depends(get_query_cache_service),
    metrics_service: QueryMetricsService = Depends(get_metrics_service),
    settings: Settings = Depends(get_settings),
) -> QueryResponse:
    started_at = perf_counter()
    question = body.question.strip()
    if not question:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Question cannot be empty.")

    effective_top_k = top_k if top_k is not None else settings.top_k
    effective_threshold = threshold if threshold is not None else settings.similarity_threshold

    cache_used = False
    cache_key = f"{question}|k={effective_top_k}|t={effective_threshold}|r={int(use_retrieval)}"
    cached_response = None if bypass_cache else query_cache_service.get(cache_key)
    if cached_response is not None:
        cache_used = True
        response_time_ms = round((perf_counter() - started_at) * 1000, 2)
        metrics_service.record_query(response_time_ms=response_time_ms, cache_hit=True)
        logger.info(
            "Query=%s | Retrieved=%s | CacheUsed=%s | ResponseTimeMs=%s",
            question,
            len(cached_response["retrieved_chunks"]),
            cache_used,
            response_time_ms,
        )
        return QueryResponse(
            answer=cached_response["answer"],
            retrieved_chunks=cached_response["retrieved_chunks"],
            response_time_ms=response_time_ms,
        )

    try:
        retrieved: list[dict] = []
        contexts: list[str] = []
        if use_retrieval:
            query_embedding = await run_in_threadpool(embedding_service.embed_query, question)
            retrieved = await run_in_threadpool(
                retriever_service.retrieve,
                question,
                query_embedding,
                effective_top_k,
                effective_threshold,
            )
            contexts = [item["text"] for item in retrieved]

        if not use_retrieval:
            answer = await run_in_threadpool(generator_service.generate_answer, question, [])
        elif not retrieved:
            answer = "Not found"
        elif contexts:
            answer = await run_in_threadpool(generator_service.generate_answer, question, contexts)
        else:
            answer = "Not found"
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Query failed.") from exc

    response_time_ms = round((perf_counter() - started_at) * 1000, 2)
    metrics_service.record_query(response_time_ms=response_time_ms, cache_hit=False)
    returned_chunks = _trim_chunks(retrieved, settings.max_return_chunk_chars)
    if not bypass_cache:
        query_cache_service.set(
            cache_key,
            {
                "answer": answer,
                "retrieved_chunks": returned_chunks,
            },
        )

    logger.info(
        "Query=%s | Retrieved=%s | CacheUsed=%s | ResponseTimeMs=%s | top_k=%s | threshold=%s | use_retrieval=%s | bypass_cache=%s",
        question,
        len(retrieved),
        cache_used,
        response_time_ms,
        effective_top_k,
        effective_threshold,
        use_retrieval,
        bypass_cache,
    )
    logger.info("Retrieved document sources: %s", [chunk.get("source") for chunk in retrieved])
    for idx, chunk in enumerate(retrieved, start=1):
        logger.info(
            "Top chunk %s | similarity=%s | source=%s | text=%s",
            idx,
            chunk.get("similarity", chunk.get("score")),
            chunk.get("source"),
            chunk.get("text", "")[:220],
        )

    return QueryResponse(
        answer=answer,
        retrieved_chunks=returned_chunks,
        response_time_ms=response_time_ms,
    )
