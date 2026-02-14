"""
Tag Service

CRUD operations for tag rules and tag management.
"""

from datetime import datetime
from typing import Any, Dict, List, Optional

from bson import ObjectId
from loguru import logger
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.schemas.tag import TagRuleCreate, TagRuleUpdate, TagRuleInDB


class TagService:
    """
    Service for managing tag rules.

    Provides CRUD operations and tag-related queries.
    """

    def __init__(self, db: AsyncIOMotorDatabase):
        """
        Initialize tag service.

        Args:
            db: Async MongoDB database instance
        """
        self.db = db
        self.collection = db.tag_rules

    async def create_rule(
        self,
        user_id: str,
        data: TagRuleCreate,
    ) -> Dict[str, Any]:
        """
        Create a new tag rule.

        Args:
            user_id: Owner user ID
            data: Tag rule creation data

        Returns:
            Created tag rule document
        """
        now = datetime.utcnow()

        doc = {
            "user_id": user_id,
            "tag_name": data.tag_name,
            "keywords": data.keywords,
            "match_mode": data.match_mode.value,
            "case_sensitive": data.case_sensitive,
            "match_title": data.match_title,
            "match_description": data.match_description,
            "match_content": data.match_content,
            "priority": data.priority,
            "is_active": True,
            "match_count": 0,
            "created_at": now,
            "updated_at": now,
        }

        result = await self.collection.insert_one(doc)
        doc["_id"] = result.inserted_id

        logger.info(f"Created tag rule '{data.tag_name}' for user {user_id}")

        return doc

    async def get_rule(
        self,
        rule_id: str,
        user_id: str,
    ) -> Optional[Dict[str, Any]]:
        """
        Get a tag rule by ID.

        Args:
            rule_id: Tag rule ID
            user_id: Owner user ID

        Returns:
            Tag rule document or None
        """
        try:
            oid = ObjectId(rule_id)
        except Exception:
            return None

        return await self.collection.find_one({"_id": oid, "user_id": user_id})

    async def list_rules(
        self,
        user_id: str,
        is_active: Optional[bool] = None,
        skip: int = 0,
        limit: int = 100,
    ) -> List[Dict[str, Any]]:
        """
        List tag rules for a user.

        Args:
            user_id: Owner user ID
            is_active: Filter by active status
            skip: Number of rules to skip
            limit: Maximum rules to return

        Returns:
            List of tag rule documents
        """
        query: Dict[str, Any] = {"user_id": user_id}

        if is_active is not None:
            query["is_active"] = is_active

        cursor = (
            self.collection.find(query)
            .sort([("priority", -1), ("created_at", -1)])
            .skip(skip)
            .limit(limit)
        )

        return await cursor.to_list(length=limit)

    async def update_rule(
        self,
        rule_id: str,
        user_id: str,
        data: TagRuleUpdate,
    ) -> Optional[Dict[str, Any]]:
        """
        Update a tag rule.

        Args:
            rule_id: Tag rule ID
            user_id: Owner user ID
            data: Update data

        Returns:
            Updated tag rule document or None
        """
        try:
            oid = ObjectId(rule_id)
        except Exception:
            return None

        # Build update fields (only include non-None values)
        update_fields = {"updated_at": datetime.utcnow()}

        if data.tag_name is not None:
            update_fields["tag_name"] = data.tag_name
        if data.keywords is not None:
            update_fields["keywords"] = data.keywords
        if data.match_mode is not None:
            update_fields["match_mode"] = data.match_mode.value
        if data.case_sensitive is not None:
            update_fields["case_sensitive"] = data.case_sensitive
        if data.match_title is not None:
            update_fields["match_title"] = data.match_title
        if data.match_description is not None:
            update_fields["match_description"] = data.match_description
        if data.match_content is not None:
            update_fields["match_content"] = data.match_content
        if data.priority is not None:
            update_fields["priority"] = data.priority
        if data.is_active is not None:
            update_fields["is_active"] = data.is_active

        result = await self.collection.update_one(
            {"_id": oid, "user_id": user_id},
            {"$set": update_fields},
        )

        if result.matched_count == 0:
            return None

        return await self.collection.find_one({"_id": oid})

    async def delete_rule(
        self,
        rule_id: str,
        user_id: str,
    ) -> bool:
        """
        Delete a tag rule.

        Args:
            rule_id: Tag rule ID
            user_id: Owner user ID

        Returns:
            True if deleted, False if not found
        """
        try:
            oid = ObjectId(rule_id)
        except Exception:
            return False

        result = await self.collection.delete_one({"_id": oid, "user_id": user_id})

        if result.deleted_count > 0:
            logger.info(f"Deleted tag rule {rule_id} for user {user_id}")
            return True

        return False

    async def increment_match_count(
        self,
        rule_ids: List[str],
    ) -> None:
        """
        Increment match count for multiple rules.

        Args:
            rule_ids: List of tag rule IDs
        """
        if not rule_ids:
            return

        oids = []
        for rid in rule_ids:
            try:
                oids.append(ObjectId(rid))
            except Exception:
                continue

        if oids:
            await self.collection.update_many(
                {"_id": {"$in": oids}},
                {"$inc": {"match_count": 1}},
            )

    async def get_user_tags(
        self,
        user_id: str,
    ) -> List[Dict[str, Any]]:
        """
        Get all unique tags used by a user with their counts.

        Args:
            user_id: Owner user ID

        Returns:
            List of {tag_name, count} dicts
        """
        pipeline = [
            {"$match": {"user_id": user_id}},
            {"$unwind": "$tags"},
            {"$group": {"_id": "$tags", "count": {"$sum": 1}}},
            {"$sort": {"count": -1}},
            {"$project": {"tag_name": "$_id", "count": 1, "_id": 0}},
        ]

        cursor = self.db.news.aggregate(pipeline)
        return await cursor.to_list(length=500)

    async def get_rules_count(self, user_id: str) -> int:
        """
        Get count of tag rules for a user.

        Args:
            user_id: Owner user ID

        Returns:
            Number of rules
        """
        return await self.collection.count_documents({"user_id": user_id})
