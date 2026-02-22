"""AI assistant orchestration service."""

import asyncio
import json
import re
import time
from typing import Any, AsyncGenerator, Dict, List, Optional

from bson import ObjectId
from loguru import logger

from app.core.config import settings
from app.db.mongo import mongodb
from app.schemas.assistant import (
    AugmentedSearchResponseData,
    ClassifyResponseData,
    DiscoverSourcesResponseData,
    SearchResultItem,
    SourceSuggestion,
    SummarizeResponseData,
)
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

    async def chat(
        self, messages: List[dict], user_id: str
    ) -> AsyncGenerator[str, None]:
        """Stream assistant chat response chunks via LangGraph agent.

        Now uses the same LangGraph ResearchAgent as /chat-rag and /research,
        giving the basic chat endpoint full tool-calling capabilities.
        """
        from app.services.ai.agents.research_agent import ResearchAgent

        agent = ResearchAgent()
        async for chunk in agent.chat(messages=messages, user_id=user_id):
            yield chunk

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
            response = await self.client.chat.completions.create(
                model=settings.openai_model,
                messages=[
                    {"role": "system", "content": SYSTEM_CHAT},
                    {"role": "user", "content": prompt},
                ],
                stream=False,
            )
            summary = (response.choices[0].message.content or "").strip()
            if not summary:
                raise ValueError("Empty AI summary")

            usage = response.usage
            await self.audit.log(
                user_id=user_id,
                action="summarize",
                input_summary=title[:200],
                output_summary=summary[:200],
                model=settings.openai_model,
                latency_ms=int((time.monotonic() - t0) * 1000),
                token_usage={
                    "prompt": usage.prompt_tokens if usage else 0,
                    "completion": usage.completion_tokens if usage else 0,
                },
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
            response = await self.client.chat.completions.create(
                model=settings.openai_model,
                messages=[
                    {"role": "system", "content": SYSTEM_CHAT},
                    {"role": "user", "content": prompt},
                ],
                stream=False,
            )
            raw = (response.choices[0].message.content or "[]").strip()
            parsed = json.loads(raw)
            tags = [str(tag) for tag in parsed if isinstance(tag, str)]

            usage = response.usage
            await self.audit.log(
                user_id=user_id,
                action="classify",
                input_summary=title[:200],
                output_summary=json.dumps(tags, ensure_ascii=False)[:200],
                model=settings.openai_model,
                latency_ms=int((time.monotonic() - t0) * 1000),
                token_usage={
                    "prompt": usage.prompt_tokens if usage else 0,
                    "completion": usage.completion_tokens if usage else 0,
                },
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
