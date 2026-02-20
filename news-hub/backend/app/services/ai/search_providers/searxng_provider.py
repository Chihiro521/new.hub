"""SearXNG external search provider."""

from __future__ import annotations

import time
from datetime import datetime
from typing import Any, Dict, List, Optional
from urllib.parse import urlparse

import httpx
from dateutil import parser as date_parser
from loguru import logger

from app.core.config import settings
from app.services.ai.search_providers.base import (
    ExternalSearchProvider,
    ExternalSearchQuery,
    ExternalSearchResult,
)


class SearXNGProvider(ExternalSearchProvider):
    """Async provider adapter for SearXNG Search API."""

    name = "searxng"

    def __init__(self):
        self.base_url = settings.searxng_base_url.rstrip("/")
        self.api_key = settings.searxng_api_key
        self._capabilities_cache: Optional[Dict[str, Any]] = None

    @property
    def available(self) -> bool:
        return bool(self.base_url)

    def _build_headers(self) -> Dict[str, str]:
        headers = {
            "User-Agent": settings.collector_user_agent,
            "Accept": "application/json",
        }
        if self.api_key:
            headers["X-API-Key"] = self.api_key
        return headers

    async def search(self, request: ExternalSearchQuery) -> List[ExternalSearchResult]:
        if not self.available:
            logger.debug("SearXNG is not configured; returning empty result set")
            return []

        params: Dict[str, Any] = {
            "q": request.query,
            "format": "json",
            "safesearch": request.safe_search,
            "pageno": 1,
        }
        if request.max_results:
            params["limit"] = request.max_results
        if request.language:
            params["language"] = request.language
        if request.time_range:
            params["time_range"] = request.time_range
        if request.engines:
            params["engines"] = ",".join(request.engines)

        search_url = f"{self.base_url}/search"

        try:
            async with httpx.AsyncClient(timeout=settings.external_search_timeout) as client:
                resp = await client.get(
                    search_url,
                    params=params,
                    headers=self._build_headers(),
                )
                resp.raise_for_status()
                data = resp.json()
        except httpx.HTTPStatusError as e:
            logger.error(f"SearXNG API HTTP error: {e.response.status_code}")
            return []
        except Exception as e:
            logger.error(f"SearXNG search failed: {e}")
            return []

        results: List[ExternalSearchResult] = []
        for item in data.get("results", []):
            title = str(item.get("title", "")).strip()
            url = str(item.get("url", "")).strip()
            if not title or not url:
                continue

            content = str(item.get("content", "") or "")
            engines = item.get("engines") or []
            published_at = self._parse_datetime(
                item.get("publishedDate")
                or item.get("published_date")
                or item.get("published")
            )
            source_name = self._extract_source_name(item, url)

            results.append(
                ExternalSearchResult(
                    title=title,
                    url=url,
                    description=content[:300],
                    content=content,
                    score=float(item.get("score", 0.0) or 0.0),
                    source_name=source_name,
                    published_at=published_at,
                    provider=self.name,
                    engine=engines[0] if engines else None,
                    metadata={
                        "engines": engines,
                        "category": item.get("category"),
                        "parsed_url": item.get("parsed_url"),
                    },
                )
            )

        return results

    async def options(self) -> Dict[str, Any]:
        capabilities = await self._fetch_capabilities()
        return {
            "name": self.name,
            "available": self.available,
            "supports": {
                "engines": True,
                "time_range": True,
                "language": True,
            },
            "engines": capabilities.get("engines", []),
            "languages": capabilities.get("languages", []),
            "time_ranges": ["day", "week", "month", "year"],
        }

    async def healthcheck(self) -> Dict[str, Any]:
        if not self.available:
            return {
                "provider": self.name,
                "available": False,
                "healthy": False,
                "latency_ms": 0,
                "message": "SEARXNG_BASE_URL is not configured",
            }

        started = time.monotonic()
        try:
            config_url = f"{self.base_url}/config"
            async with httpx.AsyncClient(timeout=settings.external_search_timeout) as client:
                resp = await client.get(config_url, headers=self._build_headers())
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

    async def _fetch_capabilities(self) -> Dict[str, Any]:
        if self._capabilities_cache is not None:
            return self._capabilities_cache

        if not self.available:
            self._capabilities_cache = {"engines": [], "languages": []}
            return self._capabilities_cache

        config_url = f"{self.base_url}/config"
        try:
            async with httpx.AsyncClient(timeout=settings.external_search_timeout) as client:
                resp = await client.get(config_url, headers=self._build_headers())
                resp.raise_for_status()
                payload = resp.json()
        except Exception as e:
            logger.warning(f"SearXNG capabilities fetch failed: {e}")
            self._capabilities_cache = {"engines": [], "languages": []}
            return self._capabilities_cache

        engines = []
        for engine in payload.get("engines", []):
            name = str(engine.get("name", "")).strip()
            if name:
                engines.append(name)

        languages = []
        for code, _ in (payload.get("locales") or {}).items():
            if code:
                languages.append(str(code))

        self._capabilities_cache = {
            "engines": sorted(set(engines)),
            "languages": sorted(set(languages)),
        }
        return self._capabilities_cache

    def _extract_source_name(self, item: Dict[str, Any], url: str) -> str:
        if item.get("source"):
            return str(item["source"])
        parsed = urlparse(url)
        return parsed.netloc or "Web"

    def _parse_datetime(self, value: Any) -> Optional[datetime]:
        if not value:
            return None
        if isinstance(value, datetime):
            return value
        try:
            return date_parser.parse(str(value))
        except Exception:
            return None
