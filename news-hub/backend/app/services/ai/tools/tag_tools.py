"""Tag management LangChain tools.

Tools: list_tag_rules, add_tag_rule, delete_tag_rule
"""

import json
from typing import List

from langchain_core.tools import tool
from loguru import logger

from app.db.mongo import mongodb


def create_tag_tools(user_id: str):
    """Create tag management tools bound to a specific user."""

    @tool
    async def list_tag_rules() -> str:
        """列出用户的所有标签规则。当用户询问'我的标签'、'标签规则'时使用。"""
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
            return json.dumps({"count": len(items), "rules": items}, ensure_ascii=False)
        except Exception as e:
            logger.error(f"list_tag_rules failed: {e}")
            return json.dumps({"error": str(e), "rules": []}, ensure_ascii=False)

    @tool
    async def add_tag_rule(tag_name: str, keywords: List[str]) -> str:
        """创建新的自动标签规则。当用户要求创建标签、设置自动分类时使用。"""
        try:
            from app.schemas.tag import TagRuleCreate
            from app.services.tagging.tag_service import TagService

            tag_service = TagService(mongodb.db)
            data = TagRuleCreate(tag_name=tag_name, keywords=keywords)
            rule = await tag_service.create_rule(user_id, data)
            return json.dumps(
                {"success": True, "rule_id": str(rule["_id"]), "message": f"已创建标签规则: {tag_name} (关键词: {', '.join(keywords)})"},
                ensure_ascii=False,
            )
        except Exception as e:
            logger.error(f"add_tag_rule failed: {e}")
            return json.dumps({"error": str(e), "success": False}, ensure_ascii=False)

    @tool
    async def delete_tag_rule(rule_id: str) -> str:
        """删除一个标签规则。当用户要求删除某个标签规则时使用。"""
        try:
            from app.services.tagging.tag_service import TagService

            tag_service = TagService(mongodb.db)
            deleted = await tag_service.delete_rule(rule_id, user_id)
            if not deleted:
                return json.dumps({"success": False, "message": "未找到该标签规则"}, ensure_ascii=False)
            return json.dumps({"success": True, "message": "已删除标签规则"}, ensure_ascii=False)
        except Exception as e:
            logger.error(f"delete_tag_rule failed: {e}")
            return json.dumps({"error": str(e), "success": False}, ensure_ascii=False)

    return [list_tag_rules, add_tag_rule, delete_tag_rule]
