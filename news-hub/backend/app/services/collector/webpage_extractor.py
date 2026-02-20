"""Webpage extractor using crawl4ai for JS-rendered full-text extraction."""

from __future__ import annotations

import hashlib
from datetime import datetime
from typing import Any, Dict, Optional
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

from bs4 import BeautifulSoup
from dateutil import parser as date_parser
from loguru import logger

# Module-level crawler instance (lazy-init to avoid startup cost)
_crawler_instance = None
_crawler_lock = None


async def _get_crawler():
    """Get or create the module-level AsyncWebCrawler instance."""
    global _crawler_instance, _crawler_lock
    import asyncio

    if _crawler_lock is None:
        _crawler_lock = asyncio.Lock()

    async with _crawler_lock:
        if _crawler_instance is None:
            from crawl4ai import AsyncWebCrawler, BrowserConfig

            browser_cfg = BrowserConfig(
                headless=True,
                text_mode=True,
            )
            _crawler_instance = AsyncWebCrawler(config=browser_cfg)
            await _crawler_instance.start()
            logger.info("crawl4ai AsyncWebCrawler initialized")
        return _crawler_instance


class WebpageExtractor:
    """Full-text extraction powered by crawl4ai (Playwright-based)."""

    DATE_META_KEYS = [
        "article:published_time",
        "og:published_time",
        "publishdate",
        "pubdate",
        "date",
    ]

    async def extract(self, url: str) -> Dict[str, Any]:
        """Extract structured content from a webpage URL using crawl4ai."""
        try:
            return await self._crawl_and_extract(url)
        except Exception as e:
            logger.warning(f"crawl4ai extraction failed for {url}: {e}")
            return {}

    async def _crawl_and_extract(self, url: str) -> Dict[str, Any]:
        from crawl4ai import CrawlerRunConfig

        crawler = await _get_crawler()
        run_cfg = CrawlerRunConfig(
            excluded_tags=["nav", "footer", "aside"],
            word_count_threshold=10,
        )
        result = await crawler.arun(url=url, config=run_cfg)

        if not result.success:
            logger.warning(f"crawl4ai returned failure for {url}: {result.error_message}")
            return {}

        # Extract markdown content (prefer fit_markdown for cleaner output)
        content = ""
        if result.markdown:
            content = getattr(result.markdown, "fit_markdown", None) or ""
            if not content:
                content = str(result.markdown) if result.markdown else ""

        # Parse HTML for OG metadata
        html = result.html or result.cleaned_html or ""
        soup = BeautifulSoup(html, "html.parser") if html else None

        title = self._extract_title(soup) if soup else ""
        description = self._extract_description(soup, content) if soup else content[:500]
        published_at = self._extract_published_at(soup) if soup else None
        author = self._extract_author(soup) if soup else None
        image_url = self._extract_image(soup) if soup else None
        canonical_url = self._extract_canonical_url(soup, url) if soup else self.normalize_url(url)
        quality_score = self._quality_score(content, title, description)

        return {
            "title": title,
            "description": description,
            "content": content,
            "author": author,
            "image_url": image_url,
            "published_at": published_at,
            "canonical_url": canonical_url,
            "url_hash": self.url_hash(canonical_url),
            "quality_score": quality_score,
        }

    def _extract_title(self, soup: BeautifulSoup) -> str:
        if soup.title and soup.title.string:
            return soup.title.string.strip()
        meta = soup.find("meta", attrs={"property": "og:title"})
        if meta and meta.get("content"):
            return str(meta["content"]).strip()
        return ""

    def _extract_description(self, soup: BeautifulSoup, article_text: str) -> str:
        for attrs in [
            {"name": "description"},
            {"property": "og:description"},
            {"name": "twitter:description"},
        ]:
            meta = soup.find("meta", attrs=attrs)
            if meta and meta.get("content"):
                return str(meta["content"]).strip()[:500]
        return article_text[:500] if article_text else ""

    def _extract_published_at(self, soup: BeautifulSoup) -> Optional[datetime]:
        for key in self.DATE_META_KEYS:
            meta = soup.find("meta", attrs={"property": key}) or soup.find(
                "meta", attrs={"name": key}
            )
            if not meta or not meta.get("content"):
                continue
            try:
                return date_parser.parse(str(meta["content"]))
            except Exception:
                continue
        return None

    def _extract_author(self, soup: BeautifulSoup) -> Optional[str]:
        for attrs in [
            {"name": "author"},
            {"property": "article:author"},
            {"name": "parsely-author"},
        ]:
            meta = soup.find("meta", attrs=attrs)
            if meta and meta.get("content"):
                return str(meta["content"]).strip()[:100]
        return None

    def _extract_image(self, soup: BeautifulSoup) -> Optional[str]:
        for attrs in [
            {"property": "og:image"},
            {"name": "twitter:image"},
        ]:
            meta = soup.find("meta", attrs=attrs)
            if meta and meta.get("content"):
                return str(meta["content"]).strip()
        return None

    def _extract_canonical_url(self, soup: BeautifulSoup, fallback_url: str) -> str:
        link = soup.find("link", attrs={"rel": "canonical"})
        if link and link.get("href"):
            return self.normalize_url(str(link["href"]))
        return self.normalize_url(fallback_url)

    def _quality_score(self, content: str, title: str, description: str) -> float:
        score = 0.0
        if title:
            score += 0.2
        if description:
            score += 0.2
        if len(content) >= 600:
            score += 0.4
        elif len(content) >= 200:
            score += 0.25
        elif len(content) >= 80:
            score += 0.1
        score += 0.2 if "\n" in content else 0.05
        return round(min(score, 1.0), 3)

    @classmethod
    def normalize_url(cls, url: str) -> str:
        """Normalize URL for deduplication and hash computation."""
        parsed = urlparse(url)
        scheme = parsed.scheme.lower() or "https"
        netloc = parsed.netloc.lower()
        path = parsed.path or "/"
        query = urlencode(
            sorted(
                (k, v)
                for k, v in parse_qsl(parsed.query, keep_blank_values=True)
                if not k.lower().startswith("utm_")
            )
        )
        normalized = urlunparse((scheme, netloc, path, "", query, ""))
        return normalized.rstrip("/") if path != "/" else normalized

    @classmethod
    def url_hash(cls, url: str) -> str:
        return hashlib.sha1(url.encode("utf-8")).hexdigest()
