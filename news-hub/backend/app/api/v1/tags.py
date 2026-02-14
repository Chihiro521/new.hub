"""
Tag Rules API Routes

Provides endpoints for managing auto-tagging rules and viewing tags.
"""

from typing import List, Optional

from bson import ObjectId
from fastapi import APIRouter, Depends, HTTPException, Query, status
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.core.deps import get_current_user
from app.db.mongo import get_db
from app.schemas.response import ResponseBase, success_response
from app.schemas.tag import (
    TagRuleCreate,
    TagRuleUpdate,
    TagRuleResponse,
)
from app.schemas.user import UserInDB
from app.services.tagging import TagService

router = APIRouter(prefix="/tags", tags=["Tags"])


def rule_doc_to_response(doc: dict) -> TagRuleResponse:
    """Convert MongoDB document to TagRuleResponse."""
    return TagRuleResponse(
        id=str(doc["_id"]),
        user_id=doc["user_id"],
        tag_name=doc["tag_name"],
        keywords=doc["keywords"],
        match_mode=doc["match_mode"],
        case_sensitive=doc.get("case_sensitive", False),
        match_title=doc.get("match_title", True),
        match_description=doc.get("match_description", True),
        match_content=doc.get("match_content", False),
        priority=doc.get("priority", 0),
        is_active=doc.get("is_active", True),
        match_count=doc.get("match_count", 0),
        created_at=doc["created_at"],
    )


# === Tag Rules CRUD ===


@router.post(
    "/rules",
    response_model=ResponseBase[TagRuleResponse],
    status_code=status.HTTP_201_CREATED,
)
async def create_tag_rule(
    rule_data: TagRuleCreate,
    current_user: UserInDB = Depends(get_current_user),
    db: AsyncIOMotorDatabase = Depends(get_db),
):
    """
    Create a new tag rule.

    Tag rules automatically apply tags to news items that match the specified keywords.
    """
    service = TagService(db)
    doc = await service.create_rule(current_user.id, rule_data)
    return success_response(data=rule_doc_to_response(doc), message="Tag rule created")


@router.get("/rules", response_model=ResponseBase[List[TagRuleResponse]])
async def list_tag_rules(
    is_active: Optional[bool] = Query(None, description="Filter by active status"),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
    current_user: UserInDB = Depends(get_current_user),
    db: AsyncIOMotorDatabase = Depends(get_db),
):
    """
    List tag rules for the current user.

    Rules are sorted by priority (highest first).
    """
    service = TagService(db)
    rules = await service.list_rules(
        user_id=current_user.id,
        is_active=is_active,
        skip=skip,
        limit=limit,
    )
    return success_response(data=[rule_doc_to_response(doc) for doc in rules])


@router.get("/rules/{rule_id}", response_model=ResponseBase[TagRuleResponse])
async def get_tag_rule(
    rule_id: str,
    current_user: UserInDB = Depends(get_current_user),
    db: AsyncIOMotorDatabase = Depends(get_db),
):
    """Get a specific tag rule by ID."""
    service = TagService(db)
    doc = await service.get_rule(rule_id, current_user.id)

    if not doc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Tag rule not found",
        )

    return success_response(data=rule_doc_to_response(doc))


@router.patch("/rules/{rule_id}", response_model=ResponseBase[TagRuleResponse])
async def update_tag_rule(
    rule_id: str,
    update_data: TagRuleUpdate,
    current_user: UserInDB = Depends(get_current_user),
    db: AsyncIOMotorDatabase = Depends(get_db),
):
    """Update a tag rule."""
    service = TagService(db)
    doc = await service.update_rule(rule_id, current_user.id, update_data)

    if not doc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Tag rule not found",
        )

    return success_response(data=rule_doc_to_response(doc), message="Tag rule updated")


@router.delete("/rules/{rule_id}", response_model=ResponseBase[None])
async def delete_tag_rule(
    rule_id: str,
    current_user: UserInDB = Depends(get_current_user),
    db: AsyncIOMotorDatabase = Depends(get_db),
):
    """Delete a tag rule."""
    service = TagService(db)
    deleted = await service.delete_rule(rule_id, current_user.id)

    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Tag rule not found",
        )

    return success_response(data=None, message="Tag rule deleted")


# === Tag Queries ===


@router.get("", response_model=ResponseBase[List[dict]])
async def get_user_tags(
    current_user: UserInDB = Depends(get_current_user),
    db: AsyncIOMotorDatabase = Depends(get_db),
):
    """
    Get all tags used by the current user with counts.

    Returns a list of {tag_name, count} objects sorted by count (descending).
    """
    service = TagService(db)
    tags = await service.get_user_tags(current_user.id)
    return success_response(data=tags)


@router.get("/stats", response_model=ResponseBase[dict])
async def get_tag_stats(
    current_user: UserInDB = Depends(get_current_user),
    db: AsyncIOMotorDatabase = Depends(get_db),
):
    """Get tag statistics for the current user."""
    service = TagService(db)

    rules_count = await service.get_rules_count(current_user.id)
    tags = await service.get_user_tags(current_user.id)

    return success_response(
        data={
            "rules_count": rules_count,
            "unique_tags": len(tags),
            "total_tagged_items": sum(t.get("count", 0) for t in tags),
        }
    )


# === Keyword Extraction ===


@router.post("/extract-keywords", response_model=ResponseBase[List[str]])
async def extract_keywords_from_text(
    text: str,
    top_k: int = Query(10, ge=1, le=50, description="Number of keywords"),
    method: str = Query("tfidf", description="Extraction method: tfidf or textrank"),
    current_user: UserInDB = Depends(get_current_user),
):
    """
    Extract keywords from text using Jieba.

    Useful for testing keyword extraction or generating suggested keywords for rules.
    """
    from app.services.tagging import extract_keywords

    keywords = extract_keywords(text, top_k=top_k, method=method)
    return success_response(data=keywords)


@router.post("/retag-news", response_model=ResponseBase[dict])
async def retag_news_items(
    source_id: Optional[str] = Query(
        None, description="Only retag items from this source"
    ),
    limit: int = Query(100, ge=1, le=1000, description="Max items to retag"),
    current_user: UserInDB = Depends(get_current_user),
    db: AsyncIOMotorDatabase = Depends(get_db),
):
    """
    Re-apply tag rules to existing news items.

    Useful after creating new tag rules to apply them to existing items.
    """
    from app.services.tagging import RuleMatcher, TagService

    # Get user's active rules
    service = TagService(db)
    rules = await service.list_rules(user_id=current_user.id, is_active=True)

    if not rules:
        return success_response(
            data={"retagged": 0}, message="No active tag rules found"
        )

    # Build query
    query = {"user_id": current_user.id}
    if source_id:
        try:
            ObjectId(source_id)
            query["source_id"] = source_id
        except Exception:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid source ID format",
            )

    # Get news items
    cursor = db.news.find(query).limit(limit)
    news_items = await cursor.to_list(length=limit)

    # Create matcher
    matcher = RuleMatcher(rules)

    # Retag items
    retagged = 0
    rule_matches = {}

    for item in news_items:
        matched_tags, matched_rule_ids = matcher.match(
            title=item.get("title", ""),
            description=item.get("description", ""),
            content=item.get("content", ""),
        )

        if matched_tags:
            # Update tags
            await db.news.update_one(
                {"_id": item["_id"]},
                {"$set": {"tags": matched_tags}},
            )
            retagged += 1

            # Track rule matches for stats update
            for rid in matched_rule_ids:
                rule_matches[rid] = rule_matches.get(rid, 0) + 1

    # Update rule match counts
    for rid, count in rule_matches.items():
        try:
            await db.tag_rules.update_one(
                {"_id": ObjectId(rid)},
                {"$inc": {"match_count": count}},
            )
        except Exception:
            pass

    return success_response(
        data={"retagged": retagged, "total_processed": len(news_items)},
        message=f"Retagged {retagged} items",
    )
