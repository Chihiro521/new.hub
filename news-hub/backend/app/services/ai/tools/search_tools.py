"""Search-related LangChain tools.

Tools: search_user_news, get_recent_news, web_search
"""

import json
from datetime import datetime, timedelta
from typing import Optional

from langchain_core.tools import tool
from loguru import logger

from app.core.config import settings
from app.db.es import es_client
from app.db.mongo import mongodb


def create_search_tools(user_id: str):
    """Create search tools bound to a specific user."""

    @tool
    async def search_user_news(query: str, limit: int = 5) -> str:
        """搜索用户的新闻库。当用户询问关于他们的新闻、文章、订阅内容时使用此工具。"""
        if not es_client.client:
            return json.dumps({"error": "Elasticsearch not available", "results": []}, ensure_ascii=False)
        try:
            from app.services.search.search_service import SearchService

            svc = SearchService(es_client.client)
            response = await svc.search(
                user_id=user_id, query=query, search_type="hybrid", page_size=limit,
            )
            results = [
                {
                    "title": r.title,
                    "url": r.url,
                    "description": r.description or "",
                    "source": r.source_name,
                    "published_at": r.published_at.isoformat() if r.published_at else None,
                    "score": round(r.score, 3),
                }
                for r in response.results
            ]
            return json.dumps({"query": query, "total": response.total, "results": results}, ensure_ascii=False)
        except Exception as e:
            logger.error(f"search_user_news failed: {e}")
            return json.dumps({"error": str(e), "results": []}, ensure_ascii=False)

    @tool
    async def get_recent_news(hours: int = 24, limit: int = 10) -> str:
        """获取用户最近的新闻。当用户询问'最近有什么新闻'、'今天的新闻'等时使用。"""
        try:
            start_date = datetime.utcnow() - timedelta(hours=hours)
            cursor = (
                mongodb.db.news.find({"user_id": user_id, "crawled_at": {"$gte": start_date}})
                .sort("crawled_at", -1)
                .limit(limit)
            )
            docs = await cursor.to_list(length=limit)
            results = [
                {
                    "title": doc.get("title", ""),
                    "url": doc.get("url", ""),
                    "description": doc.get("description", ""),
                    "source": doc.get("source_name", ""),
                    "crawled_at": doc.get("crawled_at").isoformat() if doc.get("crawled_at") else None,
                }
                for doc in docs
            ]
            return json.dumps({"hours": hours, "count": len(results), "results": results}, ensure_ascii=False)
        except Exception as e:
            logger.error(f"get_recent_news failed: {e}")
            return json.dumps({"error": str(e), "results": []}, ensure_ascii=False)

    @tool
    async def web_search(query: str, max_results: int = 5) -> str:
        """搜索互联网获取最新信息。当用户询问的内容不在新闻库中，或需要最新信息时使用。"""
        try:
            from app.services.ai.search_providers import ExternalSearchQuery, ExternalSearchRouter

            router = ExternalSearchRouter()
            if not any(p.available for p in router.providers.values()):
                return json.dumps({"error": "External search not configured", "results": []}, ensure_ascii=False)

            execution = await router.search(
                request=ExternalSearchQuery(query=query, max_results=max_results),
                provider=settings.external_search_default_provider,
            )
            results = [
                {"title": r.title, "url": r.url, "description": r.description, "score": r.score, "engine": r.engine}
                for r in execution.results
            ]
            return json.dumps(
                {"query": query, "provider": execution.provider_used, "count": len(results), "results": results},
                ensure_ascii=False,
            )
        except Exception as e:
            logger.error(f"web_search failed: {e}")
            return json.dumps({"error": str(e), "results": []}, ensure_ascii=False)

    return [search_user_news, get_recent_news, web_search]
