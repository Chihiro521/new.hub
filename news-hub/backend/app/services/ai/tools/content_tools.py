"""Content fetching LangChain tools.

Tools: fetch_rss, scrape_webpage, scrape_webpage_light
"""

import json

from langchain_core.tools import tool
from loguru import logger


def create_content_tools():
    """Create content fetching tools (no user context needed)."""

    @tool
    async def fetch_rss(url: str, limit: int = 10) -> str:
        """主动抓取RSS/Atom源的文章列表。当用户提供RSS链接或要求抓取某个源时使用。只返回结果不保存。"""
        try:
            from app.services.collector.factory import CollectorFactory

            source_config = {"url": url, "source_type": "rss", "name": "AI临时抓取", "user_id": "temp"}
            result = await CollectorFactory.collect(source_config)
            if not result.success:
                return json.dumps({"error": result.error_message or "抓取失败", "items": []}, ensure_ascii=False)
            items = [
                {
                    "title": item.title,
                    "url": item.url,
                    "description": item.description or "",
                    "published_at": item.published_at.isoformat() if item.published_at else None,
                    "author": item.author or "",
                }
                for item in result.items[:limit]
            ]
            return json.dumps({"url": url, "count": len(items), "items": items}, ensure_ascii=False)
        except Exception as e:
            logger.error(f"fetch_rss failed: {e}")
            return json.dumps({"error": str(e), "items": []}, ensure_ascii=False)

    @tool
    async def scrape_webpage(url: str) -> str:
        """抓取网页正文内容。使用Crawl4AI进行JS渲染和智能提取，当用户提供网页链接并要求分析内容时使用。"""
        try:
            from app.services.collector.webpage_extractor import WebpageExtractor

            extractor = WebpageExtractor()
            result = await extractor.extract(url)

            if not result or not result.get("content"):
                return json.dumps({"url": url, "error": "无法提取内容", "title": "", "content": ""}, ensure_ascii=False)

            content = result["content"]
            if len(content) > 5000:
                content = content[:5000] + "...(已截断)"

            return json.dumps({
                "url": url,
                "title": result.get("title", ""),
                "content": content,
                "author": result.get("author"),
                "published_at": result["published_at"].isoformat() if result.get("published_at") else None,
                "quality_score": result.get("quality_score", 0),
            }, ensure_ascii=False)
        except Exception as e:
            logger.error(f"scrape_webpage failed: {e}")
            return json.dumps({"error": str(e), "title": "", "content": ""}, ensure_ascii=False)

    @tool
    async def scrape_webpage_light(url: str) -> str:
        """轻量抓取网页内容（跳过LLM格式化）。用于研究场景，速度更快，支持大页面。"""
        try:
            from app.services.collector.webpage_extractor import WebpageExtractor

            extractor = WebpageExtractor()
            result = await extractor.extract_light(url)

            if not result or not result.get("content"):
                return json.dumps({"url": url, "error": "无法提取内容", "title": "", "content": ""}, ensure_ascii=False)

            content = result["content"]
            if len(content) > 8000:
                content = content[:8000] + "...(已截断)"

            return json.dumps({
                "url": url,
                "title": result.get("title", ""),
                "content": content,
                "quality_score": result.get("quality_score", 0),
            }, ensure_ascii=False)
        except Exception as e:
            logger.error(f"scrape_webpage_light failed: {e}")
            return json.dumps({"error": str(e), "title": "", "content": ""}, ensure_ascii=False)

    return [fetch_rss, scrape_webpage, scrape_webpage_light]
