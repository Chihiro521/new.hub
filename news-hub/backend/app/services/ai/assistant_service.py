"""AI assistant orchestration service."""

import asyncio
import hashlib
import json
import re
import time
import uuid
from datetime import datetime, timedelta
from typing import Any, AsyncGenerator, Dict, List, Optional

from bson import ObjectId
from loguru import logger

from app.core.config import settings
from app.db.mongo import mongodb
from app.schemas.assistant import (
    AugmentedSearchResponseData,
    ClassifyResponseData,
    ConversationThread,
    DiscoverSourcesResponseData,
    SearchResultItem,
    SourceSuggestion,
    SummarizeResponseData,
)
from app.services.ai.agents.research_agent import _content_to_text
from app.services.ai.audit import AuditLogger
from app.services.ai.ingestion_service import ExternalIngestionService
from app.services.ai.llm_client import get_llm_client
from app.services.ai.prompts import (
    CLASSIFY_TEMPLATE,
    DISCOVER_SOURCES_TEMPLATE,
    SEARCH_SUMMARY_TEMPLATE,
    SUMMARIZE_TEMPLATE,
    SYSTEM_CHAT,
)
from app.services.ai.search_providers import ExternalSearchQuery, ExternalSearchRouter


class AssistantService:
    """Service layer for AI assistant features."""

    def __init__(self):
        self.client = get_llm_client()
        self.audit = AuditLogger()
        self.external_search_router = ExternalSearchRouter()
        self.external_ingestion = ExternalIngestionService()

    @staticmethod
    def _is_meaningful_chat_chunk(chunk: str) -> bool:
        """Whether a streamed chunk contains real reply text (not tool-status noise)."""
        stripped = chunk.strip()
        if not stripped:
            return False
        # Tool status chunks emitted by ResearchAgent: "[🔍 tool_name...]"
        if re.fullmatch(r"\[🔍\s+.+\.\.\.\]", stripped):
            return False
        return True

    async def _resolve_or_create_thread(
        self, messages: List[dict], user_id: str, thread_id: Optional[str],
    ) -> str:
        """Resolve an existing thread or create a new one. Returns thread_id."""
        if thread_id:
            doc = await mongodb.conversation_threads.find_one(
                {"thread_id": thread_id, "user_id": user_id, "is_archived": {"$ne": True}}
            )
            if not doc:
                thread_id = None

        if not thread_id:
            thread_id = str(uuid.uuid4())
            first_msg = ""
            for m in messages:
                if m.get("role") == "user":
                    first_msg = m.get("content", "")
                    break
            title = first_msg[:50].strip() or "新对话"
            await mongodb.conversation_threads.insert_one({
                "thread_id": thread_id,
                "user_id": user_id,
                "title": title,
                "created_at": datetime.utcnow(),
                "last_message_at": datetime.utcnow(),
                "message_count": 1,
                "last_user_message": first_msg[:200],
                "is_archived": False,
            })
        else:
            last_msg = ""
            for m in reversed(messages):
                if m.get("role") == "user":
                    last_msg = m.get("content", "")
                    break
            await mongodb.conversation_threads.update_one(
                {"thread_id": thread_id},
                {"$set": {
                    "last_message_at": datetime.utcnow(),
                    "last_user_message": last_msg[:200],
                }, "$inc": {"message_count": 1}},
            )
        return thread_id

    async def chat(
        self, messages: List[dict], user_id: str,
        system_prompt: Optional[str] = None,
        thread_id: Optional[str] = None,
    ) -> AsyncGenerator[str, None]:
        """Stream assistant chat response via direct LLM streaming.

        Uses AsyncOpenAI streaming directly — no LangGraph, no tools.
        Fast and reliable for normal conversations.
        """
        thread_id = await self._resolve_or_create_thread(messages, user_id, thread_id)
        yield f"__thread_id__:{thread_id}"

        if self.client is None:
            yield "AI 助手暂不可用，请先配置 OPENAI_API_KEY。"
            return

        t0 = time.monotonic()
        prompt = (system_prompt or SYSTEM_CHAT).strip()
        payload: List[Dict[str, str]] = []
        if prompt:
            payload.append({"role": "system", "content": prompt})
        for msg in messages[-30:]:
            role = str(msg.get("role", "user"))
            if role not in {"user", "assistant", "system"}:
                continue
            content = str(msg.get("content", "")).strip()
            if not content:
                continue
            payload.append({"role": role, "content": content})

        if not payload:
            yield "（消息为空）"
            return

        collected = []
        try:
            stream = await self.client.chat.completions.create(
                model=settings.openai_model,
                messages=payload,
                stream=True,
            )
            async for chunk in stream:
                delta = chunk.choices[0].delta if chunk.choices else None
                if not delta:
                    continue
                # Use robust extraction that handles str / list / dict / nested objects
                text = _content_to_text(getattr(delta, "content", None))
                if not text:
                    text = _content_to_text(getattr(delta, "reasoning_content", None))
                if not text:
                    text = _content_to_text(getattr(delta, "reasoning", None))
                if not text:
                    text = getattr(delta, "text", None) or ""
                if text:
                    collected.append(text)
                    yield text
        except Exception as e:
            logger.error(f"Chat streaming failed: {e}")
            yield f"\n\n抱歉，发生错误：{e}"

        # Fallback: if streaming yielded nothing, try a non-streaming call
        if not collected:
            logger.warning("Chat stream produced no text, falling back to non-streaming call")
            try:
                resp = await self.client.chat.completions.create(
                    model=settings.openai_model,
                    messages=payload,
                    stream=False,
                )
                choice = resp.choices[0] if resp.choices else None
                if choice and choice.message:
                    fallback = _content_to_text(getattr(choice.message, "content", None))
                    if not fallback:
                        fallback = _content_to_text(getattr(choice.message, "reasoning_content", None))
                    if not fallback:
                        fallback = _content_to_text(getattr(choice.message, "reasoning", None))
                    if fallback:
                        collected.append(fallback)
                        yield fallback
            except Exception as e2:
                logger.error(f"Chat non-streaming fallback also failed: {e2}")

        if not collected:
            yield "（模型未返回正文，请稍后重试）"

        await self.audit.log(
            user_id=user_id,
            action="chat",
            input_summary=messages[-1].get("content", "")[:200] if messages else "",
            output_summary="".join(collected)[:200],
            model=settings.openai_model,
            latency_ms=int((time.monotonic() - t0) * 1000),
        )

    async def chat_with_agent(
        self, messages: List[dict], user_id: str,
        system_prompt: Optional[str] = None,
        thread_id: Optional[str] = None,
    ) -> AsyncGenerator[str, None]:
        """Stream assistant chat via LangGraph ResearchAgent (with tools).

        Use this when the user needs tool access (search, scrape, etc.).
        """
        from app.services.ai.agents.research_agent import ResearchAgent

        thread_id = await self._resolve_or_create_thread(messages, user_id, thread_id)
        yield f"__thread_id__:{thread_id}"

        agent = ResearchAgent()
        emitted_meaningful = False
        async for chunk in agent.chat(
            messages=messages, user_id=user_id,
            system_prompt=system_prompt, thread_id=thread_id,
        ):
            if self._is_meaningful_chat_chunk(chunk):
                emitted_meaningful = True
            yield chunk

        # Hard fallback: if LangGraph produced no meaningful text, request one plain response.
        if not emitted_meaningful:
            logger.warning(
                "assistant_chat_empty_reply user_id={} thread_id={} falling back to plain completion",
                user_id,
                thread_id,
            )
            try:
                fallback = await asyncio.wait_for(
                    self._chat_plain_fallback(messages=messages, system_prompt=system_prompt),
                    timeout=15,
                )
            except asyncio.TimeoutError:
                logger.warning("Plain chat fallback timed out (15s) user_id={}", user_id)
                fallback = ""
            if fallback:
                yield fallback
            else:
                yield "（模型未返回正文，请稍后重试）"

    async def summarize(self, news_id: str, user_id: str) -> SummarizeResponseData:
        """Summarize a news item with AI, fallback to extractive summary."""
        t0 = time.monotonic()
        news_doc = await self._get_news_doc(news_id, user_id)

        title = news_doc.get("title", "")
        source = news_doc.get("source_name", "")
        content = news_doc.get("content") or news_doc.get("description") or ""

        if self.client is None:
            summary = self._extractive_summary(content)
            await self.audit.log(
                user_id=user_id,
                action="summarize",
                input_summary=title[:200],
                output_summary=summary[:200],
                latency_ms=int((time.monotonic() - t0) * 1000),
                fallback_used=True,
            )
            return SummarizeResponseData(
                news_id=news_id,
                summary=summary,
                method="extractive",
            )

        prompt = SUMMARIZE_TEMPLATE.format(title=title, source=source, content=content)
        try:
            cache_key = f"summarize::{settings.openai_model}::{prompt}"
            summary = await self._cached_completion(
                cache_key=cache_key,
                messages=[
                    {"role": "system", "content": SYSTEM_CHAT},
                    {"role": "user", "content": prompt},
                ],
                model=settings.openai_model,
            )
            if not summary:
                raise ValueError("Empty AI summary")

            await self.audit.log(
                user_id=user_id,
                action="summarize",
                input_summary=title[:200],
                output_summary=summary[:200],
                model=settings.openai_model,
                latency_ms=int((time.monotonic() - t0) * 1000),
            )
            return SummarizeResponseData(news_id=news_id, summary=summary, method="ai")
        except Exception as e:
            logger.error(f"AI summarize failed for news {news_id}: {e}")
            summary = self._extractive_summary(content)
            await self.audit.log(
                user_id=user_id,
                action="summarize",
                input_summary=title[:200],
                output_summary=summary[:200],
                model=settings.openai_model,
                latency_ms=int((time.monotonic() - t0) * 1000),
                fallback_used=True,
                error=str(e),
            )
            return SummarizeResponseData(
                news_id=news_id,
                summary=summary,
                method="extractive",
            )

    async def classify(
        self, news_id: str, user_id: str, available_tags: List[str]
    ) -> ClassifyResponseData:
        """Classify a news item into user tag candidates."""
        t0 = time.monotonic()
        news_doc = await self._get_news_doc(news_id, user_id)
        title = news_doc.get("title", "")

        if self.client is None:
            await self.audit.log(
                user_id=user_id,
                action="classify",
                input_summary=title[:200],
                output_summary="[]",
                latency_ms=int((time.monotonic() - t0) * 1000),
                fallback_used=True,
            )
            return ClassifyResponseData(
                news_id=news_id,
                suggested_tags=[],
                method="rule_based",
            )

        prompt = CLASSIFY_TEMPLATE.format(
            title=title,
            content=news_doc.get("content") or news_doc.get("description") or "",
            available_tags=", ".join(available_tags),
        )

        try:
            cache_key = f"classify::{settings.openai_model}::{prompt}"
            raw = await self._cached_completion(
                cache_key=cache_key,
                messages=[
                    {"role": "system", "content": SYSTEM_CHAT},
                    {"role": "user", "content": prompt},
                ],
                model=settings.openai_model,
            )
            raw = raw or "[]"
            parsed = json.loads(raw)
            tags = [str(tag) for tag in parsed if isinstance(tag, str)]

            await self.audit.log(
                user_id=user_id,
                action="classify",
                input_summary=title[:200],
                output_summary=json.dumps(tags, ensure_ascii=False)[:200],
                model=settings.openai_model,
                latency_ms=int((time.monotonic() - t0) * 1000),
            )
            return ClassifyResponseData(
                news_id=news_id, suggested_tags=tags, method="ai"
            )
        except Exception as e:
            logger.error(f"AI classify failed for news {news_id}: {e}")
            await self.audit.log(
                user_id=user_id,
                action="classify",
                input_summary=title[:200],
                model=settings.openai_model,
                latency_ms=int((time.monotonic() - t0) * 1000),
                fallback_used=True,
                error=str(e),
            )
            return ClassifyResponseData(
                news_id=news_id,
                suggested_tags=[],
                method="rule_based",
            )

    async def discover_sources(
        self, topic: str, user_id: str
    ) -> DiscoverSourcesResponseData:
        """Discover source suggestions for a topic."""
        t0 = time.monotonic()

        if self.client is None:
            await self.audit.log(
                user_id=user_id,
                action="discover_sources",
                input_summary=topic[:200],
                output_summary="[]",
                latency_ms=int((time.monotonic() - t0) * 1000),
                fallback_used=True,
            )
            return DiscoverSourcesResponseData(topic=topic, suggestions=[])

        prompt = DISCOVER_SOURCES_TEMPLATE.format(topic=topic)
        try:
            response = await self.client.chat.completions.create(
                model=settings.openai_model,
                messages=[
                    {"role": "system", "content": SYSTEM_CHAT},
                    {"role": "user", "content": prompt},
                ],
                stream=False,
            )
            raw = (response.choices[0].message.content or "[]").strip()
            suggestions_payload = self._parse_json_array(raw)
            suggestions = [SourceSuggestion(**item) for item in suggestions_payload]

            usage = response.usage
            await self.audit.log(
                user_id=user_id,
                action="discover_sources",
                input_summary=topic[:200],
                output_summary=f"{len(suggestions)} suggestions",
                model=settings.openai_model,
                latency_ms=int((time.monotonic() - t0) * 1000),
                token_usage={
                    "prompt": usage.prompt_tokens if usage else 0,
                    "completion": usage.completion_tokens if usage else 0,
                },
            )
            return DiscoverSourcesResponseData(topic=topic, suggestions=suggestions)
        except Exception as e:
            logger.error(f"AI discover sources failed for topic '{topic}': {e}")
            await self.audit.log(
                user_id=user_id,
                action="discover_sources",
                input_summary=topic[:200],
                model=settings.openai_model,
                latency_ms=int((time.monotonic() - t0) * 1000),
                error=str(e),
            )
            return DiscoverSourcesResponseData(topic=topic, suggestions=[])

    async def augmented_search(
        self,
        query: str,
        user_id: str,
        include_external: bool = True,
        persist_external: bool = False,
        persist_mode: str = "none",
        external_provider: str = "auto",
        max_external_results: int = 10,
        time_range: Optional[str] = None,
        language: Optional[str] = None,
        engines: Optional[List[str]] = None,
    ) -> AugmentedSearchResponseData:
        """Perform AI-augmented search combining internal ES + external web results.

        Uses RRF (Reciprocal Rank Fusion) to merge results from different score
        distributions. Optionally generates an AI summary of the top results.
        """
        t0 = time.monotonic()

        # 1. Run internal and external searches in parallel
        tasks: List[Any] = [self._internal_search(query, user_id)]
        if include_external:
            tasks.append(
                self._external_search(
                    query=query,
                    provider=external_provider,
                    max_results=external_limit,
                    time_range=time_range,
                    language=language,
                    engines=engines,
                )
            )

        results_raw = await asyncio.gather(*tasks, return_exceptions=True)

        internal_results: List[Dict[str, Any]] = (
            results_raw[0] if not isinstance(results_raw[0], Exception) else []
        )
        external_results: List[Dict[str, Any]] = []
        provider_used: Optional[str] = None
        fallback_used = False
        if include_external and len(results_raw) > 1:
            external_payload = (
                results_raw[1] if not isinstance(results_raw[1], Exception) else {}
            )
            external_results = external_payload.get("results", [])
            provider_used = external_payload.get("provider_used")
            fallback_used = bool(external_payload.get("fallback_used", False))

        # 2. RRF fusion
        fused = self._rrf_merge(internal_results, external_results)

        # 3. Build response items
        result_items = [
            SearchResultItem(
                title=item["title"],
                url=item["url"],
                description=item.get("description", ""),
                source_name=item.get("source_name", ""),
                score=item["rrf_score"],
                origin=item["origin"],
                news_id=item.get("news_id"),
                provider=item.get("provider"),
                engine=item.get("engine"),
            )
            for item in fused[:20]
        ]

        # 4. AI summary (best-effort)
        summary = ""
        if result_items and self.client is not None:
            summary = await self._generate_search_summary(query, result_items[:5])

        # 5. Persist external if requested
        session_id: Optional[str] = None
        if external_results:
            session_id = await self.external_ingestion.create_search_session(
                user_id=user_id,
                query=query,
                provider_used=provider_used or external_provider,
                results=external_results,
            )

        effective_mode = persist_mode
        if persist_external and persist_mode == "none":
            effective_mode = "snippet"

        if effective_mode in {"snippet", "enriched"} and session_id:
            try:
                await self.external_ingestion.queue_ingest_job(
                    user_id=user_id,
                    session_id=session_id,
                    selected_urls=[],
                    persist_mode=effective_mode,
                )
            except Exception as e:
                logger.warning(f"Failed to persist external results: {e}")

        # 6. Audit
        await self.audit.log(
            user_id=user_id,
            action="augmented_search",
            input_summary=query[:200],
            output_summary=f"{len(internal_results)}i+{len(external_results)}e → {len(result_items)} results",
            model=settings.openai_model if summary else "",
            latency_ms=int((time.monotonic() - t0) * 1000),
        )

        return AugmentedSearchResponseData(
            query=query,
            summary=summary,
            results=result_items,
            internal_count=len(internal_results),
            external_count=len(external_results),
            provider_used=provider_used,
            fallback_used=fallback_used,
            search_session_id=session_id,
        )

    async def external_search_options(self) -> Dict[str, Any]:
        """Expose provider capabilities/options for frontend controls."""
        return await self.external_search_router.options()

    async def external_search_status(self) -> Dict[str, Any]:
        """Expose provider health status for operations UI."""
        return await self.external_search_router.status()

    async def queue_search_ingestion(
        self,
        user_id: str,
        session_id: str,
        selected_urls: List[str],
        persist_mode: str,
    ) -> Dict[str, Any]:
        """Queue ingestion for a search session and selected URLs."""
        return await self.external_ingestion.queue_ingest_job(
            user_id=user_id,
            session_id=session_id,
            selected_urls=selected_urls,
            persist_mode=persist_mode,
        )

    async def get_ingest_job(self, user_id: str, job_id: str) -> Optional[Dict[str, Any]]:
        """Get ingest job status scoped to user."""
        return await self.external_ingestion.get_ingest_job(user_id=user_id, job_id=job_id)

    async def _internal_search(self, query: str, user_id: str) -> List[Dict[str, Any]]:
        """Run hybrid search against user's ES index."""
        try:
            from app.db.es import es_client
            from app.services.search.search_service import SearchService

            if not es_client.is_connected:
                return []

            svc = SearchService(es_client.client)
            response = await svc.search(
                user_id=user_id, query=query, search_type="hybrid", page_size=10
            )
            return [
                {
                    "title": r.title,
                    "url": r.url,
                    "description": r.description or "",
                    "source_name": r.source_name,
                    "news_id": r.id,
                    "score": r.score,
                    "origin": "internal",
                }
                for r in response.results
            ]
        except Exception as e:
            logger.error(f"Internal search failed: {e}")
            return []

    async def _external_search(
        self,
        query: str,
        provider: str = "auto",
        max_results: Optional[int] = None,
        time_range: Optional[str] = None,
        language: Optional[str] = None,
        engines: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """Run external search via provider router (SearXNG/Tavily)."""
        try:
            effective_max_results = max_results or settings.external_search_default_limit
            execution = await self.external_search_router.search(
                request=ExternalSearchQuery(
                    query=query,
                    max_results=effective_max_results,
                    time_range=time_range,
                    language=language,
                    engines=engines,
                ),
                provider=provider,
            )
            return {
                "provider_used": execution.provider_used,
                "fallback_used": execution.fallback_used,
                "results": [
                    {
                        "title": item.title,
                        "url": item.url,
                        "description": item.description,
                        "content": item.content,
                        "score": item.score,
                        "source_name": item.source_name or "Web",
                        "origin": "external",
                        "provider": item.provider or execution.provider_used,
                        "engine": item.engine,
                        "published_at": item.published_at,
                        "metadata": item.metadata,
                    }
                    for item in execution.results
                ],
            }
        except Exception as e:
            logger.error(f"External search failed: {e}")
            return {"provider_used": provider, "fallback_used": False, "results": []}

    def _rrf_merge(
        self,
        internal: List[Dict[str, Any]],
        external: List[Dict[str, Any]],
        k: int = 60,
    ) -> List[Dict[str, Any]]:
        """Merge results using Reciprocal Rank Fusion.

        RRF score = sum(1 / (k + rank)) across lists.
        Uses URL as dedup key.
        """
        url_scores: Dict[str, float] = {}
        url_items: Dict[str, Dict[str, Any]] = {}

        for rank, item in enumerate(internal):
            url = item["url"]
            url_scores[url] = url_scores.get(url, 0) + 1.0 / (k + rank + 1)
            url_items[url] = item

        for rank, item in enumerate(external):
            url = item["url"]
            url_scores[url] = url_scores.get(url, 0) + 1.0 / (k + rank + 1)
            if url not in url_items:
                url_items[url] = item

        sorted_urls = sorted(url_scores, key=lambda u: url_scores[u], reverse=True)
        result: List[Dict[str, Any]] = []
        for url in sorted_urls:
            entry = url_items[url].copy()
            entry["rrf_score"] = round(url_scores[url], 6)
            result.append(entry)
        return result

    async def _generate_search_summary(
        self, query: str, items: List[SearchResultItem]
    ) -> str:
        """Generate AI summary of top search results."""
        if self.client is None:
            return ""

        results_text = "\n".join(
            f"- [{item.title}]({item.url}): {item.description[:100]}"
            for item in items
            if item.title
        )
        if not results_text:
            return ""

        prompt = SEARCH_SUMMARY_TEMPLATE.format(query=query, results_text=results_text)
        try:
            response = await self.client.chat.completions.create(
                model=settings.openai_model,
                messages=[
                    {"role": "system", "content": SYSTEM_CHAT},
                    {"role": "user", "content": prompt},
                ],
                stream=False,
            )
            return (response.choices[0].message.content or "").strip()
        except Exception as e:
            logger.warning(f"Search summary generation failed: {e}")
            return ""

    async def _get_news_doc(self, news_id: str, user_id: str) -> dict:
        """Load a user-scoped news document from MongoDB."""
        try:
            oid = ObjectId(news_id)
        except Exception as e:
            raise ValueError("Invalid news ID format") from e

        doc = await mongodb.db.news.find_one({"_id": oid, "user_id": user_id})
        if not doc:
            raise ValueError("News item not found")
        return doc

    def _extractive_summary(self, content: str) -> str:
        """Fallback summary using the first two sentences."""
        if not content:
            return "暂无可总结内容。"

        sentences = [
            s.strip() for s in re.split(r"(?<=[。！？.!?])\s*", content) if s.strip()
        ]
        if not sentences:
            return content[:200]
        return "".join(sentences[:2])

    def _parse_json_array(self, raw: str) -> List[dict]:
        """Best-effort JSON array parsing from model output."""
        try:
            data = json.loads(raw)
            return data if isinstance(data, list) else []
        except Exception:
            start = raw.find("[")
            end = raw.rfind("]")
            if start >= 0 and end > start:
                try:
                    data = json.loads(raw[start : end + 1])
                    return data if isinstance(data, list) else []
                except Exception:
                    return []
            return []

    # === Conversation Thread Management ===

    async def list_conversations(
        self, user_id: str, page: int = 1, page_size: int = 20,
    ) -> Dict[str, Any]:
        """List user's conversation threads, sorted by most recent."""
        query = {"user_id": user_id, "is_archived": {"$ne": True}}
        total = await mongodb.conversation_threads.count_documents(query)
        skip = (page - 1) * page_size
        cursor = mongodb.conversation_threads.find(query).sort(
            "last_message_at", -1
        ).skip(skip).limit(page_size)
        threads = []
        async for doc in cursor:
            threads.append(ConversationThread(
                thread_id=doc["thread_id"],
                title=doc.get("title", ""),
                created_at=doc.get("created_at", datetime.utcnow()),
                last_message_at=doc.get("last_message_at", datetime.utcnow()),
                message_count=doc.get("message_count", 0),
                last_user_message=doc.get("last_user_message", ""),
            ))
        return {"threads": threads, "total": total}

    async def get_conversation(self, user_id: str, thread_id: str) -> Optional[Dict[str, Any]]:
        """Get a single conversation thread metadata."""
        doc = await mongodb.conversation_threads.find_one(
            {"thread_id": thread_id, "user_id": user_id}
        )
        if not doc:
            return None
        return {
            "thread_id": doc["thread_id"],
            "title": doc.get("title", ""),
            "created_at": doc.get("created_at"),
            "last_message_at": doc.get("last_message_at"),
            "message_count": doc.get("message_count", 0),
            "last_user_message": doc.get("last_user_message", ""),
            "is_archived": doc.get("is_archived", False),
        }

    async def update_conversation(self, user_id: str, thread_id: str, title: str) -> bool:
        """Update conversation title."""
        result = await mongodb.conversation_threads.update_one(
            {"thread_id": thread_id, "user_id": user_id},
            {"$set": {"title": title}},
        )
        return result.modified_count > 0

    async def delete_conversation(self, user_id: str, thread_id: str) -> bool:
        """Archive a conversation and clean up checkpoint data."""
        result = await mongodb.conversation_threads.update_one(
            {"thread_id": thread_id, "user_id": user_id},
            {"$set": {"is_archived": True}},
        )
        if result.modified_count == 0:
            return False
        # Clean up LangGraph checkpoint data
        try:
            await mongodb.db.langgraph_checkpoints.delete_many(
                {"thread_id": thread_id}
            )
            await mongodb.db.langgraph_writes.delete_many(
                {"thread_id": thread_id}
            )
        except Exception as e:
            logger.warning(f"Failed to clean up checkpoints for thread {thread_id}: {e}")
        return True

    # === Cached LLM Completion (for AsyncOpenAI client) ===

    async def _chat_plain_fallback(
        self,
        messages: List[dict],
        system_prompt: Optional[str] = None,
    ) -> str:
        """Generate a plain non-tool response when LangGraph path yields nothing."""
        if self.client is None:
            return ""
        try:
            payload: List[Dict[str, str]] = []
            prompt = (system_prompt or SYSTEM_CHAT).strip()
            if prompt:
                payload.append({"role": "system", "content": prompt})
            for msg in messages[-20:]:
                role = str(msg.get("role", "user"))
                if role not in {"user", "assistant", "system"}:
                    continue
                content = str(msg.get("content", "")).strip()
                if not content:
                    continue
                payload.append({"role": role, "content": content})

            if not payload:
                return ""

            response = await self.client.chat.completions.create(
                model=settings.openai_model,
                messages=payload,
                stream=False,
            )
            return (response.choices[0].message.content or "").strip()
        except Exception as e:
            logger.warning(f"Plain chat fallback failed: {e}")
            return ""

    async def _cached_completion(self, cache_key: str, messages: list, model: str) -> Optional[str]:
        """Check MongoDB cache before calling OpenAI. Returns None on cache miss + API failure."""
        if not settings.llm_cache_enabled:
            response = await self.client.chat.completions.create(
                model=model, messages=messages, stream=False,
            )
            return (response.choices[0].message.content or "").strip()

        key_hash = hashlib.sha256(cache_key.encode()).hexdigest()
        # Check cache
        try:
            doc = await mongodb.llm_cache.find_one({"prompt_hash": key_hash})
            if doc:
                await mongodb.llm_cache.update_one(
                    {"_id": doc["_id"]}, {"$inc": {"hit_count": 1}}
                )
                logger.debug(f"AsyncOpenAI cache HIT: {key_hash[:12]}...")
                return doc["response"]
        except Exception as e:
            logger.warning(f"Cache lookup failed: {e}")

        # Cache miss — call API
        response = await self.client.chat.completions.create(
            model=model, messages=messages, stream=False,
        )
        text = (response.choices[0].message.content or "").strip()

        # Store in cache
        if text:
            try:
                await mongodb.llm_cache.update_one(
                    {"prompt_hash": key_hash},
                    {"$set": {
                        "model": model,
                        "response": text,
                        "created_at": datetime.utcnow(),
                        "ttl_expires_at": datetime.utcnow() + timedelta(hours=settings.llm_cache_ttl_hours),
                    }, "$setOnInsert": {"hit_count": 0}},
                    upsert=True,
                )
            except Exception as e:
                logger.warning(f"Cache store failed: {e}")

        return text
