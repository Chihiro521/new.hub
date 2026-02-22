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
    BatchIngestAllRequest,
    BatchIngestAllResponseData,
    BatchIngestItemResult,
    ChatRequest,
    ChatResponseData,
    ClassifyRequest,
    ClassifyResponseData,
    DeepResearchRequest,
    DeepResearchResponseData,
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
        async for chunk in service.chat(
            messages=messages, user_id=current_user.id, system_prompt=request.system_prompt
        ):
            chunks.append(chunk)
        return success_response(data=ChatResponseData(reply="".join(chunks)))

    async def event_generator() -> AsyncGenerator[str, None]:
        try:
            async for delta in service.chat(
                messages=messages, user_id=current_user.id, system_prompt=request.system_prompt
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


# === Ingest One with SSE progress tracking ===


@router.post("/ingest-one-stream")
async def ingest_one_stream(
    request: IngestOneRequest,
    current_user: UserInDB = Depends(get_current_user),
):
    """Crawl and ingest a single URL with real-time SSE progress tracking."""
    import time as _time

    from app.services.ai.virtual_source import VirtualSourceManager
    from app.services.collector.webpage_extractor import WebpageExtractor

    async def event_stream() -> AsyncGenerator[str, None]:
        def emit(step: str, status: str, message: str, detail: dict = None, elapsed_ms: int = 0):
            payload = {"step": step, "status": status, "message": message, "elapsed_ms": elapsed_ms}
            if detail:
                payload["detail"] = detail
            return f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"

        t_total = _time.monotonic()
        extracted = {}
        crawl_method = "crawl4ai"
        extractor = WebpageExtractor()

        # Step 1: Health check Crawl4AI Docker service
        yield emit("crawler_init", "running", "检查 Crawl4AI 服务...")
        t0 = _time.monotonic()
        try:
            import httpx as _httpx
            from app.core.config import settings as _settings
            async with _httpx.AsyncClient(timeout=5) as _client:
                _health = await _client.get(f"{_settings.crawl4ai_base_url.rstrip('/')}/health")
                _health.raise_for_status()
            ms = int((_time.monotonic() - t0) * 1000)
            yield emit("crawler_init", "done", "Crawl4AI 服务就绪", elapsed_ms=ms)
        except Exception as e:
            ms = int((_time.monotonic() - t0) * 1000)
            yield emit("crawler_init", "warn", f"Crawl4AI 服务不可用: {e}, 将使用备用方案", elapsed_ms=ms)

        # Step 2: Page fetch via Crawl4AI API
        yield emit("page_fetch", "running", f"crawl4ai 抓取: {request.url[:80]}...")
        t0 = _time.monotonic()
        crawl4ai_ok = False
        content = ""
        md_source = ""
        try:
            extracted = await asyncio.wait_for(
                extractor._crawl_via_api(request.url), timeout=150.0
            )
            ms = int((_time.monotonic() - t0) * 1000)
            if extracted and extracted.get("content"):
                content = extracted["content"]
                md_source = "crawl4ai_api"
                crawl4ai_ok = True
                yield emit("page_fetch", "done", f"页面抓取完成 ({len(content)} chars)", detail={
                    "content_length": len(content),
                }, elapsed_ms=ms)
            else:
                yield emit("page_fetch", "warn", "crawl4ai 未提取到内容, 尝试备用方案...", elapsed_ms=ms)
        except asyncio.TimeoutError:
            ms = int((_time.monotonic() - t0) * 1000)
            yield emit("page_fetch", "warn", f"crawl4ai 超时 ({ms}ms), 尝试备用方案...", elapsed_ms=ms)
        except Exception as e:
            ms = int((_time.monotonic() - t0) * 1000)
            yield emit("page_fetch", "warn", f"crawl4ai 异常: {type(e).__name__}: {e}, 尝试备用方案...", elapsed_ms=ms)

        # Step 2b: Fallback to httpx if crawl4ai failed
        if not crawl4ai_ok:
            yield emit("fallback_fetch", "running", "httpx 备用抓取...")
            t0 = _time.monotonic()
            try:
                fallback_result = await asyncio.wait_for(
                    extractor._fallback_extract(request.url), timeout=15.0
                )
                ms = int((_time.monotonic() - t0) * 1000)
                if fallback_result and fallback_result.get("content"):
                    extracted = fallback_result
                    content = fallback_result["content"]
                    md_source = "httpx_fallback"
                    yield emit("fallback_fetch", "done", f"备用抓取完成 ({len(content)} chars)", elapsed_ms=ms)
                    crawl_method = "httpx_fallback"
                else:
                    yield emit("fallback_fetch", "warn", "备用抓取也未获取到正文", elapsed_ms=ms)
                    crawl_method = "all_failed"
            except Exception as e:
                ms = int((_time.monotonic() - t0) * 1000)
                yield emit("fallback_fetch", "error", f"备用抓取也失败: {e}", elapsed_ms=ms)
                crawl_method = "all_failed"

        # Step 3: Content summary
        if content:
            yield emit("markdown_extract", "done", f"Markdown: {len(content)} 字符 (来源: {md_source})", detail={
                "content_length": len(content),
                "source": md_source,
            })
        else:
            yield emit("markdown_extract", "warn", "未提取到正文内容")

        # Step 4: Metadata (already extracted by _crawl_via_api or _fallback_extract)
        title = extracted.get("title", "")
        description = extracted.get("description", "")
        author = extracted.get("author")
        image_url = extracted.get("image_url")
        published_at = extracted.get("published_at")
        quality_score = extracted.get("quality_score", 0.0)

        if extracted:
            yield emit("metadata_parse", "done", "元数据解析完成", detail={
                "title": title[:80] if title else "(空)",
                "author": author,
                "has_image": bool(image_url),
                "has_date": bool(published_at),
            })

        # Step 5: Quality scoring
        if content or title:
            yield emit("quality_check", "done", f"质量评分: {quality_score}", detail={
                "quality_score": quality_score,
                "content_length": len(content),
                "has_title": bool(title),
                "has_description": bool(description),
            })

        # Fallback to request data if extraction failed
        if not title:
            title = request.title or request.url
        if not description:
            description = request.description or ""

        # Quality gate: refuse to store empty articles
        if not content and crawl_method == "all_failed":
            total_ms = int((_time.monotonic() - t_total) * 1000)
            yield emit("db_insert", "skip", "正文为空，跳过入库")
            yield emit("complete", "warn", "入库流程完成（未入库：无正文内容）", detail={
                "success": False,
                "news_id": None,
                "quality_score": 0.0,
                "crawl_method": crawl_method,
                "title": title[:100],
                "content_length": 0,
                "author": author,
                "image_url": image_url,
                "published_at": None,
                "content_preview": "",
            }, elapsed_ms=total_ms)
            return

        # Step 6: Database insert
        yield emit("db_insert", "running", "写入数据库...")
        t0 = _time.monotonic()
        try:
            item = {
                "title": title,
                "url": request.url,
                "description": description,
                "content": content,
                "image_url": image_url,
                "published_at": published_at,
                "author": author or "",
                "score": quality_score,
            }
            stored = await VirtualSourceManager.ingest_results(
                user_id=current_user.id,
                provider=request.provider,
                items=[item],
            )
            ms = int((_time.monotonic() - t0) * 1000)

            news_id = None
            if stored > 0:
                doc = await mongodb.db.news.find_one(
                    {"user_id": current_user.id, "url": request.url},
                    sort=[("created_at", -1)],
                )
                news_id = str(doc["_id"]) if doc else None
                yield emit("db_insert", "done", f"入库成功 (news_id: {news_id})", detail={
                    "news_id": news_id, "stored": stored,
                }, elapsed_ms=ms)
            else:
                yield emit("db_insert", "warn", "文章已存在或入库失败", detail={
                    "stored": 0,
                }, elapsed_ms=ms)
        except Exception as e:
            ms = int((_time.monotonic() - t0) * 1000)
            yield emit("db_insert", "error", f"数据库写入失败: {e}", elapsed_ms=ms)
            news_id = None
            stored = 0

        # Step 7: Complete
        total_ms = int((_time.monotonic() - t_total) * 1000)
        pub_at = published_at
        yield emit("complete", "done" if (stored and stored > 0) else "warn", "入库流程完成", detail={
            "success": bool(stored and stored > 0),
            "news_id": news_id,
            "quality_score": quality_score,
            "crawl_method": crawl_method,
            "title": title[:100],
            "content_length": len(content),
            "author": author,
            "image_url": image_url,
            "published_at": pub_at.isoformat() if hasattr(pub_at, "isoformat") else (str(pub_at) if pub_at else None),
            "content_preview": content[:500] if content else "",
        }, elapsed_ms=total_ms)

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
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
    crawl_method = "crawl4ai"
    try:
        extracted = await asyncio.wait_for(
            extractor.extract(request.url), timeout=15.0
        )
    except asyncio.TimeoutError:
        logger.warning(f"Crawl timeout for {request.url}, falling back to snippet")
        crawl_method = "snippet_timeout"
    except Exception as e:
        logger.warning(f"Crawl failed for {request.url}: {e}")
        crawl_method = "snippet_error"

    if not extracted:
        crawl_method = crawl_method if crawl_method != "crawl4ai" else "snippet_empty"

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

    # Common extracted fields for visualization
    pub_at = extracted.get("published_at")
    extracted_fields = dict(
        extracted_title=title,
        extracted_description=description,
        extracted_content_preview=content[:800] if content else "",
        extracted_author=extracted.get("author"),
        extracted_image_url=extracted.get("image_url"),
        extracted_published_at=pub_at.isoformat() if hasattr(pub_at, "isoformat") else (str(pub_at) if pub_at else None),
        content_length=len(content),
        crawl_method=crawl_method,
    )

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
                **extracted_fields,
            )
        )

    return success_response(
        data=IngestOneResponseData(
            success=False,
            quality_score=quality_score,
            message="文章已存在或入库失败",
            **extracted_fields,
        )
    )


# === Batch Ingest All (crawl + persist multiple URLs) ===


@router.post(
    "/ingest-batch",
    response_model=ResponseBase[BatchIngestAllResponseData],
)
async def ingest_batch(
    request: BatchIngestAllRequest,
    current_user: UserInDB = Depends(get_current_user),
):
    """Batch-crawl multiple URLs with crawl4ai and ingest into user's library."""
    from app.services.ai.virtual_source import VirtualSourceManager
    from app.services.collector.webpage_extractor import WebpageExtractor

    extractor = WebpageExtractor()
    urls = [item.url for item in request.items]
    url_to_input = {item.url: item for item in request.items}

    # Batch crawl with timeout
    batch_results = []
    try:
        batch_results = await asyncio.wait_for(
            extractor.batch_extract(urls), timeout=60.0
        )
    except asyncio.TimeoutError:
        logger.warning("Batch crawl timeout, returning partial results")
    except Exception as e:
        logger.warning(f"Batch crawl failed: {e}")

    url_to_extracted = {url: data for url, data in batch_results}

    item_results: list[BatchIngestItemResult] = []
    quality_sum = 0.0
    quality_count = 0
    succeeded = 0

    for req_item in request.items:
        extracted = url_to_extracted.get(req_item.url, {})
        title = (extracted.get("title") or req_item.title or "").strip()
        description = (extracted.get("description") or req_item.description or "").strip()
        content = extracted.get("content", "")
        quality_score = extracted.get("quality_score", 0.0)

        if not title and not content:
            title = req_item.title or req_item.url

        item = {
            "title": title,
            "url": req_item.url,
            "description": description,
            "content": content,
            "image_url": extracted.get("image_url"),
            "published_at": extracted.get("published_at"),
            "author": extracted.get("author", ""),
            "score": quality_score,
        }

        try:
            stored_count = await VirtualSourceManager.ingest_results(
                user_id=current_user.id,
                provider=request.provider,
                items=[item],
            )
            if stored_count > 0:
                doc = await mongodb.db.news.find_one(
                    {"user_id": current_user.id, "url": req_item.url},
                    sort=[("created_at", -1)],
                )
                news_id = str(doc["_id"]) if doc else None
                item_results.append(
                    BatchIngestItemResult(
                        url=req_item.url,
                        success=True,
                        news_id=news_id,
                        quality_score=quality_score,
                        title=title,
                        content_length=len(content),
                    )
                )
                succeeded += 1
                quality_sum += quality_score
                quality_count += 1
            else:
                item_results.append(
                    BatchIngestItemResult(
                        url=req_item.url,
                        success=False,
                        quality_score=quality_score,
                        title=title,
                        content_length=len(content),
                        error="文章已存在",
                    )
                )
        except Exception as e:
            item_results.append(
                BatchIngestItemResult(
                    url=req_item.url,
                    success=False,
                    error=str(e),
                )
            )

    avg_quality = round(quality_sum / quality_count, 3) if quality_count > 0 else 0.0

    return success_response(
        data=BatchIngestAllResponseData(
            total=len(request.items),
            succeeded=succeeded,
            failed=len(request.items) - succeeded,
            average_quality_score=avg_quality,
            results=item_results,
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


# === Debug: Test crawl4ai extraction ===


@router.get("/debug-crawl")
async def debug_crawl(
    url: str = Query(..., description="URL to test crawl"),
    current_user: UserInDB = Depends(get_current_user),
):
    """Debug endpoint: test Crawl4AI Docker API extraction on a single URL."""
    from app.services.collector.webpage_extractor import WebpageExtractor

    extractor = WebpageExtractor()
    diag: dict = {"url": url, "stages": {}}

    # Stage 1: Health check
    try:
        import httpx
        from app.core.config import settings as _settings
        async with httpx.AsyncClient(timeout=5) as client:
            health = await client.get(f"{_settings.crawl4ai_base_url.rstrip('/')}/health")
            diag["stages"]["health"] = health.json()
    except Exception as e:
        diag["stages"]["health"] = f"FAIL: {e}"
        return success_response(data=diag)

    # Stage 2: Full extraction
    try:
        extracted = await asyncio.wait_for(
            extractor.extract(url), timeout=30.0
        )
        diag["stages"]["extract"] = {
            "title": extracted.get("title", ""),
            "description_length": len(extracted.get("description", "")),
            "content_length": len(extracted.get("content", "")),
            "content_preview": extracted.get("content", "")[:500],
            "quality_score": extracted.get("quality_score", 0),
            "author": extracted.get("author"),
            "published_at": str(extracted.get("published_at")) if extracted.get("published_at") else None,
        }
    except asyncio.TimeoutError:
        diag["stages"]["extract"] = "TIMEOUT (30s)"
    except Exception as e:
        diag["stages"]["extract"] = f"FAIL: {e}"

    return success_response(data=diag)


@router.post("/research", response_model=ResponseBase[ChatResponseData])
async def research_with_agent(
    request: ChatRequest,
    current_user: UserInDB = Depends(get_current_user),
):
    """Chat with LangGraph research agent.

    Uses LangChain/LangGraph for multi-step reasoning with tool calling.
    Supports the same SSE streaming protocol as /chat and /chat-rag.
    """
    from app.services.ai.agents.research_agent import ResearchAgent

    agent = ResearchAgent()
    messages: List[dict] = [m.model_dump() for m in request.messages]

    if not request.stream:
        chunks = []
        async for chunk in agent.chat(messages=messages, user_id=current_user.id):
            chunks.append(chunk)
        return success_response(data=ChatResponseData(reply="".join(chunks)))

    async def event_generator() -> AsyncGenerator[str, None]:
        try:
            async for delta in agent.chat(messages=messages, user_id=current_user.id):
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


@router.post("/deep-research", response_model=ResponseBase[DeepResearchResponseData])
async def deep_research(
    request: DeepResearchRequest,
    current_user: UserInDB = Depends(get_current_user),
):
    """Run multi-step deep research: plan -> search -> read -> synthesize.

    Returns a structured research report with citations.
    Supports SSE streaming for real-time progress updates.
    """
    from app.services.ai.agents.deep_research_agent import DeepResearchAgent

    agent = DeepResearchAgent()

    if not request.stream:
        chunks = []
        async for chunk in agent.research(
            query=request.query,
            user_id=current_user.id,
            system_prompt=request.system_prompt,
        ):
            chunks.append(chunk)
        full_report = "".join(chunks)
        return success_response(
            data=DeepResearchResponseData(query=request.query, report=full_report)
        )

    async def event_generator() -> AsyncGenerator[str, None]:
        try:
            async for delta in agent.research(
                query=request.query,
                user_id=current_user.id,
                system_prompt=request.system_prompt,
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