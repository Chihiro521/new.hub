"""Webpage extractor using Crawl4AI Docker REST API.

Features:
- Calls Crawl4AI Docker service via HTTP for JS-rendered extraction
- fit_markdown for LLM-ready clean output
- Batch extraction via multi-URL POST
- Overlay/popup removal, social link stripping
- Falls back to httpx + BeautifulSoup when Crawl4AI is unavailable
"""

from __future__ import annotations

import hashlib
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

import httpx
from bs4 import BeautifulSoup
from dateutil import parser as date_parser
from loguru import logger

from app.core.config import settings

# Crawl4AI Docker API: browser_config with stealth for anti-bot bypass
_BROWSER_CONFIG = {
    "type": "BrowserConfig",
    "params": {
        "headless": True,
        "light_mode": True,
        "enable_stealth": True,
        "user_agent_mode": "random",
        "extra_args": ["--disable-blink-features=AutomationControlled"],
    },
}

# Crawl4AI Docker API: crawler_config with PruningContentFilter for fit_markdown
_CRAWLER_CONFIG = {
    "type": "CrawlerRunConfig",
    "params": {
        "word_count_threshold": 10,
        "excluded_tags": ["nav", "footer", "aside", "header", "form", "noscript"],
        "exclude_social_media_links": True,
        "remove_overlay_elements": True,
        "page_timeout": 30000,
        "cache_mode": "bypass",
        "markdown_generator": {
            "type": "DefaultMarkdownGenerator",
            "params": {
                "content_filter": {
                    "type": "PruningContentFilter",
                    "params": {
                        "threshold": 0.1,
                        "threshold_type": "fixed",
                        "min_word_threshold": 1,
                    },
                },
            },
        },
    },
}


class WebpageExtractor:
    """Full-text extraction powered by Crawl4AI Docker REST API."""

    DATE_META_KEYS = [
        "article:published_time",
        "og:published_time",
        "publishdate",
        "pubdate",
        "date",
    ]

    async def extract(self, url: str) -> Dict[str, Any]:
        """Extract structured content from a webpage URL.

        Tries Crawl4AI Docker API first, falls back to httpx + BeautifulSoup.
        """
        try:
            result = await self._crawl_via_api(url)
            if result and result.get("content"):
                return result
        except Exception as e:
            logger.warning(f"Crawl4AI API extraction failed for {url}: {e}")

        # Fallback: simple HTTP fetch + BeautifulSoup
        try:
            return await self._fallback_extract(url)
        except Exception as e:
            logger.warning(f"Fallback extraction also failed for {url}: {e}")
            return {}

    async def _crawl_via_api(self, url: str) -> Dict[str, Any]:
        """Call Crawl4AI Docker REST API to crawl a single URL."""
        base_url = settings.crawl4ai_base_url.rstrip("/")
        headers = {"Content-Type": "application/json"}
        if settings.crawl4ai_api_token:
            headers["Authorization"] = f"Bearer {settings.crawl4ai_api_token}"

        payload = {
            "urls": [url],
            "browser_config": _BROWSER_CONFIG,
            "crawler_config": _CRAWLER_CONFIG,
        }

        logger.debug(f"[crawl4ai-api] POST {base_url}/crawl for {url}")
        async with httpx.AsyncClient(timeout=settings.crawl4ai_timeout) as client:
            resp = await client.post(f"{base_url}/crawl", json=payload, headers=headers)
            resp.raise_for_status()

        data = resp.json()
        if not data.get("success") or not data.get("results"):
            logger.warning(f"Crawl4AI API returned no results for {url}")
            return {}

        item = data["results"][0]
        if not item.get("success"):
            logger.warning(f"Crawl4AI crawl failed for {url}: {item.get('error_message')}")
            return {}

        # Detect server-side blocks: status 403/429/5xx AND no real content
        status_code = item.get("status_code", 200)
        content = self._pick_markdown(item)
        if status_code in (403, 429, 451, 503) and len(content) < 100:
            logger.warning(
                f"Crawl4AI got HTTP {status_code} with no useful content for {url}"
            )
            return {}

        # Extract markdown content
        logger.debug(f"[crawl4ai-api] extracted {len(content)} chars for {url}")

        # Prefer metadata from API response, fallback to HTML parsing
        meta = item.get("metadata") or {}
        html = item.get("html") or item.get("cleaned_html") or ""
        soup = BeautifulSoup(html, "html.parser") if html else None

        title = (
            meta.get("og:title") or meta.get("title") or ""
        ).strip() or (self._extract_title(soup) if soup else "")
        description = (
            meta.get("og:description") or meta.get("description") or ""
        ).strip()[:500] or (self._extract_description(soup, content) if soup else content[:500])
        published_at = self._parse_date(meta.get("article:published_time")) or (
            self._extract_published_at(soup) if soup else None
        )
        author = (
            meta.get("article:author") or meta.get("author") or ""
        ).strip()[:100] or (self._extract_author(soup) if soup else None)
        image_url = (
            meta.get("og:image") or ""
        ).strip() or (self._extract_image(soup) if soup else None)
        canonical_url = (
            meta.get("og:url") or ""
        ).strip() or (self._extract_canonical_url(soup, url) if soup else self.normalize_url(url))
        canonical_url = self.normalize_url(canonical_url)
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

    @staticmethod
    def _pick_markdown(item: dict) -> str:
        """Pick best markdown from Crawl4AI API response item.

        The API returns markdown as either:
        - a dict with keys: raw_markdown, fit_markdown, markdown_with_citations
        - or a plain string
        """
        md = item.get("markdown", "")
        if isinstance(md, dict):
            fit = (md.get("fit_markdown") or "").strip()
            if fit and len(fit) > 50:
                return fit
            raw = (md.get("raw_markdown") or "").strip()
            return raw if raw else ""
        # Plain string fallback
        fit = (item.get("fit_markdown") or "").strip()
        if fit and len(fit) > 50:
            return fit
        return (str(md) if md else "").strip()

    _FALLBACK_UAS = [
        # Mobile UA — many sites (Zhihu, Weibo) are less strict on mobile
        "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) "
        "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1",
        # Desktop UA
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    ]

    async def _fallback_extract(self, url: str) -> Dict[str, Any]:
        """Lightweight fallback: httpx GET + BeautifulSoup text extraction.

        Tries mobile UA first (less anti-bot), then desktop UA.
        """
        last_err: Optional[Exception] = None
        for ua in self._FALLBACK_UAS:
            try:
                logger.debug(f"[fallback] httpx 抓取: {url} (UA={ua[:30]}...)")
                async with httpx.AsyncClient(
                    follow_redirects=True, timeout=15.0,
                    headers={"User-Agent": ua},
                ) as client:
                    resp = await client.get(url)
                    resp.raise_for_status()
                html = resp.text
                break
            except httpx.HTTPStatusError as e:
                last_err = e
                logger.debug(f"[fallback] HTTP {e.response.status_code} with UA={ua[:30]}...")
                continue
        else:
            raise last_err or RuntimeError(f"All fallback UAs failed for {url}")
        soup = BeautifulSoup(html, "html.parser")

        for tag in soup.find_all(["nav", "footer", "aside", "header", "script", "style", "noscript"]):
            tag.decompose()

        article = (
            soup.find("article")
            or soup.find("div", class_=lambda c: c and any(k in (c if isinstance(c, str) else " ".join(c)) for k in ["article", "content", "post-body", "entry"]))
            or soup.find("main")
        )
        text_source = article if article else soup.body or soup

        paragraphs = []
        for p in text_source.find_all(["p", "h1", "h2", "h3", "h4", "li"]):
            text = p.get_text(strip=True)
            if len(text) > 15:
                if p.name and p.name.startswith("h"):
                    paragraphs.append(f"## {text}")
                else:
                    paragraphs.append(text)
        content = "\n\n".join(paragraphs)

        title = self._extract_title(soup)
        description = self._extract_description(soup, content)
        published_at = self._extract_published_at(soup)
        author = self._extract_author(soup)
        image_url = self._extract_image(soup)
        canonical_url = self._extract_canonical_url(soup, url)
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

    async def batch_extract(self, urls: List[str]) -> List[Tuple[str, Dict[str, Any]]]:
        """Batch-extract multiple URLs via Crawl4AI Docker API.

        Returns list of (url, extracted_dict) tuples.
        """
        if not urls:
            return []

        base_url = settings.crawl4ai_base_url.rstrip("/")
        headers = {"Content-Type": "application/json"}
        if settings.crawl4ai_api_token:
            headers["Authorization"] = f"Bearer {settings.crawl4ai_api_token}"

        payload = {
            "urls": urls,
            "browser_config": _BROWSER_CONFIG,
            "crawler_config": _CRAWLER_CONFIG,
        }

        try:
            async with httpx.AsyncClient(timeout=settings.crawl4ai_timeout * 2) as client:
                resp = await client.post(f"{base_url}/crawl", json=payload, headers=headers)
                resp.raise_for_status()
            data = resp.json()
        except Exception as e:
            logger.error(f"Batch crawl API failed: {e}")
            return [(url, {}) for url in urls]

        if not data.get("success") or not data.get("results"):
            return [(url, {}) for url in urls]

        output: List[Tuple[str, Dict[str, Any]]] = []
        for item in data["results"]:
            item_url = item.get("url", "")
            if not item.get("success"):
                logger.warning(f"Batch item failed ({item_url}): {item.get('error_message')}")
                output.append((item_url, {}))
                continue

            try:
                content = self._pick_markdown(item)
                html = item.get("html") or item.get("cleaned_html") or ""
                soup = BeautifulSoup(html, "html.parser") if html else None

                title = self._extract_title(soup) if soup else ""
                description = self._extract_description(soup, content) if soup else content[:500]
                published_at = self._extract_published_at(soup) if soup else None
                author = self._extract_author(soup) if soup else None
                image_url = self._extract_image(soup) if soup else None
                canonical_url = self._extract_canonical_url(soup, item_url) if soup else self.normalize_url(item_url)
                quality_score = self._quality_score(content, title, description)

                output.append((item_url, {
                    "title": title,
                    "description": description,
                    "content": content,
                    "author": author,
                    "image_url": image_url,
                    "published_at": published_at,
                    "canonical_url": canonical_url,
                    "url_hash": self.url_hash(canonical_url),
                    "quality_score": quality_score,
                }))
            except Exception as e:
                logger.warning(f"Batch post-processing failed for {item_url}: {e}")
                output.append((item_url, {}))

        return output

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
            dt = self._parse_date(str(meta["content"]))
            if dt:
                return dt
        return None

    @staticmethod
    def _parse_date(value: Optional[str]) -> Optional[datetime]:
        if not value or not value.strip():
            return None
        try:
            return date_parser.parse(value.strip())
        except Exception:
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
