"""AI assistant orchestration service."""

import json
import re
from typing import AsyncGenerator, List

from bson import ObjectId
from loguru import logger

from app.core.config import settings
from app.db.mongo import mongodb
from app.schemas.assistant import (
    ClassifyResponseData,
    DiscoverSourcesResponseData,
    SourceSuggestion,
    SummarizeResponseData,
)
from app.services.ai.llm_client import get_llm_client
from app.services.ai.prompts import (
    CLASSIFY_TEMPLATE,
    DISCOVER_SOURCES_TEMPLATE,
    SUMMARIZE_TEMPLATE,
    SYSTEM_CHAT,
)


class AssistantService:
    """Service layer for AI assistant features."""

    def __init__(self):
        self.client = get_llm_client()

    async def chat(
        self, messages: List[dict], user_id: str
    ) -> AsyncGenerator[str, None]:
        """Stream assistant chat response chunks."""
        if self.client is None:
            yield "AI 助手暂不可用，请先配置 OPENAI_API_KEY。"
            return

        payload_messages = [{"role": "system", "content": SYSTEM_CHAT}, *messages]

        try:
            stream = await self.client.chat.completions.create(
                model=settings.openai_model,
                messages=payload_messages,
                stream=True,
            )
            async for chunk in stream:
                for choice in chunk.choices:
                    delta = choice.delta.content
                    if delta:
                        yield delta
        except Exception as e:
            logger.error(f"AI chat streaming failed for user {user_id}: {e}")
            raise

    async def summarize(self, news_id: str, user_id: str) -> SummarizeResponseData:
        """Summarize a news item with AI, fallback to extractive summary."""
        news_doc = await self._get_news_doc(news_id, user_id)

        title = news_doc.get("title", "")
        source = news_doc.get("source_name", "")
        content = news_doc.get("content") or news_doc.get("description") or ""

        if self.client is None:
            return SummarizeResponseData(
                news_id=news_id,
                summary=self._extractive_summary(content),
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
            return SummarizeResponseData(news_id=news_id, summary=summary, method="ai")
        except Exception as e:
            logger.error(f"AI summarize failed for news {news_id}: {e}")
            return SummarizeResponseData(
                news_id=news_id,
                summary=self._extractive_summary(content),
                method="extractive",
            )

    async def classify(
        self, news_id: str, user_id: str, available_tags: List[str]
    ) -> ClassifyResponseData:
        """Classify a news item into user tag candidates."""
        news_doc = await self._get_news_doc(news_id, user_id)

        if self.client is None:
            return ClassifyResponseData(
                news_id=news_id,
                suggested_tags=[],
                method="rule_based",
            )

        prompt = CLASSIFY_TEMPLATE.format(
            title=news_doc.get("title", ""),
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
            return ClassifyResponseData(
                news_id=news_id, suggested_tags=tags, method="ai"
            )
        except Exception as e:
            logger.error(f"AI classify failed for news {news_id}: {e}")
            return ClassifyResponseData(
                news_id=news_id,
                suggested_tags=[],
                method="rule_based",
            )

    async def discover_sources(self, topic: str) -> DiscoverSourcesResponseData:
        """Discover source suggestions for a topic."""
        if self.client is None:
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
            return DiscoverSourcesResponseData(topic=topic, suggestions=suggestions)
        except Exception as e:
            logger.error(f"AI discover sources failed for topic '{topic}': {e}")
            return DiscoverSourcesResponseData(topic=topic, suggestions=[])

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
