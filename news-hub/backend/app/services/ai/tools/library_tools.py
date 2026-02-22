"""Library management LangChain tools.

Tools: save_news_to_library, list_sources, add_source, delete_source
"""

import json
from datetime import datetime

from langchain_core.tools import tool
from loguru import logger

from app.db.es import es_client
from app.db.mongo import mongodb


def create_library_tools(user_id: str):
    """Create library management tools bound to a specific user."""

    @tool
    async def save_news_to_library(
        title: str, url: str, description: str = "", source_name: str = "AI助手"
    ) -> str:
        """保存一条新闻到用户的新闻库。当用户要求保存、收藏某条新闻时使用。"""
        try:
            from bson import ObjectId

            from app.services.search.indexer import ESIndexer
            from app.services.tagging.rule_matcher import RuleMatcher
            from app.services.tagging.tag_service import TagService

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

            if es_client.client:
                indexer = ESIndexer(es_client.client)
                await indexer.index_news_item(
                    user_id=user_id,
                    news_id=str(news_doc["_id"]),
                    doc={"title": title, "url": url, "description": description, "source_name": source_name, "tags": tags},
                )
            return json.dumps(
                {"success": True, "news_id": str(news_doc["_id"]), "tags": tags, "message": f"已保存: {title}"},
                ensure_ascii=False,
            )
        except Exception as e:
            logger.error(f"save_news failed: {e}")
            return json.dumps({"error": str(e), "success": False}, ensure_ascii=False)

    @tool
    async def list_sources() -> str:
        """列出用户的所有订阅源。当用户询问'我的订阅源'、'我订阅了什么'时使用。"""
        try:
            cursor = mongodb.db.sources.find({"user_id": user_id}).sort("created_at", -1)
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
            return json.dumps({"count": len(sources), "sources": sources}, ensure_ascii=False)
        except Exception as e:
            logger.error(f"list_sources failed: {e}")
            return json.dumps({"error": str(e), "sources": []}, ensure_ascii=False)

    @tool
    async def add_source(name: str, url: str, source_type: str = "rss") -> str:
        """添加新的订阅源。当用户要求订阅新的RSS源或新闻源时使用。"""
        try:
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
            return json.dumps(
                {"success": True, "source_id": str(source_doc["_id"]), "message": f"已添加订阅源: {name}"},
                ensure_ascii=False,
            )
        except Exception as e:
            logger.error(f"add_source failed: {e}")
            return json.dumps({"error": str(e), "success": False}, ensure_ascii=False)

    @tool
    async def delete_source(source_id: str) -> str:
        """删除一个订阅源及其关联新闻。当用户要求取消订阅或删除某个源时使用。"""
        try:
            from bson import ObjectId

            oid = ObjectId(source_id)
            result = await mongodb.db.sources.delete_one({"_id": oid, "user_id": user_id})
            if result.deleted_count == 0:
                return json.dumps({"success": False, "message": "未找到该订阅源"}, ensure_ascii=False)

            del_news = await mongodb.db.news.delete_many({"source_id": source_id, "user_id": user_id})
            if es_client.client:
                from app.services.search.indexer import ESIndexer

                indexer = ESIndexer(es_client.client)
                await indexer.delete_by_source(user_id, source_id)

            return json.dumps(
                {"success": True, "message": f"已删除订阅源，同时删除了 {del_news.deleted_count} 条关联新闻"},
                ensure_ascii=False,
            )
        except Exception as e:
            logger.error(f"delete_source failed: {e}")
            return json.dumps({"error": str(e), "success": False}, ensure_ascii=False)

    return [save_news_to_library, list_sources, add_source, delete_source]
