"""Content fetching LangChain tools.

Tools: fetch_rss, scrape_webpage
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
        """抓取网页正文内容。当用户提供网页链接并要求分析内容时使用。"""
        try:
            import httpx
            from bs4 import BeautifulSoup

            async with httpx.AsyncClient(timeout=15, follow_redirects=True) as client:
                resp = await client.get(url, headers={"User-Agent": "Mozilla/5.0 (compatible; NewsHub/1.0)"})
                resp.raise_for_status()

            soup = BeautifulSoup(resp.text, "html.parser")
            for tag in soup(["script", "style", "nav", "footer", "header"]):
                tag.decompose()

            title = soup.title.string.strip() if soup.title and soup.title.string else ""
            article = soup.find("article") or soup.find("main") or soup.body
            text = article.get_text(separator="\n", strip=True) if article else ""
            if len(text) > 3000:
                text = text[:3000] + "...(已截断)"

            return json.dumps({"url": url, "title": title, "content": text}, ensure_ascii=False)
        except Exception as e:
            logger.error(f"scrape_webpage failed: {e}")
            return json.dumps({"error": str(e), "title": "", "content": ""}, ensure_ascii=False)

    return [fetch_rss, scrape_webpage]
