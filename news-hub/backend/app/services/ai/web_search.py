"""
Async web search client using Tavily API via httpx.

Gracefully degrades when TAVILY_API_KEY is not configured.
"""

from typing import Any, Dict, List, Optional

import httpx
from loguru import logger

from app.core.config import settings

TAVILY_SEARCH_URL = "https://api.tavily.com/search"


class WebSearchClient:
    """Thin async wrapper around the Tavily Search API."""

    def __init__(self):
        self.api_key = settings.tavily_api_key

    @property
    def available(self) -> bool:
        """Check if external search is configured."""
        return bool(self.api_key)

    async def search(
        self,
        query: str,
        max_results: int = 5,
        search_depth: str = "basic",
        include_answer: bool = False,
    ) -> List[Dict[str, Any]]:
        """Execute a web search and return normalised result dicts.

        Returns:
            List of dicts with keys: title, url, description, content, score.
            Empty list on error or if unconfigured.
        """
        if not self.available:
            logger.debug("Tavily API key not configured, skipping external search")
            return []

        payload = {
            "api_key": self.api_key,
            "query": query,
            "max_results": max_results,
            "search_depth": search_depth,
            "include_answer": include_answer,
        }

        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                resp = await client.post(TAVILY_SEARCH_URL, json=payload)
                resp.raise_for_status()
                data = resp.json()

            results: List[Dict[str, Any]] = []
            for item in data.get("results", []):
                results.append(
                    {
                        "title": item.get("title", ""),
                        "url": item.get("url", ""),
                        "description": item.get("content", "")[:300],
                        "content": item.get("content", ""),
                        "score": item.get("score", 0.0),
                    }
                )
            return results
        except httpx.HTTPStatusError as e:
            logger.error(f"Tavily API HTTP error: {e.response.status_code}")
            return []
        except Exception as e:
            logger.error(f"Tavily search failed: {e}")
            return []
