"""
Source Detection Service

Analyzes URLs to determine source type (RSS, API, HTML) and suggest parser configuration.
"""

import re
from typing import Any, Dict, List, Optional
from urllib.parse import urlparse

import httpx
from loguru import logger

from app.schemas.source import (
    ParserConfig,
    ParserConfigAPI,
    ParserConfigHTML,
    SourceDetectResponse,
    SourceType,
)


class SourceDetector:
    """Detects source type and suggests configuration from a URL."""

    def __init__(self):
        self.timeout = 15.0
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        }

    async def detect(self, url: str) -> SourceDetectResponse:
        """
        Analyze a URL and detect the source type.

        Returns detected type, suggested name, and parser config.
        """
        try:
            async with httpx.AsyncClient(
                timeout=self.timeout, follow_redirects=True
            ) as client:
                response = await client.get(url, headers=self.headers)
                response.raise_for_status()

                content_type = response.headers.get("content-type", "").lower()
                content = response.text

                # Try RSS/Atom detection first
                if self._is_rss_feed(content_type, content):
                    return await self._detect_rss(url, content)

                # Try JSON API detection
                if self._is_json_response(content_type, content):
                    return await self._detect_api(url, content)

                # Default to HTML scraping
                return await self._detect_html(url, content)

        except httpx.TimeoutException:
            logger.warning(f"Timeout detecting source: {url}")
            return SourceDetectResponse(
                detected_type=SourceType.HTML,
                confidence=0.1,
            )
        except Exception as e:
            logger.error(f"Error detecting source {url}: {e}")
            return SourceDetectResponse(
                detected_type=SourceType.HTML,
                confidence=0.0,
            )

    def _is_rss_feed(self, content_type: str, content: str) -> bool:
        """Check if response is an RSS/Atom feed."""
        # Check content type
        if any(t in content_type for t in ["xml", "rss", "atom"]):
            return True

        # Check content for RSS/Atom markers
        content_lower = content[:2000].lower()
        rss_markers = ["<rss", "<feed", "<channel>", "xmlns:atom", "application/rss"]
        return any(marker in content_lower for marker in rss_markers)

    def _is_json_response(self, content_type: str, content: str) -> bool:
        """Check if response is JSON."""
        if "json" in content_type:
            return True

        # Try to detect JSON structure
        content_stripped = content.strip()
        return content_stripped.startswith("{") or content_stripped.startswith("[")

    async def _detect_rss(self, url: str, content: str) -> SourceDetectResponse:
        """Detect RSS feed details."""
        import feedparser

        feed = feedparser.parse(content)

        # feedparser returns FeedParserDict which supports .get()
        feed_data = feed.feed
        suggested_name = getattr(feed_data, "title", None) or self._extract_domain(url)
        preview_items = []

        for entry in feed.entries[:3]:
            preview_items.append(
                {
                    "title": getattr(entry, "title", ""),
                    "link": getattr(entry, "link", ""),
                    "published": getattr(entry, "published", ""),
                }
            )

        return SourceDetectResponse(
            detected_type=SourceType.RSS,
            suggested_name=suggested_name,
            suggested_config=None,  # RSS doesn't need config
            preview_items=preview_items,
            confidence=0.95,
        )

    async def _detect_api(self, url: str, content: str) -> SourceDetectResponse:
        """Detect JSON API structure."""
        import json

        try:
            data = json.loads(content)
        except json.JSONDecodeError:
            return SourceDetectResponse(
                detected_type=SourceType.API,
                confidence=0.3,
            )

        # Find the list of items
        list_path, items = self._find_list_in_json(data)

        if not items:
            return SourceDetectResponse(
                detected_type=SourceType.API,
                confidence=0.4,
            )

        # Suggest field mappings
        field_mappings = self._suggest_field_mappings(items[0] if items else {})

        config = ParserConfig(
            mode=SourceType.API,
            api=ParserConfigAPI(
                list_path=list_path,
                fields=field_mappings,
            ),
        )

        preview_items = []
        for item in items[:3]:
            preview_items.append(
                {
                    k: self._extract_jmes_value(item, v)
                    for k, v in field_mappings.items()
                    if self._extract_jmes_value(item, v)
                }
            )

        return SourceDetectResponse(
            detected_type=SourceType.API,
            suggested_name=self._extract_domain(url),
            suggested_config=config,
            preview_items=preview_items,
            confidence=0.8,
        )

    async def _detect_html(self, url: str, content: str) -> SourceDetectResponse:
        """Detect HTML page structure for scraping."""
        from bs4 import BeautifulSoup

        soup = BeautifulSoup(content, "html.parser")

        # Extract page title
        title_tag = soup.find("title")
        suggested_name = (
            title_tag.text.strip() if title_tag else self._extract_domain(url)
        )

        # Try to find article list patterns
        list_selector, link_selector = self._find_article_list(soup)

        config = None
        preview_items = []

        if list_selector:
            config = ParserConfig(
                mode=SourceType.HTML,
                html=ParserConfigHTML(
                    list_selector=list_selector,
                    link_selector=link_selector or "a",
                ),
            )

            # Extract preview items
            items = soup.select(list_selector)[:3]
            for item in items:
                link = item.select_one(link_selector or "a")
                title_el = item.select_one("h1, h2, h3, h4, .title, [class*='title']")
                preview_items.append(
                    {
                        "title": title_el.text.strip() if title_el else "",
                        "link": link.get("href", "") if link else "",
                    }
                )

        return SourceDetectResponse(
            detected_type=SourceType.HTML,
            suggested_name=suggested_name[:100],
            suggested_config=config,
            preview_items=preview_items,
            confidence=0.6 if list_selector else 0.3,
        )

    def _extract_domain(self, url: str) -> str:
        """Extract domain name from URL."""
        parsed = urlparse(url)
        domain = parsed.netloc.replace("www.", "")
        return domain.split(".")[0].title()

    def _find_list_in_json(self, data: Any, path: str = "") -> tuple:
        """Recursively find a list of items in JSON structure."""
        if isinstance(data, list) and len(data) > 0:
            if isinstance(data[0], dict):
                return path or "@", data
            return None, None

        if isinstance(data, dict):
            # Common list field names
            priority_keys = [
                "items",
                "data",
                "results",
                "articles",
                "news",
                "posts",
                "entries",
                "list",
            ]

            for key in priority_keys:
                if key in data and isinstance(data[key], list):
                    new_path = f"{path}.{key}" if path else key
                    return new_path, data[key]

            # Check all keys
            for key, value in data.items():
                if (
                    isinstance(value, list)
                    and len(value) > 0
                    and isinstance(value[0], dict)
                ):
                    new_path = f"{path}.{key}" if path else key
                    return new_path, value

        return None, None

    def _suggest_field_mappings(self, sample_item: Dict[str, Any]) -> Dict[str, str]:
        """Suggest field mappings based on a sample item."""
        mappings = {}

        # Title field
        title_keys = ["title", "headline", "name", "subject"]
        for key in title_keys:
            if key in sample_item:
                mappings["title"] = key
                break

        # Link field
        link_keys = ["url", "link", "href", "uri", "permalink"]
        for key in link_keys:
            if key in sample_item:
                mappings["link"] = key
                break

        # Content field
        content_keys = ["content", "body", "text", "description", "summary", "excerpt"]
        for key in content_keys:
            if key in sample_item:
                mappings["content"] = key
                break

        # Published date field
        date_keys = [
            "published",
            "publishedAt",
            "created_at",
            "date",
            "time",
            "timestamp",
            "pubDate",
        ]
        for key in date_keys:
            if key in sample_item:
                mappings["published_at"] = key
                break

        # Author field
        author_keys = ["author", "creator", "writer", "by"]
        for key in author_keys:
            if key in sample_item:
                mappings["author"] = key
                break

        return mappings

    def _extract_jmes_value(self, item: Dict, path: str) -> Any:
        """Simple extraction for preview (not full JMESPath)."""
        if "." not in path:
            return item.get(path)
        return None

    def _find_article_list(self, soup) -> tuple:
        """Find article list selector in HTML."""
        # Common article container patterns
        patterns = [
            ("article", "a"),
            (".article", "a"),
            (".post", "a"),
            (".news-item", "a"),
            (".item", "a"),
            ("[class*='article']", "a"),
            ("[class*='post']", "a"),
            ("li.item", "a"),
            (".list-item", "a"),
        ]

        for list_sel, link_sel in patterns:
            items = soup.select(list_sel)
            if len(items) >= 3:  # At least 3 items to be considered a list
                return list_sel, link_sel

        return None, None
