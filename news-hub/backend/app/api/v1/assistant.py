"""AI Assistant API routes with streaming chat and RAG support."""

import asyncio
import json
from datetime import datetime
from typing import AsyncGenerator, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import StreamingResponse
from loguru import logger

from app.core.deps import get_current_user
from app.db.mongo import mongodb
from app.schemas.assistant import (
    AugmentedSearchRequest,
    AugmentedSearchResponseData,
    ChatRequest,
    ChatResponseData,
    ClassifyRequest,
    ClassifyResponseData,
    DiscoverSourcesRequest,
    DiscoverSourcesResponseData,
    ExternalSearchOptionsResponseData,
    ExternalSearchRequest,
    ExternalSearchResponseData,
    ExternalSearchResultItem,
    ExternalSearchStatusResponseData,
    IngestJobStatusResponseData,
    IngestOneRequest,
    IngestOneResponseData,
    SearchIngestRequest,
    SearchIngestResponseData,
    SummarizeRequest,
    SummarizeResponseData,
)
from app.schemas.audit import AuditFeedback, AuditLogResponse
from app.schemas.response import PaginatedData, ResponseBase, success_response
from app.schemas.user import UserInDB
from app.services.ai.assistant_service import AssistantService
from app.services.ai.audit import AuditLogger

router = APIRouter(prefix="/assistant", tags=["AI Assistant"])


def _service_error_to_http(error: ValueError) -> HTTPException:
    """Map service-level ValueError to HTTPException."""
    message = str(error)
    if "not found" in message.lower():
        return HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=message,
        )
    return HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail=message,
    )


@router.post("/chat", response_model=ResponseBase[ChatResponseData])
async def chat_with_assistant(
    request: ChatRequest,
    current_user: UserInDB = Depends(get_current_user),
):
    """Chat with AI assistant, with SSE streaming by default."""
    service = AssistantService()
    messages: List[dict] = [m.model_dump() for m in request.messages]

    if not request.stream:
        chunks = []
        async for chunk in service.chat(messages=messages, user_id=current_user.id):
            chunks.append(chunk)
        return success_response(data=ChatResponseData(reply="".join(chunks)))

    async def event_generator() -> AsyncGenerator[str, None]:
        try:
            async for delta in service.chat(messages=messages, user_id=current_user.id):
                payload = json.dumps({"type": "delta", "content": delta})
                yield f"data: {payload}\n\n"
            yield 'data: {"type": "done"}\n\n'
        except Exception as e:
            error_payload = json.dumps({"type": "error", "content": str(e)})
            yield f"data: {error_payload}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.post("/chat-rag", response_model=ResponseBase[ChatResponseData])
async def chat_with_rag(
    request: ChatRequest,
    current_user: UserInDB = Depends(get_current_user),
):
    """
    Chat with RAG-enabled AI assistant.

    The AI can autonomously retrieve information from:
    - User's news library (Elasticsearch)
    - Recent news (MongoDB)
    - External web search (SearXNG/Tavily)
    """
    from app.services.ai.rag_assistant import RAGAssistant

    service = RAGAssistant()
    messages: List[dict] = [m.model_dump() for m in request.messages]

    if not request.stream:
        chunks = []
        async for chunk in service.chat_with_rag(
            messages=messages, user_id=current_user.id
        ):
            chunks.append(chunk)
        return success_response(data=ChatResponseData(reply="".join(chunks)))

    async def event_generator() -> AsyncGenerator[str, None]:
        try:
            async for delta in service.chat_with_rag(
                messages=messages, user_id=current_user.id
            ):
                payload = json.dumps({"type": "delta", "content": delta})
                yield f"data: {payload}\n\n"
            yield 'data: {"type": "done"}\n\n'
        except Exception as e:
            error_payload = json.dumps({"type": "error", "content": str(e)})
            yield f"data: {error_payload}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.post("/summarize", response_model=ResponseBase[SummarizeResponseData])
async def summarize_news(
    request: SummarizeRequest,
    current_user: UserInDB = Depends(get_current_user),
):
    """Summarize a news article with AI/fallback mode."""
    service = AssistantService()
    try:
        data = await service.summarize(news_id=request.news_id, user_id=current_user.id)
        return success_response(data=data)
    except ValueError as e:
        raise _service_error_to_http(e)


@router.post("/classify", response_model=ResponseBase[ClassifyResponseData])
async def classify_news(
    request: ClassifyRequest,
    current_user: UserInDB = Depends(get_current_user),
):
    """Classify a news article to suggested tags."""
    service = AssistantService()

    rules = await mongodb.db.tag_rules.find(
        {"user_id": current_user.id, "is_active": True}
    ).to_list(length=1000)
    available_tags = sorted(
        {
            str(rule.get("tag_name", "")).strip()
            for rule in rules
            if str(rule.get("tag_name", "")).strip()
        }
    )

    try:
        data = await service.classify(
            news_id=request.news_id,
            user_id=current_user.id,
            available_tags=available_tags,
        )
        return success_response(data=data)
    except ValueError as e:
        raise _service_error_to_http(e)


@router.post(
    "/discover-sources",
    response_model=ResponseBase[DiscoverSourcesResponseData],
)
async def discover_sources(
    request: DiscoverSourcesRequest,
    current_user: UserInDB = Depends(get_current_user),
):
    """Discover source suggestions for a topic."""
    service = AssistantService()
    data = await service.discover_sources(topic=request.topic, user_id=current_user.id)
    return success_response(data=data)


@router.post(
    "/search",
    response_model=ResponseBase[AugmentedSearchResponseData],
)
async def augmented_search(
    request: AugmentedSearchRequest,
    current_user: UserInDB = Depends(get_current_user),
):
    """AI-augmented search combining internal library + external web results."""
    service = AssistantService()
    data = await service.augmented_search(
        query=request.query,
        user_id=current_user.id,
        include_external=request.include_external,
        persist_external=request.persist_external,
        persist_mode=request.persist_mode,
        external_provider=request.external_provider,
        max_external_results=request.max_external_results,
        time_range=request.time_range,
        language=request.language,
        engines=request.engines,
    )
    return success_response(data=data)


@router.get(
    "/external-search/options",
    response_model=ResponseBase[ExternalSearchOptionsResponseData],
)
async def external_search_options(
    current_user: UserInDB = Depends(get_current_user),
):
    """Get external provider options and capabilities for frontend controls."""
    _ = current_user
    service = AssistantService()
    payload = await service.external_search_options()
    data = ExternalSearchOptionsResponseData(
        default_provider=str(payload.get("default_provider", "auto")),
        fallback_provider=str(payload.get("fallback_provider", "tavily")),
        providers=payload.get("providers", []),
    )
    return success_response(data=data)


@router.get(
    "/external-search/status",
    response_model=ResponseBase[ExternalSearchStatusResponseData],
)
async def external_search_status(
    current_user: UserInDB = Depends(get_current_user),
):
    """Get provider runtime health status."""
    _ = current_user
    service = AssistantService()
    payload = await service.external_search_status()
    data = ExternalSearchStatusResponseData(
        default_provider=str(payload.get("default_provider", "auto")),
        fallback_provider=str(payload.get("fallback_provider", "tavily")),
        healthy_provider_count=int(payload.get("healthy_provider_count", 0)),
        providers=payload.get("providers", []),
    )
    return success_response(data=data)


@router.post(
    "/search/ingest",
    response_model=ResponseBase[SearchIngestResponseData],
)
async def queue_search_ingest(
    request: SearchIngestRequest,
    current_user: UserInDB = Depends(get_current_user),
):
    """Queue ingestion for selected external search results."""
    service = AssistantService()
    try:
        payload = await service.queue_search_ingestion(
            user_id=current_user.id,
            session_id=request.session_id,
            selected_urls=request.selected_urls,
            persist_mode=request.persist_mode,
        )
    except ValueError as e:
        raise _service_error_to_http(e)
    return success_response(data=SearchIngestResponseData(**payload))


@router.get(
    "/ingest-jobs/{job_id}",
    response_model=ResponseBase[IngestJobStatusResponseData],
)
async def get_ingest_job(
    job_id: str,
    current_user: UserInDB = Depends(get_current_user),
):
    """Fetch status for an ingestion job."""
    service = AssistantService()
    job = await service.get_ingest_job(user_id=current_user.id, job_id=job_id)
    if not job:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Ingest job not found",
        )
    data = IngestJobStatusResponseData(
        job_id=str(job["_id"]),
        status=job.get("status", "unknown"),
        session_id=job.get("session_id", ""),
        persist_mode=job.get("persist_mode", "snippet"),
        total_items=job.get("total_items", 0),
        processed_items=job.get("processed_items", 0),
        stored_items=job.get("stored_items", 0),
        failed_items=job.get("failed_items", 0),
        retry_count=job.get("retry_count", 0),
        average_quality_score=job.get("average_quality_score", 0.0),
        error_message=job.get("error_message"),
        created_at=job.get("created_at", datetime.utcnow()),
        updated_at=job.get("updated_at", datetime.utcnow()),
    )
    return success_response(data=data)


# === External Search (pure, no RRF fusion) ===


@router.post(
    "/external-search",
    response_model=ResponseBase[ExternalSearchResponseData],
)
async def external_search(
    request: ExternalSearchRequest,
    current_user: UserInDB = Depends(get_current_user),
):
    """Pure external search via SearXNG/Tavily — no internal ES mixing."""
    _ = current_user
    from app.services.ai.search_providers import ExternalSearchQuery, ExternalSearchRouter

    router_inst = ExternalSearchRouter()
    query = ExternalSearchQuery(
        query=request.query,
        max_results=request.max_results,
        time_range=request.time_range,
        language=request.language,
    )
    execution = await router_inst.search(request=query, provider=request.provider)

    items = [
        ExternalSearchResultItem(
            title=r.title,
            url=r.url,
            description=r.description,
            source_name=r.source_name,
            score=r.score,
            provider=r.provider,
            engine=r.engine,
            published_at=r.published_at.isoformat() if r.published_at else None,
        )
        for r in execution.results
    ]
    return success_response(
        data=ExternalSearchResponseData(
            query=request.query,
            results=items,
            total=len(items),
            provider_used=execution.provider_used,
        )
    )


# === Ingest One (crawl + persist single URL) ===


@router.post(
    "/ingest-one",
    response_model=ResponseBase[IngestOneResponseData],
)
async def ingest_one(
    request: IngestOneRequest,
    current_user: UserInDB = Depends(get_current_user),
):
    """Crawl a single URL with crawl4ai and ingest into user's library."""
    from app.services.ai.virtual_source import VirtualSourceManager
    from app.services.collector.webpage_extractor import WebpageExtractor

    extractor = WebpageExtractor()

    # Crawl with 15s timeout; fallback to snippet on failure
    extracted = {}
    try:
        extracted = await asyncio.wait_for(
            extractor.extract(request.url), timeout=15.0
        )
    except asyncio.TimeoutError:
        logger.warning(f"Crawl timeout for {request.url}, falling back to snippet")
    except Exception as e:
        logger.warning(f"Crawl failed for {request.url}: {e}")

    # Build the item to ingest
    title = (extracted.get("title") or request.title or "").strip()
    description = (extracted.get("description") or request.description or "").strip()
    content = extracted.get("content", "")
    quality_score = extracted.get("quality_score", 0.0)

    if not title and not content:
        # Nothing useful extracted and no fallback title
        title = request.title or request.url
        description = request.description

    item = {
        "title": title,
        "url": request.url,
        "description": description,
        "content": content,
        "image_url": extracted.get("image_url"),
        "published_at": extracted.get("published_at"),
        "author": extracted.get("author", ""),
        "score": quality_score,
    }

    stored = await VirtualSourceManager.ingest_results(
        user_id=current_user.id,
        provider=request.provider,
        items=[item],
    )

    if stored > 0:
        # Retrieve the just-inserted news_id
        doc = await mongodb.db.news.find_one(
            {"user_id": current_user.id, "url": request.url},
            sort=[("created_at", -1)],
        )
        news_id = str(doc["_id"]) if doc else None
        return success_response(
            data=IngestOneResponseData(
                success=True,
                news_id=news_id,
                quality_score=quality_score,
                message="入库成功",
            )
        )

    return success_response(
        data=IngestOneResponseData(
            success=False,
            quality_score=quality_score,
            message="文章已存在或入库失败",
        )
    )


# === Audit Log Endpoints ===


@router.get(
    "/audit-logs",
    response_model=ResponseBase[PaginatedData[AuditLogResponse]],
)
async def get_audit_logs(
    current_user: UserInDB = Depends(get_current_user),
    action: Optional[str] = Query(None, description="Filter by action type"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
):
    """Retrieve paginated AI audit logs for the current user."""
    logs, total = await AuditLogger.get_logs(
        user_id=current_user.id,
        action=action,
        page=page,
        page_size=page_size,
    )

    items = [
        AuditLogResponse(
            id=log["_id"],
            action=log.get("action", ""),
            input_summary=log.get("input_summary", ""),
            output_summary=log.get("output_summary", ""),
            model=log.get("model", ""),
            latency_ms=log.get("latency_ms", 0),
            token_usage=log.get("token_usage", {}),
            quality_signals=log.get("quality_signals", {}),
            created_at=log["created_at"],
        )
        for log in logs
    ]

    return success_response(
        data=PaginatedData(
            items=items,
            total=total,
            page=page,
            page_size=page_size,
            has_more=(page * page_size) < total,
        )
    )


@router.post(
    "/audit-logs/{log_id}/feedback",
    response_model=ResponseBase,
)
async def submit_audit_feedback(
    log_id: str,
    body: AuditFeedback,
    current_user: UserInDB = Depends(get_current_user),
):
    """Record user feedback (positive/negative) on an AI action."""
    updated = await AuditLogger.record_feedback(
        log_id=log_id,
        user_id=current_user.id,
        feedback=body.feedback,
    )
    if not updated:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Audit log not found",
        )
    return success_response(message="Feedback recorded")
