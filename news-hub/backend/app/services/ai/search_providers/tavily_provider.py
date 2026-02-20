"""Tavily external search provider."""

from __future__ import annotations

import time
from typing import Any, Dict, List

import httpx
from loguru import logger

from app.core.config import settings
from app.services.ai.search_providers.base import (
    ExternalSearchProvider,
    ExternalSearchQuery,
    ExternalSearchResult,
)

TAVILY_SEARCH_URL = "https://api.tavily.com/search"


class TavilyProvider(ExternalSearchProvider):
    """Async provider adapter for Tavily Search API."""

    name = "tavily"

    def __init__(self):
        self.api_key = settings.tavily_api_key

    @property
    def available(self) -> bool:
        return bool(self.api_key)

    async def search(self, request: ExternalSearchQuery) -> List[ExternalSearchResult]:
        if not self.available:
            logger.debug("Tavily is not configured; returning empty result set")
            return []

        payload = {
            "api_key": self.api_key,
            "query": request.query,
            "max_results": request.max_results,
            "search_depth": "advanced" if request.time_range else "basic",
            "include_answer": False,
            "include_raw_content": True,
        }

        try:
            async with httpx.AsyncClient(timeout=settings.external_search_timeout) as client:
                resp = await client.post(TAVILY_SEARCH_URL, json=payload)
                resp.raise_for_status()
                data: Dict[str, Any] = resp.json()
        except httpx.HTTPStatusError as e:
            logger.error(f"Tavily API HTTP error: {e.response.status_code}")
            return []
        except Exception as e:
            logger.error(f"Tavily search failed: {e}")
            return []

        results: List[ExternalSearchResult] = []
        for item in data.get("results", []):
            url = str(item.get("url", "")).strip()
            title = str(item.get("title", "")).strip()
            if not url or not title:
                continue
            content = str(item.get("content", "") or "")
            results.append(
                ExternalSearchResult(
                    title=title,
                    url=url,
                    description=content[:300],
                    content=content,
                    score=float(item.get("score", 0.0) or 0.0),
                    source_name="Web",
                    provider=self.name,
                    metadata={"raw": item},
                )
            )

        return results

    async def options(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "available": self.available,
            "supports": {
                "engines": False,
                "time_range": False,
                "language": False,
            },
        }

    async def healthcheck(self) -> Dict[str, Any]:
        if not self.available:
            return {
                "provider": self.name,
                "available": False,
                "healthy": False,
                "latency_ms": 0,
                "message": "TAVILY_API_KEY is not configured",
            }

        started = time.monotonic()
        payload = {
            "api_key": self.api_key,
            "query": "latest news",
            "max_results": 1,
            "search_depth": "basic",
            "include_answer": False,
        }
        try:
            async with httpx.AsyncClient(timeout=settings.external_search_timeout) as client:
                resp = await client.post(TAVILY_SEARCH_URL, json=payload)
                resp.raise_for_status()
            latency_ms = int((time.monotonic() - started) * 1000)
            return {
                "provider": self.name,
                "available": True,
                "healthy": True,
                "latency_ms": latency_ms,
                "message": "ok",
            }
        except Exception as e:
            latency_ms = int((time.monotonic() - started) * 1000)
            return {
                "provider": self.name,
                "available": True,
                "healthy": False,
                "latency_ms": latency_ms,
                "message": str(e),
            }
