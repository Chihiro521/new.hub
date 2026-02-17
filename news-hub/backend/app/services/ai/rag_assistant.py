"""
RAG-enabled AI Assistant with Elasticsearch

Implements Retrieval-Augmented Generation using:
- Elasticsearch for document retrieval
- Hybrid search (keyword + semantic)
- Function calling for dynamic retrieval
"""

import json
import time
from typing import Any, AsyncGenerator, Dict, List, Optional

from loguru import logger

from app.core.config import settings
from app.db.es import es_client
from app.db.mongo import mongodb
from app.services.ai.audit import AuditLogger
from app.services.ai.llm_client import get_llm_client
from app.services.search.search_service import SearchService


class RAGAssistant:
    """AI Assistant with RAG capabilities using Elasticsearch."""

    def __init__(self):
        self.client = get_llm_client()
        self.audit = AuditLogger()
        self.search_service = None
        if es_client.client:
            self.search_service = SearchService(es_client.client)

    def _get_tools_definition(self) -> List[Dict[str, Any]]:
        """Define tools that AI can call."""
        return [
            {
                "type": "function",
                "function": {
                    "name": "search_user_news",
                    "description": "搜索用户的新闻库。当用户询问关于他们的新闻、文章、订阅内容时使用此工具。",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "query": {
                                "type": "string",
                                "description": "搜索关键词或问题",
                            },
                            "limit": {
                                "type": "integer",
                                "description": "返回结果数量",
                                "default": 5,
                            },
                        },
                        "required": ["query"],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "get_recent_news",
                    "description": "获取用户最近的新闻。当用户询问'最近有什么新闻'、'今天的新闻'等时使用。",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "hours": {
                                "type": "integer",
                                "description": "获取最近多少小时的新闻",
                                "default": 24,
                            },
                            "limit": {
                                "type": "integer",
                                "description": "返回结果数量",
                                "default": 10,
                            },
                        },
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "web_search",
                    "description": "搜索互联网获取最新信息。当用户询问的内容不在新闻库中，或需要最新信息时使用。",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "query": {
                                "type": "string",
                                "description": "搜索关键词",
                            },
                            "max_results": {
                                "type": "integer",
                                "description": "返回结果数量",
                                "default": 5,
                            },
                        },
                        "required": ["query"],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "fetch_rss",
                    "description": "主动抓取RSS/Atom源的文章列表。当用户提供RSS链接或要求抓取某个源时使用。只返回结果不保存。",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "url": {
                                "type": "string",
                                "description": "RSS/Atom源的URL",
                            },
                            "limit": {
                                "type": "integer",
                                "description": "返回文章数量上限",
                                "default": 10,
                            },
                        },
                        "required": ["url"],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "scrape_webpage",
                    "description": "抓取网页正文内容。当用户提供网页链接并要求分析内容时使用。",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "url": {
                                "type": "string",
                                "description": "网页URL",
                            },
                        },
                        "required": ["url"],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "save_news_to_library",
                    "description": "保存一条新闻到用户的新闻库。当用户要求保存、收藏某条新闻时使用。",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "title": {
                                "type": "string",
                                "description": "新闻标题",
                            },
                            "url": {
                                "type": "string",
                                "description": "新闻链接",
                            },
                            "description": {
                                "type": "string",
                                "description": "新闻摘要",
                                "default": "",
                            },
                            "source_name": {
                                "type": "string",
                                "description": "来源名称",
                                "default": "AI助手",
                            },
                        },
                        "required": ["title", "url"],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "list_sources",
                    "description": "列出用户的所有订阅源。当用户询问'我的订阅源'、'我订阅了什么'时使用。",
                    "parameters": {
                        "type": "object",
                        "properties": {},
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "add_source",
                    "description": "添加新的订阅源。当用户要求订阅新的RSS源或新闻源时使用。",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "name": {
                                "type": "string",
                                "description": "订阅源名称",
                            },
                            "url": {
                                "type": "string",
                                "description": "订阅源URL",
                            },
                            "source_type": {
                                "type": "string",
                                "description": "源类型：rss 或 api",
                                "default": "rss",
                            },
                        },
                        "required": ["name", "url"],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "delete_source",
                    "description": "删除一个订阅源及其关联新闻。当用户要求取消订阅或删除某个源时使用。",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "source_id": {
                                "type": "string",
                                "description": "要删除的订阅源ID",
                            },
                        },
                        "required": ["source_id"],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "list_tag_rules",
                    "description": "列出用户的所有标签规则。当用户询问'我的标签'、'标签规则'时使用。",
                    "parameters": {
                        "type": "object",
                        "properties": {},
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "add_tag_rule",
                    "description": "创建新的自动标签规则。当用户要求创建标签、设置自动分类时使用。",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "tag_name": {
                                "type": "string",
                                "description": "标签名称",
                            },
                            "keywords": {
                                "type": "array",
                                "items": {"type": "string"},
                                "description": "匹配关键词列表",
                            },
                        },
                        "required": ["tag_name", "keywords"],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "delete_tag_rule",
                    "description": "删除一个标签规则。当用户要求删除某个标签规则时使用。",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "rule_id": {
                                "type": "string",
                                "description": "要删除的规则ID",
                            },
                        },
                        "required": ["rule_id"],
                    },
                },
            },
        ]

    async def _handle_search_user_news(
        self, user_id: str, query: str, limit: int = 5
    ) -> Dict[str, Any]:
        """Handle search_user_news tool call."""
        if not self.search_service:
            return {"error": "Elasticsearch not available", "results": []}

        try:
            response = await self.search_service.search(
                user_id=user_id,
                query=query,
                search_type="hybrid",
                page_size=limit,
            )

            results = [
                {
                    "title": r.title,
                    "url": r.url,
                    "description": r.description or "",
                    "source": r.source_name,
                    "published_at": (
                        r.published_at.isoformat() if r.published_at else None
                    ),
                    "score": round(r.score, 3),
                }
                for r in response.results
            ]

            return {
                "query": query,
                "total": response.total,
                "results": results,
                "took_ms": response.took_ms,
            }
        except Exception as e:
            logger.error(f"Search user news failed: {e}")
            return {"error": str(e), "results": []}

    async def _handle_get_recent_news(
        self, user_id: str, hours: int = 24, limit: int = 10
    ) -> Dict[str, Any]:
        """Handle get_recent_news tool call."""
        try:
            from datetime import datetime, timedelta

            start_date = datetime.utcnow() - timedelta(hours=hours)

            cursor = (
                mongodb.db.news.find(
                    {
                        "user_id": user_id,
                        "crawled_at": {"$gte": start_date},
                    }
                )
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
                    "crawled_at": doc.get("crawled_at").isoformat()
                    if doc.get("crawled_at")
                    else None,
                }
                for doc in docs
            ]

            return {
                "hours": hours,
                "count": len(results),
                "results": results,
            }
        except Exception as e:
            logger.error(f"Get recent news failed: {e}")
            return {"error": str(e), "results": []}

    async def _handle_web_search(
        self, query: str, max_results: int = 5
    ) -> Dict[str, Any]:
        """Handle web_search tool call."""
        try:
            from app.services.ai.web_search import WebSearchClient

            client = WebSearchClient()
            if not client.available:
                return {
                    "error": "External search not configured",
                    "results": [],
                }

            results = await client.search(query, max_results=max_results)

            return {
                "query": query,
                "count": len(results),
                "results": [
                    {
                        "title": r.get("title", ""),
                        "url": r.get("url", ""),
                        "description": r.get("description", ""),
                        "score": r.get("score", 0),
                    }
                    for r in results
                ],
            }
        except Exception as e:
            logger.error(f"Web search failed: {e}")
            return {"error": str(e), "results": []}

    async def _handle_fetch_rss(
        self, url: str, limit: int = 10
    ) -> Dict[str, Any]:
        """Handle fetch_rss tool call."""
        try:
            from app.services.collector.factory import CollectorFactory

            source_config = {
                "url": url,
                "source_type": "rss",
                "name": "AI临时抓取",
                "user_id": "temp",
            }
            result = await CollectorFactory.collect(source_config)
            if not result.success:
                return {"error": result.error_message or "抓取失败", "items": []}

            items = [
                {
                    "title": item.title,
                    "url": item.url,
                    "description": item.description or "",
                    "published_at": (
                        item.published_at.isoformat() if item.published_at else None
                    ),
                    "author": item.author or "",
                }
                for item in result.items[:limit]
            ]
            return {"url": url, "count": len(items), "items": items}
        except Exception as e:
            logger.error(f"Fetch RSS failed: {e}")
            return {"error": str(e), "items": []}

    async def _handle_scrape_webpage(self, url: str) -> Dict[str, Any]:
        """Handle scrape_webpage tool call."""
        try:
            import httpx
            from bs4 import BeautifulSoup

            async with httpx.AsyncClient(
                timeout=15, follow_redirects=True
            ) as client:
                resp = await client.get(url, headers={
                    "User-Agent": "Mozilla/5.0 (compatible; NewsHub/1.0)"
                })
                resp.raise_for_status()

            soup = BeautifulSoup(resp.text, "html.parser")

            # Remove script/style elements
            for tag in soup(["script", "style", "nav", "footer", "header"]):
                tag.decompose()

            title = soup.title.string.strip() if soup.title and soup.title.string else ""

            # Try to find main content
            article = soup.find("article") or soup.find("main") or soup.body
            text = article.get_text(separator="\n", strip=True) if article else ""

            # Truncate to avoid token overflow
            if len(text) > 3000:
                text = text[:3000] + "...(已截断)"

            return {"url": url, "title": title, "content": text}
        except Exception as e:
            logger.error(f"Scrape webpage failed: {e}")
            return {"error": str(e), "title": "", "content": ""}

    async def _handle_save_news(
        self,
        user_id: str,
        title: str,
        url: str,
        description: str = "",
        source_name: str = "AI助手",
    ) -> Dict[str, Any]:
        """Handle save_news_to_library tool call."""
        try:
            from datetime import datetime

            from bson import ObjectId

            from app.services.search.indexer import ESIndexer
            from app.services.tagging.rule_matcher import RuleMatcher
            from app.services.tagging.tag_service import TagService

            # Auto-tag
            tag_service = TagService(mongodb.db)
            rules = await tag_service.list_rules(user_id)
            matcher = RuleMatcher(rules)
            tags, matched_rule_ids = matcher.match(title, description)

            if matched_rule_ids:
                await tag_service.increment_match_count(matched_rule_ids)

            news_doc = {
                "_id": ObjectId(),
                "user_id": user_id,
                "title": title,
                "url": url,
                "description": description,
                "source_name": source_name,
                "tags": tags,
                "is_read": False,
                "is_starred": False,
                "crawled_at": datetime.utcnow(),
            }

            await mongodb.db.news.insert_one(news_doc)

            # Index to ES
            if es_client.client:
                indexer = ESIndexer(es_client.client)
                await indexer.index_news_item(
                    user_id=user_id,
                    news_id=str(news_doc["_id"]),
                    doc={
                        "title": title,
                        "url": url,
                        "description": description,
                        "source_name": source_name,
                        "tags": tags,
                    },
                )

            return {
                "success": True,
                "news_id": str(news_doc["_id"]),
                "tags": tags,
                "message": f"已保存: {title}",
            }
        except Exception as e:
            logger.error(f"Save news failed: {e}")
            return {"error": str(e), "success": False}

    async def _handle_list_sources(self, user_id: str) -> Dict[str, Any]:
        """Handle list_sources tool call."""
        try:
            cursor = mongodb.db.sources.find({"user_id": user_id}).sort(
                "created_at", -1
            )
            docs = await cursor.to_list(length=50)

            sources = [
                {
                    "id": str(doc["_id"]),
                    "name": doc.get("name", ""),
                    "url": doc.get("url", ""),
                    "source_type": doc.get("source_type", ""),
                    "status": doc.get("status", ""),
                    "article_count": doc.get("article_count", 0),
                }
                for doc in docs
            ]
            return {"count": len(sources), "sources": sources}
        except Exception as e:
            logger.error(f"List sources failed: {e}")
            return {"error": str(e), "sources": []}

    async def _handle_add_source(
        self, user_id: str, name: str, url: str, source_type: str = "rss"
    ) -> Dict[str, Any]:
        """Handle add_source tool call."""
        try:
            from datetime import datetime

            from bson import ObjectId

            source_doc = {
                "_id": ObjectId(),
                "user_id": user_id,
                "name": name,
                "url": url,
                "source_type": source_type,
                "status": "active",
                "article_count": 0,
                "error_count": 0,
                "created_at": datetime.utcnow(),
                "updated_at": datetime.utcnow(),
            }
            await mongodb.db.sources.insert_one(source_doc)
            return {
                "success": True,
                "source_id": str(source_doc["_id"]),
                "message": f"已添加订阅源: {name}",
            }
        except Exception as e:
            logger.error(f"Add source failed: {e}")
            return {"error": str(e), "success": False}

    async def _handle_delete_source(
        self, user_id: str, source_id: str
    ) -> Dict[str, Any]:
        """Handle delete_source tool call."""
        try:
            from bson import ObjectId

            oid = ObjectId(source_id)
            result = await mongodb.db.sources.delete_one(
                {"_id": oid, "user_id": user_id}
            )
            if result.deleted_count == 0:
                return {"success": False, "message": "未找到该订阅源"}

            # Delete associated news
            del_news = await mongodb.db.news.delete_many(
                {"source_id": source_id, "user_id": user_id}
            )

            # Delete from ES
            if es_client.client:
                from app.services.search.indexer import ESIndexer

                indexer = ESIndexer(es_client.client)
                await indexer.delete_by_source(user_id, source_id)

            return {
                "success": True,
                "message": f"已删除订阅源，同时删除了 {del_news.deleted_count} 条关联新闻",
            }
        except Exception as e:
            logger.error(f"Delete source failed: {e}")
            return {"error": str(e), "success": False}

    async def _handle_list_tag_rules(self, user_id: str) -> Dict[str, Any]:
        """Handle list_tag_rules tool call."""
        try:
            from app.services.tagging.tag_service import TagService

            tag_service = TagService(mongodb.db)
            rules = await tag_service.list_rules(user_id)

            items = [
                {
                    "id": str(r["_id"]),
                    "tag_name": r.get("tag_name", ""),
                    "keywords": r.get("keywords", []),
                    "match_mode": r.get("match_mode", "any"),
                    "is_active": r.get("is_active", True),
                    "match_count": r.get("match_count", 0),
                }
                for r in rules
            ]
            return {"count": len(items), "rules": items}
        except Exception as e:
            logger.error(f"List tag rules failed: {e}")
            return {"error": str(e), "rules": []}

    async def _handle_add_tag_rule(
        self, user_id: str, tag_name: str, keywords: List[str]
    ) -> Dict[str, Any]:
        """Handle add_tag_rule tool call."""
        try:
            from app.schemas.tag import TagRuleCreate
            from app.services.tagging.tag_service import TagService

            tag_service = TagService(mongodb.db)
            data = TagRuleCreate(tag_name=tag_name, keywords=keywords)
            rule = await tag_service.create_rule(user_id, data)
            return {
                "success": True,
                "rule_id": str(rule["_id"]),
                "message": f"已创建标签规则: {tag_name} (关键词: {', '.join(keywords)})",
            }
        except Exception as e:
            logger.error(f"Add tag rule failed: {e}")
            return {"error": str(e), "success": False}

    async def _handle_delete_tag_rule(
        self, user_id: str, rule_id: str
    ) -> Dict[str, Any]:
        """Handle delete_tag_rule tool call."""
        try:
            from app.services.tagging.tag_service import TagService

            tag_service = TagService(mongodb.db)
            deleted = await tag_service.delete_rule(rule_id, user_id)
            if not deleted:
                return {"success": False, "message": "未找到该标签规则"}
            return {"success": True, "message": "已删除标签规则"}
        except Exception as e:
            logger.error(f"Delete tag rule failed: {e}")
            return {"error": str(e), "success": False}

    async def _execute_tool_call(
        self, tool_name: str, arguments: Dict[str, Any], user_id: str
    ) -> Dict[str, Any]:
        """Execute a tool call and return the result."""
        if tool_name == "search_user_news":
            return await self._handle_search_user_news(
                user_id=user_id,
                query=arguments.get("query", ""),
                limit=arguments.get("limit", 5),
            )
        elif tool_name == "get_recent_news":
            return await self._handle_get_recent_news(
                user_id=user_id,
                hours=arguments.get("hours", 24),
                limit=arguments.get("limit", 10),
            )
        elif tool_name == "web_search":
            return await self._handle_web_search(
                query=arguments.get("query", ""),
                max_results=arguments.get("max_results", 5),
            )
        elif tool_name == "fetch_rss":
            return await self._handle_fetch_rss(
                url=arguments.get("url", ""),
                limit=arguments.get("limit", 10),
            )
        elif tool_name == "scrape_webpage":
            return await self._handle_scrape_webpage(
                url=arguments.get("url", ""),
            )
        elif tool_name == "save_news_to_library":
            return await self._handle_save_news(
                user_id=user_id,
                title=arguments.get("title", ""),
                url=arguments.get("url", ""),
                description=arguments.get("description", ""),
                source_name=arguments.get("source_name", "AI助手"),
            )
        elif tool_name == "list_sources":
            return await self._handle_list_sources(user_id=user_id)
        elif tool_name == "add_source":
            return await self._handle_add_source(
                user_id=user_id,
                name=arguments.get("name", ""),
                url=arguments.get("url", ""),
                source_type=arguments.get("source_type", "rss"),
            )
        elif tool_name == "delete_source":
            return await self._handle_delete_source(
                user_id=user_id,
                source_id=arguments.get("source_id", ""),
            )
        elif tool_name == "list_tag_rules":
            return await self._handle_list_tag_rules(user_id=user_id)
        elif tool_name == "add_tag_rule":
            return await self._handle_add_tag_rule(
                user_id=user_id,
                tag_name=arguments.get("tag_name", ""),
                keywords=arguments.get("keywords", []),
            )
        elif tool_name == "delete_tag_rule":
            return await self._handle_delete_tag_rule(
                user_id=user_id,
                rule_id=arguments.get("rule_id", ""),
            )
        else:
            return {"error": f"Unknown tool: {tool_name}"}

    async def chat_with_rag(
        self,
        messages: List[Dict[str, str]],
        user_id: str,
        max_iterations: int = 5,
    ) -> AsyncGenerator[str, None]:
        """
        Chat with RAG capabilities.

        The AI can autonomously decide when to retrieve information from:
        - User's news library (Elasticsearch)
        - Recent news (MongoDB)
        - External web search (Tavily)
        """
        t0 = time.monotonic()

        if self.client is None:
            fallback = "AI 助手暂不可用，请先配置 OPENAI_API_KEY。"
            yield fallback
            await self.audit.log(
                user_id=user_id,
                action="rag_chat",
                input_summary=messages[-1].get("content", "")[:200] if messages else "",
                output_summary=fallback,
                latency_ms=int((time.monotonic() - t0) * 1000),
                fallback_used=True,
            )
            return

        # System prompt for RAG
        system_prompt = """你是 News Hub 的智能新闻助手。

你可以使用以下工具来帮助用户：
1. search_user_news - 搜索用户的新闻库
2. get_recent_news - 获取用户最近的新闻
3. web_search - 搜索互联网获取最新信息
4. fetch_rss - 主动抓取RSS/Atom源的文章列表
5. scrape_webpage - 抓取网页正文内容进行分析
6. save_news_to_library - 保存新闻到用户的新闻库
7. list_sources - 列出用户的所有订阅源
8. add_source - 添加新的订阅源
9. delete_source - 删除订阅源及其关联新闻
10. list_tag_rules - 列出用户的标签规则
11. add_tag_rule - 创建新的自动标签规则
12. delete_tag_rule - 删除标签规则

工作流程：
1. 理解用户的问题
2. 判断是否需要检索信息或执行操作
3. 选择合适的工具执行
4. 基于结果回答问题或确认操作

重要原则：
- 优先使用用户的新闻库
- 只在必要时搜索互联网
- 基于事实回答，不要编造信息
- 引用来源时提供标题和链接
- 执行删除等危险操作前，先确认用户意图
"""

        conversation = [{"role": "system", "content": system_prompt}, *messages]
        tools = self._get_tools_definition()

        collected_chunks: List[str] = []
        tool_calls_made: List[str] = []

        try:
            for iteration in range(max_iterations):
                # Call LLM
                response = await self.client.chat.completions.create(
                    model=settings.openai_model,
                    messages=conversation,
                    tools=tools,
                    tool_choice="auto",
                    stream=False,  # We'll handle streaming separately
                )

                message = response.choices[0].message

                # If no tool calls, return the response
                if not message.tool_calls:
                    content = message.content or ""
                    collected_chunks.append(content)
                    yield content

                    # Log audit
                    await self.audit.log(
                        user_id=user_id,
                        action="rag_chat",
                        input_summary=messages[-1].get("content", "")[:200]
                        if messages
                        else "",
                        output_summary=content[:200],
                        model=settings.openai_model,
                        latency_ms=int((time.monotonic() - t0) * 1000),
                    )
                    return

                # AI wants to call tools
                conversation.append(
                    {
                        "role": "assistant",
                        "content": message.content,
                        "tool_calls": [
                            {
                                "id": tc.id,
                                "type": "function",
                                "function": {
                                    "name": tc.function.name,
                                    "arguments": tc.function.arguments,
                                },
                            }
                            for tc in message.tool_calls
                        ],
                    }
                )

                # Execute all tool calls
                for tool_call in message.tool_calls:
                    function_name = tool_call.function.name
                    function_args = json.loads(tool_call.function.arguments)

                    logger.info(
                        f"AI calling tool: {function_name} with args: {function_args}"
                    )
                    tool_calls_made.append(function_name)

                    # Execute tool
                    result = await self._execute_tool_call(
                        tool_name=function_name,
                        arguments=function_args,
                        user_id=user_id,
                    )

                    # Add tool result to conversation
                    conversation.append(
                        {
                            "role": "tool",
                            "tool_call_id": tool_call.id,
                            "content": json.dumps(result, ensure_ascii=False),
                        }
                    )

                    # Yield a status message to user
                    status = f"\n[🔍 正在{function_name}...]\n"
                    yield status

            # Max iterations reached
            error_msg = "抱歉，处理超时。请尝试简化问题。"
            yield error_msg

            await self.audit.log(
                user_id=user_id,
                action="rag_chat",
                input_summary=messages[-1].get("content", "")[:200] if messages else "",
                output_summary=error_msg,
                model=settings.openai_model,
                latency_ms=int((time.monotonic() - t0) * 1000),
                error="Max iterations reached",
            )

        except Exception as e:
            logger.error(f"RAG chat failed: {e}")
            error_msg = f"抱歉，发生错误：{str(e)}"
            yield error_msg

            await self.audit.log(
                user_id=user_id,
                action="rag_chat",
                input_summary=messages[-1].get("content", "")[:200] if messages else "",
                model=settings.openai_model,
                latency_ms=int((time.monotonic() - t0) * 1000),
                error=str(e),
            )
